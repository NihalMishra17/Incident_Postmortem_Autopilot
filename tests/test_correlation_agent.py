import pytest
from unittest.mock import MagicMock, patch
from agents.correlation_agent import CorrelationAgent


@pytest.fixture
def correlation_agent(mock_weaviate_client):
    """Create CorrelationAgent with mocked dependencies."""
    mock_genai_client = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate_client.collections.get.return_value = mock_collection

    with patch("agents.correlation_agent.genai.Client", return_value=mock_genai_client):
        with patch("agents.correlation_agent.get_client", return_value=mock_weaviate_client):
            agent = CorrelationAgent()
            agent.genai_client = mock_genai_client
            agent.collection = mock_collection
            yield agent


def test_returns_correlated_incidents(correlation_agent):
    """Should return correlated incidents from Weaviate."""
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.1] * 768)]
    correlation_agent.genai_client.models.embed_content.return_value = mock_embedding

    mock_obj1 = MagicMock()
    mock_obj1.properties = {
        "title": "Database connection pool exhausted",
        "root_cause": "Too many concurrent connections",
        "fix": "Increased pool size",
        "service": "database",
    }
    mock_obj2 = MagicMock()
    mock_obj2.properties = {
        "title": "Connection timeout",
        "root_cause": "Network latency spike",
        "fix": "Adjusted timeout settings",
        "service": "api-gateway",
    }

    mock_response = MagicMock()
    mock_response.objects = [mock_obj1, mock_obj2]
    correlation_agent.collection.query.near_vector.return_value = mock_response

    alert = {"service": "database", "message": "connection pool exhausted"}
    result = correlation_agent.process(alert)

    assert len(result["correlated_incidents"]) == 2
    assert result["correlated_incidents"][0]["title"] == "Database connection pool exhausted"
    assert result["correlated_incidents"][1]["title"] == "Connection timeout"


def test_empty_when_no_results(correlation_agent):
    """Should return empty list when Weaviate returns no results."""
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.1] * 768)]
    correlation_agent.genai_client.models.embed_content.return_value = mock_embedding

    mock_response = MagicMock()
    mock_response.objects = []
    correlation_agent.collection.query.near_vector.return_value = mock_response

    alert = {"service": "unknown-service", "message": "unique error"}
    result = correlation_agent.process(alert)

    assert result["correlated_incidents"] == []


def test_handles_embed_failure(correlation_agent):
    """Should return empty list when Gemini embed fails without crashing."""
    correlation_agent.genai_client.models.embed_content.side_effect = Exception("API timeout")

    alert = {"service": "api-gateway", "message": "high latency"}
    result = correlation_agent.process(alert)

    assert result["correlated_incidents"] == []
    assert "service" in result
    assert "message" in result


def test_original_fields_preserved(correlation_agent):
    """Output dict should contain all input keys."""
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.1] * 768)]
    correlation_agent.genai_client.models.embed_content.return_value = mock_embedding

    mock_response = MagicMock()
    mock_response.objects = []
    correlation_agent.collection.query.near_vector.return_value = mock_response

    alert = {
        "alert_id": "123",
        "service": "api-gateway",
        "message": "latency spike",
        "severity": "P1",
        "timestamp": "2026-06-02T10:00:00Z",
        "severity_level": "critical",
        "blast_radius": ["payment-service"],
    }
    result = correlation_agent.process(alert)

    for key in alert:
        assert key in result
        assert result[key] == alert[key]
    assert "correlated_incidents" in result
