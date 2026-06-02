import pytest
from unittest.mock import MagicMock, patch
from agents.triage_agent import TriageAgent


@pytest.fixture
def triage_agent(mock_neo4j_driver):
    """Create TriageAgent with mocked Neo4j driver."""
    with patch("agents.triage_agent.get_driver", return_value=mock_neo4j_driver):
        agent = TriageAgent()
        yield agent


def test_severity_mapping_p1(triage_agent, mock_neo4j_driver):
    """P1 alert should map to critical severity."""
    mock_neo4j_driver.session().__enter__().run.return_value = []

    alert = {"alert_id": "123", "severity": "P1", "service": "api-gateway"}
    result = triage_agent.process(alert)

    assert result["severity_level"] == "critical"
    assert result["alert_id"] == "123"


def test_severity_mapping_p2(triage_agent, mock_neo4j_driver):
    """P2 alert should map to high severity."""
    mock_neo4j_driver.session().__enter__().run.return_value = []

    alert = {"alert_id": "456", "severity": "P2", "service": "database"}
    result = triage_agent.process(alert)

    assert result["severity_level"] == "high"


def test_severity_mapping_p3(triage_agent, mock_neo4j_driver):
    """P3 alert should map to medium severity."""
    mock_neo4j_driver.session().__enter__().run.return_value = []

    alert = {"alert_id": "789", "severity": "P3", "service": "cache"}
    result = triage_agent.process(alert)

    assert result["severity_level"] == "medium"


def test_severity_mapping_unknown(triage_agent, mock_neo4j_driver):
    """Missing or unknown severity should map to low."""
    mock_neo4j_driver.session().__enter__().run.return_value = []

    alert = {"alert_id": "999", "service": "worker"}
    result = triage_agent.process(alert)

    assert result["severity_level"] == "low"

    alert_invalid = {"alert_id": "1000", "severity": "P5", "service": "worker"}
    result_invalid = triage_agent.process(alert_invalid)

    assert result_invalid["severity_level"] == "low"


def test_blast_radius_returned(triage_agent, mock_neo4j_driver):
    """Should return blast radius from Neo4j query."""
    mock_records = [
        {"name": "payment-service"},
        {"name": "notification-service"},
    ]
    mock_neo4j_driver.session().__enter__().run.return_value = mock_records

    alert = {"alert_id": "123", "severity": "P1", "service": "api-gateway"}
    result = triage_agent.process(alert)

    assert result["blast_radius"] == ["payment-service", "notification-service"]
    assert len(result["blast_radius"]) == 2


def test_blast_radius_neo4j_failure(triage_agent, mock_neo4j_driver):
    """Should return empty blast_radius when Neo4j fails without crashing."""
    mock_neo4j_driver.session().__enter__().run.side_effect = Exception("Connection timeout")

    alert = {"alert_id": "123", "severity": "P1", "service": "api-gateway"}
    result = triage_agent.process(alert)

    assert result["blast_radius"] == []
    assert result["severity_level"] == "critical"


def test_original_alert_fields_preserved(triage_agent, mock_neo4j_driver):
    """Output dict should contain all original alert keys."""
    mock_neo4j_driver.session().__enter__().run.return_value = []

    alert = {
        "alert_id": "123",
        "severity": "P1",
        "service": "api-gateway",
        "message": "High latency detected",
        "timestamp": "2026-06-02T10:00:00Z",
        "custom_field": "custom_value",
    }
    result = triage_agent.process(alert)

    for key in alert:
        assert key in result
        assert result[key] == alert[key]
    assert "severity_level" in result
    assert "blast_radius" in result
