import pytest
from unittest.mock import MagicMock, patch
from agents.correlation_agent import CorrelationAgent
from google.genai.errors import ClientError
from tenacity import wait_none


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


def test_embed_query_retries_on_429_and_succeeds(correlation_agent):
    """Should retry on ClientError with code 429 and succeed after transient failure."""
    # Mock ClientError with code=429
    error_429 = ClientError(429, {"error": "Rate limit exceeded"})

    # Mock successful response
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.1] * 768)]

    # Fail twice with 429, then succeed
    correlation_agent.genai_client.models.embed_content.side_effect = [
        error_429,
        error_429,
        mock_embedding,
    ]

    # Patch retry wait to avoid slow tests
    with patch("agents.correlation_agent.wait_exponential", return_value=wait_none()):
        result = correlation_agent._embed_query("test query")

    assert len(result) == 768
    assert result[0] == 0.1
    assert correlation_agent.genai_client.models.embed_content.call_count == 3


def test_embed_query_raises_on_non_429_error(correlation_agent):
    """Should raise immediately on ClientError with non-429 code (no retry)."""
    # Mock ClientError with code=400
    error_400 = ClientError(400, {"error": "Bad request"})

    correlation_agent.genai_client.models.embed_content.side_effect = error_400

    with patch("agents.correlation_agent.wait_exponential", return_value=wait_none()):
        with pytest.raises(ClientError) as exc_info:
            correlation_agent._embed_query("test query")

    # Should not retry, only called once
    assert correlation_agent.genai_client.models.embed_content.call_count == 1
    assert exc_info.value.code == 400


def test_embed_query_reraises_after_max_retries(correlation_agent):
    """Should re-raise ClientError after 5 failed retry attempts."""
    # Mock ClientError with code=429
    error_429 = ClientError(429, {"error": "Rate limit exceeded"})

    # Always fail with 429
    correlation_agent.genai_client.models.embed_content.side_effect = error_429

    with patch("agents.correlation_agent.wait_exponential", return_value=wait_none()):
        with pytest.raises(ClientError) as exc_info:
            correlation_agent._embed_query("test query")

    # Should have tried 5 times (stop_after_attempt=5)
    assert correlation_agent.genai_client.models.embed_content.call_count == 5
    assert exc_info.value.code == 429


def test_process_uses_embed_query_with_retry(correlation_agent):
    """Integration test: process() should use _embed_query with retry logic."""
    # Mock ClientError with code=429
    error_429 = ClientError(429, {"error": "Rate limit exceeded"})

    # Mock successful response after one retry
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.2] * 768)]

    correlation_agent.genai_client.models.embed_content.side_effect = [
        error_429,
        mock_embedding,
    ]

    # Mock Weaviate response
    mock_obj = MagicMock()
    mock_obj.properties = {
        "title": "Test incident",
        "root_cause": "Test cause",
        "fix": "Test fix",
        "service": "test-service",
    }
    mock_response = MagicMock()
    mock_response.objects = [mock_obj]
    correlation_agent.collection.query.near_vector.return_value = mock_response

    alert = {"service": "test-service", "message": "test error"}

    with patch("agents.correlation_agent.wait_exponential", return_value=wait_none()):
        result = correlation_agent.process(alert)

    assert len(result["correlated_incidents"]) == 1
    assert result["correlated_incidents"][0]["title"] == "Test incident"
    assert correlation_agent.genai_client.models.embed_content.call_count == 2


def test_embed_query_handles_other_exceptions(correlation_agent):
    """Should not retry on non-ClientError exceptions."""
    # Regular exception (not ClientError)
    correlation_agent.genai_client.models.embed_content.side_effect = ValueError("Invalid input")

    with patch("agents.correlation_agent.wait_exponential", return_value=wait_none()):
        with pytest.raises(ValueError):
            correlation_agent._embed_query("test query")

    # Should not retry on non-ClientError
    assert correlation_agent.genai_client.models.embed_content.call_count == 1
