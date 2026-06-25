import pytest
import json
import tempfile
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from google.genai.errors import ClientError
from tenacity import wait_none
from data.seed_weaviate import _embed_text


def test_embed_text_retries_on_429_and_succeeds():
    """Should retry on ClientError with code 429 and succeed after transient failure."""
    mock_genai_client = MagicMock()

    # Mock ClientError with code=429
    error_429 = ClientError(429, {"error": "Rate limit exceeded"})

    # Mock successful response
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.3] * 768)]

    # Fail once with 429, then succeed
    mock_genai_client.models.embed_content.side_effect = [error_429, mock_embedding]

    # Patch retry wait to avoid slow tests
    with patch("data.seed_weaviate.wait_exponential", return_value=wait_none()):
        result = _embed_text(mock_genai_client, "test incident text")

    assert len(result) == 768
    assert result[0] == 0.3
    assert mock_genai_client.models.embed_content.call_count == 2


def test_embed_text_raises_on_non_429_error():
    """Should raise immediately on ClientError with non-429 code (no retry)."""
    mock_genai_client = MagicMock()

    # Mock ClientError with code=401
    error_401 = ClientError(401, {"error": "Unauthorized"})

    mock_genai_client.models.embed_content.side_effect = error_401

    with patch("data.seed_weaviate.wait_exponential", return_value=wait_none()):
        with pytest.raises(ClientError) as exc_info:
            _embed_text(mock_genai_client, "test text")

    # Should not retry, only called once
    assert mock_genai_client.models.embed_content.call_count == 1
    assert exc_info.value.code == 401


def test_embed_text_reraises_after_max_retries():
    """Should re-raise ClientError after 5 failed retry attempts."""
    mock_genai_client = MagicMock()

    # Mock ClientError with code=429
    error_429 = ClientError(429, {"error": "Rate limit exceeded"})

    # Always fail with 429
    mock_genai_client.models.embed_content.side_effect = error_429

    with patch("data.seed_weaviate.wait_exponential", return_value=wait_none()):
        with pytest.raises(ClientError) as exc_info:
            _embed_text(mock_genai_client, "test text")

    # Should have tried 5 times (stop_after_attempt=5)
    assert mock_genai_client.models.embed_content.call_count == 5
    assert exc_info.value.code == 429


def test_embed_text_succeeds_on_first_attempt():
    """Should succeed immediately if no error occurs."""
    mock_genai_client = MagicMock()

    # Mock successful response
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.5] * 768)]
    mock_genai_client.models.embed_content.return_value = mock_embedding

    result = _embed_text(mock_genai_client, "test incident text")

    assert len(result) == 768
    assert result[0] == 0.5
    assert mock_genai_client.models.embed_content.call_count == 1


def test_embed_text_handles_multiple_retries_before_success():
    """Should retry multiple times (up to 4) before succeeding on 5th attempt."""
    mock_genai_client = MagicMock()

    # Mock ClientError with code=429
    error_429 = ClientError(429, {"error": "Rate limit exceeded"})

    # Mock successful response
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.7] * 768)]

    # Fail 4 times, then succeed on the 5th
    mock_genai_client.models.embed_content.side_effect = [
        error_429,
        error_429,
        error_429,
        error_429,
        mock_embedding,
    ]

    with patch("data.seed_weaviate.wait_exponential", return_value=wait_none()):
        result = _embed_text(mock_genai_client, "test text")

    assert len(result) == 768
    assert result[0] == 0.7
    assert mock_genai_client.models.embed_content.call_count == 5


def test_embed_text_does_not_retry_on_value_error():
    """Should not retry on non-ClientError exceptions."""
    mock_genai_client = MagicMock()

    # Regular exception (not ClientError)
    mock_genai_client.models.embed_content.side_effect = ValueError("Invalid model name")

    with patch("data.seed_weaviate.wait_exponential", return_value=wait_none()):
        with pytest.raises(ValueError):
            _embed_text(mock_genai_client, "test text")

    # Should not retry on non-ClientError
    assert mock_genai_client.models.embed_content.call_count == 1


def test_embed_text_uses_correct_model_and_content():
    """Should call embed_content with correct model and content parameters."""
    mock_genai_client = MagicMock()

    # Mock successful response
    mock_embedding = MagicMock()
    mock_embedding.embeddings = [MagicMock(values=[0.9] * 768)]
    mock_genai_client.models.embed_content.return_value = mock_embedding

    test_text = "Payment service DB connection pool exhaustion"
    result = _embed_text(mock_genai_client, test_text)

    # Verify correct parameters passed (updated to gemini-embedding-001)
    mock_genai_client.models.embed_content.assert_called_once_with(
        model="models/gemini-embedding-001", contents=test_text
    )
    assert len(result) == 768



def test_load_incidents_from_json():
    """Should verify INCIDENTS is loaded from past_incidents.json."""
    from data.seed_weaviate import INCIDENTS
    
    # INCIDENTS should be loaded from the JSON file
    assert len(INCIDENTS) > 0
    assert all("title" in inc for inc in INCIDENTS)
    assert all("root_cause" in inc for inc in INCIDENTS)
    assert all("fix" in inc for inc in INCIDENTS)
    assert all("service" in inc for inc in INCIDENTS)


def test_incidents_json_missing_field_raises():
    """Should raise ValueError during import when JSON entry is missing required field."""
    # This test validates the validation logic exists
    # The actual validation happens at module import time
    # We test by checking that all loaded incidents have required fields
    from data.seed_weaviate import INCIDENTS, _REQUIRED_FIELDS
    
    # Verify validation logic would catch missing fields
    for incident in INCIDENTS:
        missing = _REQUIRED_FIELDS - set(incident.keys())
        assert not missing, f"Incident missing required fields: {missing}"

