import pytest
from unittest.mock import MagicMock, patch, call
from agents.postmortem_writer import PostmortemWriter, FixCandidate


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer for testing."""
    return MagicMock()


@pytest.fixture
def mock_weaviate_client():
    """Mock Weaviate client for testing."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.collections.get.return_value = mock_collection
    return mock_client


@pytest.fixture
def mock_genai_client():
    """Mock Google GenAI client for testing."""
    return MagicMock()


@pytest.fixture
def postmortem_writer(mock_kafka_producer, mock_weaviate_client, mock_genai_client):
    """Create PostmortemWriter with mocked dependencies."""
    with patch("agents.postmortem_writer.get_producer", return_value=mock_kafka_producer):
        with patch("agents.postmortem_writer.get_client", return_value=mock_weaviate_client):
            with patch("agents.postmortem_writer.genai.Client", return_value=mock_genai_client):
                with patch("agents.postmortem_writer.dspy.Predict") as mock_predict_class:
                    mock_predictor = MagicMock()
                    mock_predict_class.return_value = mock_predictor

                    writer = PostmortemWriter()
                    writer.predictor = mock_predictor
                    yield writer


def test_postmortem_fields_present(postmortem_writer, mock_kafka_producer):
    """Should return postmortem with all required fields including suggested_fixes."""
    mock_result = MagicMock()
    mock_result.title = "API Gateway Latency Spike"
    mock_result.root_cause = "Database connection pool exhausted during peak traffic"
    mock_result.timeline = "- 10:00 AM: Alert triggered\n- 10:05 AM: Investigation started\n- 10:15 AM: Root cause identified"
    mock_result.remediation = "Scaled up connection pool size from 10 to 50"
    mock_result.prevention = "Implement auto-scaling for connection pools based on traffic patterns"
    postmortem_writer.predictor.return_value = mock_result

    # Mock _rank_fixes_from_weaviate to return fixed candidates
    mock_fixes = [
        FixCandidate(fix="Increase connection pool size", confidence=0.85, reasoning="Test reasoning 1"),
        FixCandidate(fix="Add connection timeout", confidence=0.70, reasoning="Test reasoning 2"),
        FixCandidate(fix="Monitor pool metrics", confidence=0.60, reasoning="Test reasoning 3"),
    ]
    with patch.object(postmortem_writer, '_rank_fixes_from_weaviate', return_value=mock_fixes):
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
    assert "suggested_fixes" in result
    assert len(result["suggested_fixes"]) == 3
    assert result["suggested_fixes"][0]["fix"] == "Increase connection pool size"
    assert result["suggested_fixes"][0]["confidence"] == 0.85


def test_kafka_flush_called(postmortem_writer, mock_kafka_producer):
    """Should call producer.flush() after produce."""
    mock_result = MagicMock()
    mock_result.title = "Test Incident"
    mock_result.root_cause = "Test cause"
    mock_result.timeline = "Test timeline"
    mock_result.remediation = "Test remediation"
    mock_result.prevention = "Test prevention"
    postmortem_writer.predictor.return_value = mock_result

    mock_fixes = [
        FixCandidate(fix="Fix 1", confidence=0.5, reasoning="Reason 1"),
        FixCandidate(fix="Fix 2", confidence=0.4, reasoning="Reason 2"),
        FixCandidate(fix="Fix 3", confidence=0.3, reasoning="Reason 3"),
    ]
    with patch.object(postmortem_writer, '_rank_fixes_from_weaviate', return_value=mock_fixes):
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

    mock_fixes = [
        FixCandidate(fix="Fix 1", confidence=0.5, reasoning="Reason 1"),
        FixCandidate(fix="Fix 2", confidence=0.4, reasoning="Reason 2"),
        FixCandidate(fix="Fix 3", confidence=0.3, reasoning="Reason 3"),
    ]
    with patch.object(postmortem_writer, '_rank_fixes_from_weaviate', return_value=mock_fixes):
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

    mock_fixes = [
        FixCandidate(fix="Fix 1", confidence=0.5, reasoning="Reason 1"),
        FixCandidate(fix="Fix 2", confidence=0.4, reasoning="Reason 2"),
        FixCandidate(fix="Fix 3", confidence=0.3, reasoning="Reason 3"),
    ]
    with patch.object(postmortem_writer, '_rank_fixes_from_weaviate', return_value=mock_fixes):
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


def test_fix_candidate_model():
    """Test FixCandidate Pydantic model."""
    fix = FixCandidate(
        fix="Increase connection pool size",
        confidence=0.85,
        reasoning="Similar to previous incident with connection pool exhaustion"
    )

    assert fix.fix == "Increase connection pool size"
    assert fix.confidence == 0.85
    assert fix.reasoning == "Similar to previous incident with connection pool exhaustion"

    # Test model_dump
    dumped = fix.model_dump()
    assert dumped["fix"] == "Increase connection pool size"
    assert dumped["confidence"] == 0.85
    assert dumped["reasoning"] == "Similar to previous incident with connection pool exhaustion"


