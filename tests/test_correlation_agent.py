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


def test_process_batch_multiple_alerts(correlation_agent):
    """Should process multiple alerts in batch and return list of enriched dicts."""
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.1] * 768)]
    correlation_agent.genai_client.models.embed_content.return_value = mock_embedding

    mock_obj = MagicMock()
    mock_obj.properties = {
        "title": "Past incident",
        "root_cause": "Root cause",
        "fix": "Fix applied",
        "service": "database",
    }

    mock_response = MagicMock()
    mock_response.objects = [mock_obj]
    correlation_agent.collection.query.near_vector.return_value = mock_response

    alerts = [
        {"alert_id": "1", "service": "database", "message": "error 1"},
        {"alert_id": "2", "service": "api-gateway", "message": "error 2"},
    ]
    results = correlation_agent.process_batch(alerts)

    assert len(results) == 2
    assert results[0]["alert_id"] == "1"
    assert results[1]["alert_id"] == "2"
    assert "correlated_incidents" in results[0]
    assert "correlated_incidents" in results[1]
    # Both alerts get the same correlated incidents since we batch the query
    assert results[0]["correlated_incidents"] == results[1]["correlated_incidents"]


def test_process_single_alert_backward_compat(correlation_agent):
    """Should verify process(alert) shim returns a single dict, not a list."""
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.1] * 768)]
    correlation_agent.genai_client.models.embed_content.return_value = mock_embedding

    mock_response = MagicMock()
    mock_response.objects = []
    correlation_agent.collection.query.near_vector.return_value = mock_response

    alert = {"alert_id": "123", "service": "api-gateway", "message": "latency spike"}
    result = correlation_agent.process(alert)

    # Should return dict, not list
    assert isinstance(result, dict)
    assert not isinstance(result, list)
    assert result["alert_id"] == "123"
    assert "correlated_incidents" in result


def test_dedup_removes_exact_duplicate_fix(mock_weaviate_client):
    """Should remove exact duplicate fix text and return only 3 unique results."""
    mock_genai_client = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate_client.collections.get.return_value = mock_collection

    with patch("agents.correlation_agent.genai.Client", return_value=mock_genai_client):
        with patch("agents.correlation_agent.get_client", return_value=mock_weaviate_client):
            agent = CorrelationAgent()

    incidents = [
        {"title": "Incident 1", "fix": "Increased pool size from 10 to 50"},
        {"title": "Incident 2", "fix": "Added connection timeout logic"},
        {"title": "Incident 3", "fix": "Increased pool size from 10 to 50"},  # duplicate
        {"title": "Incident 4", "fix": "Configured retry backoff"},
    ]

    result = agent._deduplicate_fixes(incidents)

    assert len(result) == 3
    # First unique instance kept
    assert result[0]["title"] == "Incident 1"
    assert result[1]["title"] == "Incident 2"
    # Incident 3 skipped (duplicate of Incident 1)
    assert result[2]["title"] == "Incident 4"


def test_dedup_removes_near_duplicate_fix(mock_weaviate_client):
    """Should remove fixes with >85% Jaccard similarity and return 3 unique results."""
    mock_genai_client = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate_client.collections.get.return_value = mock_collection

    with patch("agents.correlation_agent.genai.Client", return_value=mock_genai_client):
        with patch("agents.correlation_agent.get_client", return_value=mock_weaviate_client):
            agent = CorrelationAgent()

    incidents = [
        {"title": "Inc1", "fix": "increased pool size timeout logic cache retry"},
        {"title": "Inc2", "fix": "Configured rate limiting"},
        {"title": "Inc3", "fix": "increased pool size timeout logic cache"},  # >85% similar to Inc1
        {"title": "Inc4", "fix": "Implemented circuit breaker pattern"},
    ]
    result = agent._deduplicate_fixes(incidents)

    assert len(result) == 3
    assert result[0]["title"] == "Inc1"
    assert result[1]["title"] == "Inc2"
    # Inc3 skipped (near duplicate of Inc1)
    assert result[2]["title"] == "Inc4"


def test_dedup_no_duplicates(mock_weaviate_client):
    """Should return all 3 incidents when fixes are completely different."""
    mock_genai_client = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate_client.collections.get.return_value = mock_collection

    with patch("agents.correlation_agent.genai.Client", return_value=mock_genai_client):
        with patch("agents.correlation_agent.get_client", return_value=mock_weaviate_client):
            agent = CorrelationAgent()

    incidents = [
        {"title": "Inc1", "fix": "Increased pool size"},
        {"title": "Inc2", "fix": "Added circuit breaker"},
        {"title": "Inc3", "fix": "Configured rate limiting"},
    ]

    result = agent._deduplicate_fixes(incidents)

    assert len(result) == 3
    assert result[0]["title"] == "Inc1"
    assert result[1]["title"] == "Inc2"
    assert result[2]["title"] == "Inc3"


def test_dedup_returns_fewer_than_3_when_not_enough_unique(mock_weaviate_client):
    """Should return only 2 results when 10 incidents have only 2 unique fixes."""
    mock_genai_client = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate_client.collections.get.return_value = mock_collection

    with patch("agents.correlation_agent.genai.Client", return_value=mock_genai_client):
        with patch("agents.correlation_agent.get_client", return_value=mock_weaviate_client):
            agent = CorrelationAgent()

    incidents = [
        {"title": "Inc1", "fix": "Increased connection pool size"},
        {"title": "Inc2", "fix": "Added LRU cache with TTL"},
        {"title": "Inc3", "fix": "Increased connection pool size"},  # duplicate
        {"title": "Inc4", "fix": "Added LRU cache with TTL"},  # duplicate
        {"title": "Inc5", "fix": "Increased connection pool size"},  # duplicate
        {"title": "Inc6", "fix": "Added LRU cache with TTL"},  # duplicate
        {"title": "Inc7", "fix": "Increased connection pool size"},  # duplicate
        {"title": "Inc8", "fix": "Added LRU cache with TTL"},  # duplicate
        {"title": "Inc9", "fix": "Increased connection pool size"},  # duplicate
        {"title": "Inc10", "fix": "Added LRU cache with TTL"},  # duplicate
    ]

    result = agent._deduplicate_fixes(incidents)

    assert len(result) == 2
    assert result[0]["fix"] == "Increased connection pool size"
    assert result[1]["fix"] == "Added LRU cache with TTL"


def test_dedup_handles_empty_fix(mock_weaviate_client):
    """Should handle empty string fix without crashing; empty strings deduplicate."""
    mock_genai_client = MagicMock()
    mock_collection = MagicMock()
    mock_weaviate_client.collections.get.return_value = mock_collection

    with patch("agents.correlation_agent.genai.Client", return_value=mock_genai_client):
        with patch("agents.correlation_agent.get_client", return_value=mock_weaviate_client):
            agent = CorrelationAgent()

    incidents = [
        {"title": "Inc1", "fix": ""},
        {"title": "Inc2", "fix": "Added connection timeout"},
        {"title": "Inc3", "fix": ""},  # duplicate empty
        {"title": "Inc4", "fix": "Configured retry logic"},
    ]

    result = agent._deduplicate_fixes(incidents)

    assert len(result) == 3
    assert result[0]["fix"] == ""
    assert result[1]["fix"] == "Added connection timeout"
    # Inc3 skipped (duplicate empty)
    assert result[2]["fix"] == "Configured retry logic"
