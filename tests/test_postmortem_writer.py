import pytest
from unittest.mock import MagicMock, patch, call
from agents.postmortem_writer import PostmortemWriter


@pytest.fixture
def postmortem_writer(mock_kafka_producer):
    """Create PostmortemWriter with mocked dependencies."""
    with patch("agents.postmortem_writer.get_producer", return_value=mock_kafka_producer):
        with patch("agents.postmortem_writer.dspy.Predict") as mock_predict_class:
            mock_predictor = MagicMock()
            mock_predict_class.return_value = mock_predictor

            writer = PostmortemWriter()
            writer.predictor = mock_predictor
            yield writer


def test_postmortem_fields_present(postmortem_writer, mock_kafka_producer):
    """Should return postmortem with all required fields."""
    mock_result = MagicMock()
    mock_result.title = "API Gateway Latency Spike"
    mock_result.root_cause = "Database connection pool exhausted during peak traffic"
    mock_result.timeline = "- 10:00 AM: Alert triggered\n- 10:05 AM: Investigation started\n- 10:15 AM: Root cause identified"
    mock_result.remediation = "Scaled up connection pool size from 10 to 50"
    mock_result.prevention = "Implement auto-scaling for connection pools based on traffic patterns"
    postmortem_writer.predictor.return_value = mock_result

    alert = {
        "alert_id": "test-123",
        "service": "api-gateway",
        "message": "high latency detected",
        "severity_level": "critical",
        "blast_radius": ["payment-service", "notification-service"],
        "rca_result": "Connection pool exhausted",
        "correlated_incidents": [{"title": "Previous latency issue"}],
    }
    result = postmortem_writer.process(alert)

    assert result["incident_id"] == "test-123"
    assert result["title"] == "API Gateway Latency Spike"
    assert result["severity"] == "critical"
    assert result["affected_services"] == ["payment-service", "notification-service"]
    assert result["root_cause"] == "Database connection pool exhausted during peak traffic"
    assert result["timeline"] == "- 10:00 AM: Alert triggered\n- 10:05 AM: Investigation started\n- 10:15 AM: Root cause identified"
    assert result["remediation"] == "Scaled up connection pool size from 10 to 50"
    assert result["prevention"] == "Implement auto-scaling for connection pools based on traffic patterns"
    assert "generated_at" in result


def test_kafka_flush_called(postmortem_writer, mock_kafka_producer):
    """Should call producer.flush() after produce."""
    mock_result = MagicMock()
    mock_result.title = "Test Incident"
    mock_result.root_cause = "Test cause"
    mock_result.timeline = "Test timeline"
    mock_result.remediation = "Test remediation"
    mock_result.prevention = "Test prevention"
    postmortem_writer.predictor.return_value = mock_result

    alert = {
        "alert_id": "456",
        "service": "database",
        "message": "connection timeout",
        "severity_level": "high",
        "blast_radius": [],
        "rca_result": "Network issue",
        "correlated_incidents": [],
    }
    postmortem_writer.process(alert)

    mock_kafka_producer.flush.assert_called_once()

    assert mock_kafka_producer.produce.called or mock_kafka_producer.send.called


def test_incident_id_from_alert(postmortem_writer, mock_kafka_producer):
    """Should use alert's alert_id as incident_id in output."""
    mock_result = MagicMock()
    mock_result.title = "Cache Memory Pressure"
    mock_result.root_cause = "Memory leak in cache implementation"
    mock_result.timeline = "Timeline"
    mock_result.remediation = "Restarted cache service"
    mock_result.prevention = "Add memory monitoring"
    postmortem_writer.predictor.return_value = mock_result

    alert = {
        "alert_id": "unique-alert-789",
        "service": "cache",
        "message": "memory pressure",
        "severity_level": "medium",
        "blast_radius": ["worker-service"],
        "rca_result": "Memory leak detected",
        "correlated_incidents": [],
    }
    result = postmortem_writer.process(alert)

    assert result["incident_id"] == "unique-alert-789"


def test_dspy_predictor_called_with_correct_args(postmortem_writer, mock_kafka_producer):
    """Should call DSPy predictor with formatted inputs."""
    mock_result = MagicMock()
    mock_result.title = "Test"
    mock_result.root_cause = "Test"
    mock_result.timeline = "Test"
    mock_result.remediation = "Test"
    mock_result.prevention = "Test"
    postmortem_writer.predictor.return_value = mock_result

    alert = {
        "alert_id": "999",
        "service": "api-gateway",
        "message": "high error rate",
        "severity_level": "critical",
        "blast_radius": ["auth-service", "payment-service"],
        "rca_result": "Database deadlock",
        "correlated_incidents": [{"title": "Deadlock incident"}],
    }
    postmortem_writer.process(alert)

    postmortem_writer.predictor.assert_called_once()
    call_kwargs = postmortem_writer.predictor.call_args[1]

    assert "service=api-gateway" in call_kwargs["alert_data"]
    assert "message=high error rate" in call_kwargs["alert_data"]
    assert call_kwargs["blast_radius"] == "auth-service, payment-service"
    assert call_kwargs["rca_result"] == "Database deadlock"
    assert "Deadlock incident" in str(call_kwargs["correlated_incidents"])
