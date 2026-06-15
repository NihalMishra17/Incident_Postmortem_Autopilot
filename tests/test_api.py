import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from redis.exceptions import RedisError
from api.main import app


@pytest.fixture
def client():
    """Create FastAPI test client."""
    return TestClient(app)


def test_list_postmortems_empty(client):
    """GET /postmortems with empty store should return empty list."""
    mock_redis = MagicMock()
    mock_redis.smembers.return_value = set()

    with patch("api.main._redis_client", mock_redis):
        response = client.get("/postmortems")

    assert response.status_code == 200
    assert response.json() == []


def test_get_postmortem_not_found(client):
    """GET /postmortems/{id} for nonexistent ID should return 404."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    with patch("api.main._redis_client", mock_redis):
        response = client.get("/postmortems/nonexistent-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Postmortem not found"


def test_trigger_returns_202(client):
    """POST /postmortems/trigger with valid body should return 202 and alert_id."""
    mock_producer = MagicMock()

    with patch("api.main._producer", mock_producer):
        response = client.post(
            "/postmortems/trigger",
            json={
                "service": "api-gateway",
                "severity": "P1",
                "description": "High latency detected on /api/users endpoint",
            },
        )

    assert response.status_code == 202
    data = response.json()
    assert "alert_id" in data
    assert data["status"] == "queued"

    mock_producer.flush.assert_called_once()


def test_trigger_invalid_severity(client):
    """POST /postmortems/trigger with invalid severity should return 422."""
    response = client.post(
        "/postmortems/trigger",
        json={
            "service": "database",
            "severity": "P9",
            "description": "Invalid severity level",
        },
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_trigger_missing_field(client):
    """POST /postmortems/trigger without required field should return 422."""
    response = client.post(
        "/postmortems/trigger",
        json={
            "severity": "P2",
            "description": "Missing service field",
        },
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_list_postmortems_with_data(client):
    """GET /postmortems should return all stored postmortems."""
    pm1 = {"incident_id": "pm-1", "title": "Database Outage", "severity": "critical"}
    pm2 = {"incident_id": "pm-2", "title": "Cache Miss Rate Spike", "severity": "high"}

    mock_redis = MagicMock()
    mock_redis.smembers.return_value = {"pm-1", "pm-2"}
    mock_redis.mget.return_value = [json.dumps(pm1), json.dumps(pm2)]

    with patch("api.main._redis_client", mock_redis):
        response = client.get("/postmortems")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert any(pm["incident_id"] == "pm-1" for pm in data)
    assert any(pm["incident_id"] == "pm-2" for pm in data)


def test_get_postmortem_success(client):
    """GET /postmortems/{id} for existing ID should return postmortem."""
    pm = {
        "incident_id": "pm-123",
        "title": "API Gateway Latency",
        "severity": "critical",
        "root_cause": "Connection pool exhausted",
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(pm)

    with patch("api.main._redis_client", mock_redis):
        response = client.get("/postmortems/pm-123")

    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "pm-123"
    assert data["title"] == "API Gateway Latency"
    assert data["severity"] == "critical"


def test_trigger_default_severity(client):
    """POST /postmortems/trigger without severity should default to P2."""
    mock_producer = MagicMock()

    with patch("api.main._producer", mock_producer):
        response = client.post(
            "/postmortems/trigger",
            json={
                "service": "worker-service",
                "description": "Task queue backed up",
            },
        )

    assert response.status_code == 202
    data = response.json()
    assert "alert_id" in data

    mock_producer.produce.assert_called_once()
    call_args = mock_producer.produce.call_args
    assert call_args is not None


def test_list_postmortems_redis_error(client):
    """GET /postmortems should return 503 when Redis is unavailable."""
    mock_redis = MagicMock()
    mock_redis.smembers.side_effect = RedisError("Connection timeout")

    with patch("api.main._redis_client", mock_redis):
        response = client.get("/postmortems")

    assert response.status_code == 503
    assert response.json()["detail"] == "Cache unavailable"


def test_get_postmortem_redis_error(client):
    """GET /postmortems/{id} should return 503 when Redis is unavailable."""
    mock_redis = MagicMock()
    mock_redis.get.side_effect = RedisError("Connection timeout")

    with patch("api.main._redis_client", mock_redis):
        response = client.get("/postmortems/test-id")

    assert response.status_code == 503
    assert response.json()["detail"] == "Cache unavailable"
