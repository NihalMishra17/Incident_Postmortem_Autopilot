import pytest
from unittest.mock import MagicMock, patch
from agents.rca_agent import RCAAgent


@pytest.fixture
def rca_agent():
    """Create RCAAgent with mocked DSPy dependencies."""
    with patch("agents.rca_agent.dspy.LM") as mock_lm:
        with patch("agents.rca_agent.dspy.configure"):
            with patch("agents.rca_agent.RCAModule") as mock_module_class:
                mock_module = MagicMock()
                mock_module_class.return_value = mock_module

                agent = RCAAgent()
                agent.module = mock_module
                yield agent


def test_rca_result_populated(rca_agent):
    """Should populate rca_result from DSPy forward call."""
    mock_result = MagicMock()
    mock_result.root_cause_analysis = "Root cause: Database connection pool exhausted due to sudden traffic spike. The connection pool was configured with a max size of 10, which was insufficient for peak load."
    rca_agent.module.return_value = mock_result

    alert = {
        "alert_id": "123",
        "service": "api-gateway",
        "message": "high latency",
        "blast_radius": ["payment-service", "notification-service"],
        "correlated_incidents": [
            {"title": "Similar latency issue", "root_cause": "Connection timeout"}
        ],
    }
    result = rca_agent.process(alert)

    assert "rca_result" in result
    assert "Database connection pool exhausted" in result["rca_result"]
    assert result["alert_id"] == "123"

    rca_agent.module.assert_called_once()
    call_kwargs = rca_agent.module.call_args[1]
    assert "service=api-gateway" in call_kwargs["alert_data"]
    assert "payment-service, notification-service" == call_kwargs["blast_radius"]


def test_rca_fallback_on_failure(rca_agent):
    """Should return fallback string when DSPy fails without crashing."""
    rca_agent.module.side_effect = Exception("Model timeout")

    alert = {
        "alert_id": "456",
        "service": "database",
        "message": "connection timeout",
        "blast_radius": [],
        "correlated_incidents": [],
    }
    result = rca_agent.process(alert)

    assert "rca_result" in result
    assert "RCA unavailable" in result["rca_result"]
    assert "Model timeout" not in result["rca_result"]  # internal error must not leak
    assert result["alert_id"] == "456"


def test_original_fields_preserved(rca_agent):
    """Output dict should contain all input keys."""
    mock_result = MagicMock()
    mock_result.root_cause_analysis = "Analysis result"
    rca_agent.module.return_value = mock_result

    alert = {
        "alert_id": "789",
        "service": "cache",
        "message": "memory pressure",
        "severity": "P2",
        "severity_level": "high",
        "blast_radius": ["worker-service"],
        "correlated_incidents": [{"title": "Memory leak"}],
        "timestamp": "2026-06-02T10:00:00Z",
        "custom_metadata": {"region": "us-west-2"},
    }
    result = rca_agent.process(alert)

    for key in alert:
        assert key in result
        assert result[key] == alert[key]
    assert "rca_result" in result