def test_rank_fixes_from_weaviate_success(postmortem_writer, mock_weaviate_client, mock_genai_client):
    """Test successful fix ranking from Weaviate."""
    # Mock embedding response
    mock_embed_response = MagicMock()
    mock_embed_response.embeddings = [MagicMock(values=[0.1] * 768)]
    mock_genai_client.models.embed_content.return_value = mock_embed_response

    # Mock Weaviate query results
    mock_obj1 = MagicMock()
    mock_obj1.metadata.distance = 0.2
    mock_obj1.properties = {
        "fix": "Increase connection pool size",
        "title": "Database Connection Pool Exhaustion",
        "root_cause": "Pool size too small for traffic"
    }

    mock_obj2 = MagicMock()
    mock_obj2.metadata.distance = 0.4
    mock_obj2.properties = {
        "fix": "Add connection timeout configuration",
        "title": "Connection Timeout Issue",
        "root_cause": "No timeout configured"
    }

    mock_obj3 = MagicMock()
    mock_obj3.metadata.distance = 0.6
    mock_obj3.properties = {
        "fix": "Monitor connection pool metrics",
        "title": "Connection Pool Monitoring Gap",
        "root_cause": "No visibility into pool usage"
    }

    mock_collection = postmortem_writer.weaviate_collection
    mock_collection.query.near_vector.return_value.objects = [mock_obj1, mock_obj2, mock_obj3]

    root_cause = "Database connection pool exhausted"
    result = postmortem_writer._rank_fixes_from_weaviate(root_cause)

    assert len(result) == 3
    assert result[0].fix == "Increase connection pool size"
    assert result[0].confidence == 0.9  # 1.0 - (0.2 / 2.0)
    assert "Similar to: Database Connection Pool Exhaustion" in result[0].reasoning

    assert result[1].confidence == 0.8  # 1.0 - (0.4 / 2.0)
    assert result[2].confidence == 0.7  # 1.0 - (0.6 / 2.0)

    # Verify embedding was called
    mock_genai_client.models.embed_content.assert_called_once_with(
        model="models/gemini-embedding-001",
        contents=root_cause
    )


def test_rank_fixes_from_weaviate_fewer_than_3_results(postmortem_writer, mock_weaviate_client, mock_genai_client):
    """Test fix ranking pads to 3 results when Weaviate returns fewer."""
    # Mock embedding response
    mock_embed_response = MagicMock()
    mock_embed_response.embeddings = [MagicMock(values=[0.1] * 768)]
    mock_genai_client.models.embed_content.return_value = mock_embed_response

    # Mock only 1 Weaviate result
    mock_obj1 = MagicMock()
    mock_obj1.metadata.distance = 0.2
    mock_obj1.properties = {
        "fix": "Increase connection pool size",
        "title": "Database Connection Pool Exhaustion",
        "root_cause": "Pool size too small for traffic"
    }

    mock_collection = postmortem_writer.weaviate_collection
    mock_collection.query.near_vector.return_value.objects = [mock_obj1]

    root_cause = "Database connection pool exhausted"
    result = postmortem_writer._rank_fixes_from_weaviate(root_cause)

    assert len(result) == 3
    assert result[0].fix == "Increase connection pool size"
    assert result[0].confidence == 0.9

    # Check fallback fixes
    assert result[1].fix == "Inspect recent deployments and roll back if necessary"
    assert result[1].confidence == 0.3
    assert result[1].reasoning == "Generated without historical correlation"

    assert result[2].fix == "Inspect recent deployments and roll back if necessary"
    assert result[2].confidence == 0.3


def test_rank_fixes_from_weaviate_error_fallback(postmortem_writer, mock_weaviate_client, mock_genai_client):
    """Test fix ranking returns fallback fixes on error."""
    # Mock embedding to raise an exception
    mock_genai_client.models.embed_content.side_effect = Exception("API error")

    root_cause = "Database connection pool exhausted"
    result = postmortem_writer._rank_fixes_from_weaviate(root_cause)

    assert len(result) == 3
    for fix_candidate in result:
        assert fix_candidate.fix == "Inspect recent deployments and roll back if necessary"
        assert fix_candidate.confidence == 0.3
        assert fix_candidate.reasoning == "Generated without historical correlation"


