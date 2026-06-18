import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, call
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


# ============================
# PATCH /postmortems/{incident_id}/verify tests
# ============================


def test_verify_postmortem_happy_path(client):
    """PATCH /postmortems/{id}/verify with valid data should return 200 with verified fields and call Weaviate insert."""
    pm = {
        "incident_id": "pm-verify-1",
        "title": "Database Connection Pool Exhausted",
        "severity": "critical",
        "affected_services": ["auth-service", "user-service"],
    }

    mock_redis = MagicMock()
    # First GET call returns the original postmortem
    mock_redis.get.return_value = json.dumps(pm)
    # Second SET call (after verification) succeeds
    mock_redis.set.return_value = True

    mock_weaviate = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate.collections.get.return_value = mock_collection

    mock_genai_client = MagicMock()
    mock_result = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.1] * 768
    mock_result.embeddings = [mock_embedding]
    mock_genai_client.models.embed_content.return_value = mock_result

    with patch("api.main._redis_client", mock_redis), \
         patch("api.main._weaviate_client", mock_weaviate), \
         patch("api.main.genai.Client", return_value=mock_genai_client), \
         patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        response = client.patch(
            "/postmortems/pm-verify-1/verify",
            json={
                "confirmed_root_cause": "Max connections reached due to connection leak",
                "confirmed_fix": "Patched connection cleanup in ORM layer",
                "verified_by": "john.doe@example.com",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["verified"] is True
    assert data["verified_by"] == "john.doe@example.com"
    assert "verified_at" in data
    assert data["confirmed_root_cause"] == "Max connections reached due to connection leak"
    assert data["confirmed_fix"] == "Patched connection cleanup in ORM layer"
    assert data["incident_id"] == "pm-verify-1"
    assert data["title"] == "Database Connection Pool Exhausted"

    # Verify Weaviate insert was called with correct args
    mock_collection.data.insert.assert_called_once()
    insert_args = mock_collection.data.insert.call_args
    assert insert_args[1]["properties"]["title"] == "Database Connection Pool Exhausted"
    assert insert_args[1]["properties"]["root_cause"] == "Max connections reached due to connection leak"
    assert insert_args[1]["properties"]["fix"] == "Patched connection cleanup in ORM layer"
    assert insert_args[1]["properties"]["service"] == "auth-service, user-service"
    assert insert_args[1]["vector"] == [0.1] * 768

    # Verify Redis set was called with TTL
    mock_redis.set.assert_called_once()
    set_call = mock_redis.set.call_args
    assert set_call[0][0] == "postmortem:pm-verify-1"
    stored_pm = json.loads(set_call[0][1])
    assert stored_pm["verified"] is True
    assert set_call[1]["ex"] == 86400


def test_verify_postmortem_not_found(client):
    """PATCH /postmortems/{id}/verify for nonexistent ID should return 404."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    with patch("api.main._redis_client", mock_redis):
        response = client.patch(
            "/postmortems/nonexistent-id/verify",
            json={
                "confirmed_root_cause": "Root cause here",
                "confirmed_fix": "Fix here",
                "verified_by": "user@example.com",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Postmortem not found"


def test_verify_postmortem_already_verified(client):
    """PATCH /postmortems/{id}/verify for already-verified postmortem should return 409 and not call Weaviate."""
    pm = {
        "incident_id": "pm-already-verified",
        "title": "Cache Outage",
        "verified": True,
        "verified_by": "jane.smith@example.com",
        "verified_at": "2026-06-15T10:30:00Z",
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(pm)

    mock_weaviate = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate.collections.get.return_value = mock_collection

    with patch("api.main._redis_client", mock_redis), \
         patch("api.main._weaviate_client", mock_weaviate):
        response = client.patch(
            "/postmortems/pm-already-verified/verify",
            json={
                "confirmed_root_cause": "New root cause",
                "confirmed_fix": "New fix",
                "verified_by": "another@example.com",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Postmortem already verified"

    # Ensure Weaviate insert was NOT called (409 short-circuits)
    mock_collection.data.insert.assert_not_called()


def test_verify_postmortem_missing_title(client):
    """PATCH /postmortems/{id}/verify for postmortem without title should return 500."""
    pm = {
        "incident_id": "pm-no-title",
        "severity": "critical",
        # title is missing
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(pm)

    with patch("api.main._redis_client", mock_redis):
        response = client.patch(
            "/postmortems/pm-no-title/verify",
            json={
                "confirmed_root_cause": "Root cause",
                "confirmed_fix": "Fix",
                "verified_by": "user@example.com",
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Postmortem record is missing a title"


def test_verify_postmortem_empty_title(client):
    """PATCH /postmortems/{id}/verify for postmortem with empty title should return 500."""
    pm = {
        "incident_id": "pm-empty-title",
        "title": "",
        "severity": "critical",
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(pm)

    with patch("api.main._redis_client", mock_redis):
        response = client.patch(
            "/postmortems/pm-empty-title/verify",
            json={
                "confirmed_root_cause": "Root cause",
                "confirmed_fix": "Fix",
                "verified_by": "user@example.com",
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Postmortem record is missing a title"


def test_verify_postmortem_redis_error_on_get(client):
    """PATCH /postmortems/{id}/verify should return 503 when Redis GET fails."""
    mock_redis = MagicMock()
    mock_redis.get.side_effect = RedisError("Connection timeout")

    with patch("api.main._redis_client", mock_redis):
        response = client.patch(
            "/postmortems/test-id/verify",
            json={
                "confirmed_root_cause": "Root cause",
                "confirmed_fix": "Fix",
                "verified_by": "user@example.com",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Cache unavailable"


def test_verify_postmortem_redis_error_on_set(client):
    """PATCH /postmortems/{id}/verify should return 503 when Redis SET fails after verification."""
    pm = {
        "incident_id": "pm-redis-set-fail",
        "title": "Service Outage",
        "severity": "critical",
        "affected_services": ["payment-service"],
    }

    mock_redis = MagicMock()
    # GET succeeds
    mock_redis.get.return_value = json.dumps(pm)
    # SET fails
    mock_redis.set.side_effect = RedisError("Write timeout")

    mock_weaviate = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate.collections.get.return_value = mock_collection

    mock_genai_client = MagicMock()
    mock_result = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.2] * 768
    mock_result.embeddings = [mock_embedding]
    mock_genai_client.models.embed_content.return_value = mock_result

    with patch("api.main._redis_client", mock_redis), \
         patch("api.main._weaviate_client", mock_weaviate), \
         patch("api.main.genai.Client", return_value=mock_genai_client), \
         patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        response = client.patch(
            "/postmortems/pm-redis-set-fail/verify",
            json={
                "confirmed_root_cause": "Payment gateway timeout",
                "confirmed_fix": "Increased timeout and added circuit breaker",
                "verified_by": "ops@example.com",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Cache unavailable"


def test_verify_postmortem_weaviate_insert_fails(client):
    """PATCH /postmortems/{id}/verify should return 503 when Weaviate insert fails."""
    pm = {
        "incident_id": "pm-weaviate-fail",
        "title": "API Gateway Down",
        "severity": "critical",
        "affected_services": ["gateway"],
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(pm)

    mock_weaviate = MagicMock()
    mock_collection = MagicMock()
    mock_collection.data.insert.side_effect = Exception("Weaviate connection error")
    mock_weaviate.collections.get.return_value = mock_collection

    mock_genai_client = MagicMock()
    mock_result = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.3] * 768
    mock_result.embeddings = [mock_embedding]
    mock_genai_client.models.embed_content.return_value = mock_result

    with patch("api.main._redis_client", mock_redis), \
         patch("api.main._weaviate_client", mock_weaviate), \
         patch("api.main.genai.Client", return_value=mock_genai_client), \
         patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        response = client.patch(
            "/postmortems/pm-weaviate-fail/verify",
            json={
                "confirmed_root_cause": "DDoS attack",
                "confirmed_fix": "Rate limiting enabled",
                "verified_by": "security@example.com",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Vector store unavailable"


def test_verify_postmortem_empty_confirmed_root_cause(client):
    """PATCH /postmortems/{id}/verify with empty confirmed_root_cause should return 422."""
    response = client.patch(
        "/postmortems/test-id/verify",
        json={
            "confirmed_root_cause": "",
            "confirmed_fix": "Fix applied",
            "verified_by": "user@example.com",
        },
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_verify_postmortem_whitespace_only_confirmed_root_cause(client):
    """PATCH /postmortems/{id}/verify with whitespace-only confirmed_root_cause should return 422."""
    response = client.patch(
        "/postmortems/test-id/verify",
        json={
            "confirmed_root_cause": "   \n\t  ",
            "confirmed_fix": "Fix applied",
            "verified_by": "user@example.com",
        },
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_verify_postmortem_empty_confirmed_fix(client):
    """PATCH /postmortems/{id}/verify with empty confirmed_fix should return 422."""
    response = client.patch(
        "/postmortems/test-id/verify",
        json={
            "confirmed_root_cause": "Root cause identified",
            "confirmed_fix": "",
            "verified_by": "user@example.com",
        },
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_verify_postmortem_whitespace_only_confirmed_fix(client):
    """PATCH /postmortems/{id}/verify with whitespace-only confirmed_fix should return 422."""
    response = client.patch(
        "/postmortems/test-id/verify",
        json={
            "confirmed_root_cause": "Root cause identified",
            "confirmed_fix": "  \t\n  ",
            "verified_by": "user@example.com",
        },
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_startup_missing_gemini_api_key():
    """_do_startup() should raise RuntimeError when GEMINI_API_KEY is missing."""
    from api.main import _do_startup

    with patch.dict("os.environ", {}, clear=True), \
         patch("api.main.get_redis_client"), \
         patch("api.main.get_client"), \
         patch("api.main.get_producer"):
        with pytest.raises(RuntimeError) as exc_info:
            _do_startup()
        assert "GEMINI_API_KEY environment variable is required" in str(exc_info.value)


def test_verify_postmortem_affected_services_string(client):
    """PATCH /postmortems/{id}/verify should handle affected_services as string."""
    pm = {
        "incident_id": "pm-service-string",
        "title": "Redis Cluster Failover",
        "severity": "high",
        "affected_services": "cache-service",  # string instead of list
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(pm)
    mock_redis.set.return_value = True

    mock_weaviate = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate.collections.get.return_value = mock_collection

    mock_genai_client = MagicMock()
    mock_result = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.4] * 768
    mock_result.embeddings = [mock_embedding]
    mock_genai_client.models.embed_content.return_value = mock_result

    with patch("api.main._redis_client", mock_redis), \
         patch("api.main._weaviate_client", mock_weaviate), \
         patch("api.main.genai.Client", return_value=mock_genai_client), \
         patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        response = client.patch(
            "/postmortems/pm-service-string/verify",
            json={
                "confirmed_root_cause": "Leader election failure",
                "confirmed_fix": "Restarted cluster with quorum",
                "verified_by": "sre@example.com",
            },
        )

    assert response.status_code == 200
    insert_args = mock_collection.data.insert.call_args
    assert insert_args[1]["properties"]["service"] == "cache-service"


def test_verify_postmortem_affected_services_empty_list(client):
    """PATCH /postmortems/{id}/verify should handle empty affected_services list."""
    pm = {
        "incident_id": "pm-service-empty",
        "title": "Network Latency Spike",
        "severity": "medium",
        "affected_services": [],
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(pm)
    mock_redis.set.return_value = True

    mock_weaviate = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate.collections.get.return_value = mock_collection

    mock_genai_client = MagicMock()
    mock_result = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.5] * 768
    mock_result.embeddings = [mock_embedding]
    mock_genai_client.models.embed_content.return_value = mock_result

    with patch("api.main._redis_client", mock_redis), \
         patch("api.main._weaviate_client", mock_weaviate), \
         patch("api.main.genai.Client", return_value=mock_genai_client), \
         patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        response = client.patch(
            "/postmortems/pm-service-empty/verify",
            json={
                "confirmed_root_cause": "ISP routing issue",
                "confirmed_fix": "Contacted ISP, issue resolved",
                "verified_by": "netops@example.com",
            },
        )

    assert response.status_code == 200
    insert_args = mock_collection.data.insert.call_args
    assert insert_args[1]["properties"]["service"] == "unknown"


def test_verify_postmortem_affected_services_missing(client):
    """PATCH /postmortems/{id}/verify should handle missing affected_services field."""
    pm = {
        "incident_id": "pm-service-missing",
        "title": "Disk Space Full",
        "severity": "critical",
        # affected_services field is missing
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(pm)
    mock_redis.set.return_value = True

    mock_weaviate = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate.collections.get.return_value = mock_collection

    mock_genai_client = MagicMock()
    mock_result = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.6] * 768
    mock_result.embeddings = [mock_embedding]
    mock_genai_client.models.embed_content.return_value = mock_result

    with patch("api.main._redis_client", mock_redis), \
         patch("api.main._weaviate_client", mock_weaviate), \
         patch("api.main.genai.Client", return_value=mock_genai_client), \
         patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        response = client.patch(
            "/postmortems/pm-service-missing/verify",
            json={
                "confirmed_root_cause": "Log rotation disabled",
                "confirmed_fix": "Enabled log rotation and cleared old logs",
                "verified_by": "sysadmin@example.com",
            },
        )

    assert response.status_code == 200
    insert_args = mock_collection.data.insert.call_args
    assert insert_args[1]["properties"]["service"] == "unknown"


# ============================
# Lifespan and shutdown tests
# ============================


def test_do_shutdown_consumer_thread_timeout():
    """_do_shutdown() should log warning when consumer thread doesn't stop within timeout."""
    from api.main import _do_shutdown, _stop_event
    import logging

    # Create a mock consumer thread that won't stop within timeout
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    mock_thread.join = MagicMock()

    mock_producer = MagicMock()
    mock_weaviate = MagicMock()
    mock_redis = MagicMock()

    with patch("api.main._consumer_thread", mock_thread), \
         patch("api.main._producer", mock_producer), \
         patch("api.main._weaviate_client", mock_weaviate), \
         patch("api.main._redis_client", mock_redis), \
         patch("api.main.logger") as mock_logger:
        
        _do_shutdown()
        
        # Verify stop event was set
        assert _stop_event.is_set()
        
        # Verify thread.join was called with timeout
        mock_thread.join.assert_called_once_with(timeout=5)
        
        # Verify warning was logged for thread that didn't terminate
        mock_logger.warning.assert_called_once_with("Consumer thread did not terminate within timeout")
        
        # Verify cleanup still happened for other resources
        mock_producer.flush.assert_called_once()
        mock_weaviate.close.assert_called_once()
        mock_redis.close.assert_called_once()


def test_do_shutdown_consumer_thread_stops_successfully():
    """_do_shutdown() should not log warning when consumer thread stops successfully."""
    from api.main import _do_shutdown, _stop_event
    
    # Create a mock consumer thread that stops successfully
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = False
    mock_thread.join = MagicMock()

    mock_producer = MagicMock()
    mock_weaviate = MagicMock()
    mock_redis = MagicMock()

    with patch("api.main._consumer_thread", mock_thread), \
         patch("api.main._producer", mock_producer), \
         patch("api.main._weaviate_client", mock_weaviate), \
         patch("api.main._redis_client", mock_redis), \
         patch("api.main.logger") as mock_logger:
        
        _do_shutdown()
        
        # Verify stop event was set
        assert _stop_event.is_set()
        
        # Verify thread.join was called with timeout
        mock_thread.join.assert_called_once_with(timeout=5)
        
        # Verify NO warning was logged (thread stopped successfully)
        mock_logger.warning.assert_not_called()
        
        # Verify cleanup still happened for other resources
        mock_producer.flush.assert_called_once()
        mock_weaviate.close.assert_called_once()
        mock_redis.close.assert_called_once()


def test_lifespan_context_manager():
    """lifespan context manager should call _do_startup on enter and _do_shutdown on exit."""
    from api.main import lifespan
    import asyncio
    
    async def run_lifespan():
        mock_app = MagicMock()
        
        with patch("api.main._do_startup") as mock_startup, \
             patch("api.main._do_shutdown") as mock_shutdown:
            
            # Enter the context manager
            async with lifespan(mock_app):
                # Verify startup was called
                mock_startup.assert_called_once()
                # Verify shutdown has not been called yet
                mock_shutdown.assert_not_called()
            
            # After exiting context, verify shutdown was called
            mock_shutdown.assert_called_once()
    
    # Run the async test
    asyncio.run(run_lifespan())