def test_rank_fixes_confidence_bounds(postmortem_writer, mock_weaviate_client, mock_genai_client):
    """Test that confidence is bounded between 0.0 and 1.0."""
    # Mock embedding response
    mock_embed_response = MagicMock()
    mock_embed_response.embeddings = [MagicMock(values=[0.1] * 768)]
    mock_genai_client.models.embed_content.return_value = mock_embed_response

    # Mock result with very high distance (should clamp to 0.0)
    mock_obj1 = MagicMock()
    mock_obj1.metadata.distance = 5.0  # Very high distance
    mock_obj1.properties = {
        "fix": "Some fix",
        "title": "Some incident",
        "root_cause": "Some cause"
    }

    # Mock result with very low distance (should clamp to 1.0)
    mock_obj2 = MagicMock()
    mock_obj2.metadata.distance = 0.0  # Perfect match
    mock_obj2.properties = {
        "fix": "Another fix",
        "title": "Another incident",
        "root_cause": "Another cause"
    }

    mock_obj3 = MagicMock()
    mock_obj3.metadata.distance = 0.5
    mock_obj3.properties = {
        "fix": "Third fix",
        "title": "Third incident",
        "root_cause": "Third cause"
    }

    mock_collection = postmortem_writer.weaviate_collection
    mock_collection.query.near_vector.return_value.objects = [mock_obj1, mock_obj2, mock_obj3]

    result = postmortem_writer._rank_fixes_from_weaviate("test root cause")

    # Check confidence bounds
    for fix_candidate in result:
        assert 0.0 <= fix_candidate.confidence <= 1.0

    # Specifically check the extreme cases
    assert result[0].confidence == 0.0  # 1.0 - (5.0 / 2.0) = -1.5, clamped to 0.0
    assert result[1].confidence == 1.0  # 1.0 - (0.0 / 2.0) = 1.0


def test_postmortem_writer_close(postmortem_writer, mock_kafka_producer, mock_weaviate_client):
    """Test that close method flushes Kafka and closes Weaviate client."""
    postmortem_writer.close()

    mock_kafka_producer.flush.assert_called_once()
    mock_weaviate_client.close.assert_called_once()


def test_process_batch_multiple_alerts(postmortem_writer, mock_kafka_producer):
    """Should process multiple alerts in batch and flush Kafka once at end."""
    mock_result1 = MagicMock()
    mock_result1.title = "Incident 1"
    mock_result1.root_cause = "Root cause 1"
    mock_result1.timeline = "Timeline 1"
    mock_result1.remediation = "Remediation 1"
    mock_result1.prevention = "Prevention 1"

    mock_result2 = MagicMock()
    mock_result2.title = "Incident 2"
    mock_result2.root_cause = "Root cause 2"
    mock_result2.timeline = "Timeline 2"
    mock_result2.remediation = "Remediation 2"
    mock_result2.prevention = "Prevention 2"

    postmortem_writer.predictor.side_effect = [mock_result1, mock_result2]

    mock_fixes = [
        FixCandidate(fix="Fix 1", confidence=0.5, reasoning="Reason 1"),
        FixCandidate(fix="Fix 2", confidence=0.4, reasoning="Reason 2"),
        FixCandidate(fix="Fix 3", confidence=0.3, reasoning="Reason 3"),
    ]
    with patch.object(postmortem_writer, '_rank_fixes_from_weaviate', return_value=mock_fixes):
        alerts = [
            {
                "alert_id": "1",
                "service": "database",
                "message": "error 1",
                "severity_level": "critical",
                "blast_radius": ["service-a"],
                "rca_result": "RCA 1",
                "correlated_incidents": [],
            },
            {
                "alert_id": "2",
                "service": "api-gateway",
                "message": "error 2",
                "severity_level": "high",
                "blast_radius": ["service-b"],
                "rca_result": "RCA 2",
                "correlated_incidents": [],
            },
        ]
        results = postmortem_writer.process_batch(alerts)

    assert len(results) == 2
    assert results[0]["incident_id"] == "1"
    assert results[0]["title"] == "Incident 1"
    assert results[1]["incident_id"] == "2"
    assert results[1]["title"] == "Incident 2"

    # Verify flush called exactly once at end of batch
    mock_kafka_producer.flush.assert_called_once()


def test_process_single_alert_backward_compat(postmortem_writer, mock_kafka_producer):
    """Should verify process(alert) shim returns a single dict, not a list."""
    mock_result = MagicMock()
    mock_result.title = "Test Incident"
    mock_result.root_cause = "Test cause"
    mock_result.timeline = "Test timeline"
    mock_result.remediation = "Test remediation"
    mock_result.prevention = "Test prevention"
    postmortem_writer.predictor.return_value = mock_result

    mock_fixes = [
        FixCandidate(fix="Fix 1", confidence=0.5, reasoning="Reason 1"),
        FixCandidate(fix="Fix 2", confidence=0.4, reasoning="Reason 2"),
        FixCandidate(fix="Fix 3", confidence=0.3, reasoning="Reason 3"),
    ]
    with patch.object(postmortem_writer, '_rank_fixes_from_weaviate', return_value=mock_fixes):
        alert = {
            "alert_id": "123",
            "service": "database",
            "message": "connection timeout",
            "severity_level": "high",
            "blast_radius": [],
            "rca_result": "Network issue",
            "correlated_incidents": [],
        }
        result = postmortem_writer.process(alert)

    # Should return dict, not list
    assert isinstance(result, dict)
    assert not isinstance(result, list)
    assert result["incident_id"] == "123"
    assert result["title"] == "Test Incident"
