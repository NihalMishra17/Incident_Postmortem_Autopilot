import pytest
from unittest.mock import MagicMock, patch
from agents.pipeline import AlertBatcher, process_batches


def test_alert_batcher_groups_by_service():
    """Should group alerts by service and return them in separate lists on flush."""
    batcher = AlertBatcher(max_per_service=100)

    alert1 = {"alert_id": "1", "service": "database", "message": "error 1"}
    alert2 = {"alert_id": "2", "service": "api-gateway", "message": "error 2"}
    alert3 = {"alert_id": "3", "service": "database", "message": "error 3"}

    batcher.add_alert(alert1)
    batcher.add_alert(alert2)
    batcher.add_alert(alert3)

    batches = batcher.flush()

    assert "database" in batches
    assert "api-gateway" in batches
    assert len(batches["database"]) == 2
    assert len(batches["api-gateway"]) == 1
    assert batches["database"][0]["alert_id"] == "1"
    assert batches["database"][1]["alert_id"] == "3"
    assert batches["api-gateway"][0]["alert_id"] == "2"


def test_alert_batcher_flush_resets_state():
    """Should reset batcher state after flush so it's empty."""
    batcher = AlertBatcher(max_per_service=100)

    alert1 = {"alert_id": "1", "service": "database", "message": "error 1"}
    alert2 = {"alert_id": "2", "service": "database", "message": "error 2"}

    batcher.add_alert(alert1)
    batcher.add_alert(alert2)

    batches = batcher.flush()
    assert len(batches["database"]) == 2

    # After flush, batcher should be empty
    batches2 = batcher.flush()
    assert batches2 == {}


def test_alert_batcher_logs_warning_on_cap_exceeded(caplog):
    """Should log a warning when a service exceeds max alerts per window."""
    batcher = AlertBatcher(max_per_service=10)

    # Add 11 alerts for same service
    for i in range(11):
        alert = {"alert_id": str(i), "service": "database", "message": f"error {i}"}
        batcher.add_alert(alert)

    # Check that warning was logged with drop message
    assert any("window cap" in record.message for record in caplog.records)
    assert any("database" in record.message for record in caplog.records)


def test_alert_batcher_enforces_cap():
    """Should drop alerts exceeding the cap to prevent memory exhaustion."""
    batcher = AlertBatcher(max_per_service=10)

    # Add 15 alerts for same service
    for i in range(15):
        alert = {"alert_id": str(i), "service": "database", "message": f"error {i}"}
        batcher.add_alert(alert)

    batches = batcher.flush()

    # Only the first 10 alerts should be in the batch; excess are dropped
    assert len(batches["database"]) == 10
    assert batches["database"][0]["alert_id"] == "0"
    assert batches["database"][9]["alert_id"] == "9"


def test_process_batches_calls_triage_per_alert():
    """Should call triage.process for each alert individually."""
    triage = MagicMock()
    correlation = MagicMock()
    rca = MagicMock()
    writer = MagicMock()

    # Set up return values
    triage.process.side_effect = lambda a: {**a, "severity_level": "critical"}
    correlation.process_batch.side_effect = lambda alerts: [{**a, "correlated_incidents": []} for a in alerts]
    rca.process_batch.side_effect = lambda alerts: [{**a, "rca_result": "RCA"} for a in alerts]
    writer.process_batch.return_value = []

    batches = {
        "service-a": [
            {"alert_id": "1", "service": "service-a", "message": "error 1"},
            {"alert_id": "2", "service": "service-a", "message": "error 2"},
            {"alert_id": "3", "service": "service-a", "message": "error 3"},
        ]
    }

    process_batches(batches, triage, correlation, rca, writer, delay_seconds=0)

    # Triage should be called 3 times (once per alert)
    assert triage.process.call_count == 3


def test_process_batches_calls_batch_methods_once():
    """Should call correlation, rca, and writer process_batch methods exactly once."""
    triage = MagicMock()
    correlation = MagicMock()
    rca = MagicMock()
    writer = MagicMock()

    # Set up return values
    triage.process.side_effect = lambda a: {**a, "severity_level": "critical"}
    correlation.process_batch.side_effect = lambda alerts: [{**a, "correlated_incidents": []} for a in alerts]
    rca.process_batch.side_effect = lambda alerts: [{**a, "rca_result": "RCA"} for a in alerts]
    writer.process_batch.return_value = []

    batches = {
        "service-a": [
            {"alert_id": "1", "service": "service-a", "message": "error 1"},
            {"alert_id": "2", "service": "service-a", "message": "error 2"},
            {"alert_id": "3", "service": "service-a", "message": "error 3"},
        ]
    }

    process_batches(batches, triage, correlation, rca, writer, delay_seconds=0)

    # Each batch method should be called exactly once
    correlation.process_batch.assert_called_once()
    rca.process_batch.assert_called_once()
    writer.process_batch.assert_called_once()


def test_process_batches_skips_empty_service():
    """Should skip processing when a service has an empty alert list."""
    triage = MagicMock()
    correlation = MagicMock()
    rca = MagicMock()
    writer = MagicMock()

    batches = {
        "service-a": [],  # Empty list
    }

    process_batches(batches, triage, correlation, rca, writer, delay_seconds=0)

    # No agent methods should be called for empty batch
    triage.process.assert_not_called()
    correlation.process_batch.assert_not_called()
    rca.process_batch.assert_not_called()
    writer.process_batch.assert_not_called()


def test_process_batches_continues_on_error():
    """Should continue processing other services if one service raises an exception."""
    triage = MagicMock()
    correlation = MagicMock()
    rca = MagicMock()
    writer = MagicMock()

    # Set up return values - correlation will fail for first service
    triage.process.side_effect = lambda a: {**a, "severity_level": "critical"}

    call_count = [0]
    def correlation_side_effect(alerts):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("Correlation failed for service-a")
        return [{**a, "correlated_incidents": []} for a in alerts]

    correlation.process_batch.side_effect = correlation_side_effect
    rca.process_batch.side_effect = lambda alerts: [{**a, "rca_result": "RCA"} for a in alerts]
    writer.process_batch.return_value = []

    batches = {
        "service-a": [
            {"alert_id": "1", "service": "service-a", "message": "error 1"},
        ],
        "service-b": [
            {"alert_id": "2", "service": "service-b", "message": "error 2"},
        ]
    }

    process_batches(batches, triage, correlation, rca, writer, delay_seconds=0)

    # Correlation should have been called twice (once for each service)
    assert correlation.process_batch.call_count == 2

    # RCA and writer should only be called once (for service-b)
    # because service-a failed at correlation stage
    rca.process_batch.assert_called_once()
    writer.process_batch.assert_called_once()


def test_alert_batcher_handles_unknown_service():
    """Should handle alerts with no service field by grouping under 'unknown'."""
    batcher = AlertBatcher(max_per_service=100)

    alert1 = {"alert_id": "1", "message": "error without service"}
    alert2 = {"alert_id": "2", "service": "database", "message": "error with service"}

    batcher.add_alert(alert1)
    batcher.add_alert(alert2)

    batches = batcher.flush()

    assert "unknown" in batches
    assert "database" in batches
    assert len(batches["unknown"]) == 1
    assert batches["unknown"][0]["alert_id"] == "1"


def test_process_batches_enriches_alerts_through_pipeline():
    """Should pass alerts through full pipeline and enrich at each stage."""
    triage = MagicMock()
    correlation = MagicMock()
    rca = MagicMock()
    writer = MagicMock()

    # Each agent adds a field
    triage.process.side_effect = lambda a: {**a, "severity_level": "critical", "blast_radius": ["service-b"]}
    correlation.process_batch.side_effect = lambda alerts: [{**a, "correlated_incidents": [{"title": "Past incident"}]} for a in alerts]
    rca.process_batch.side_effect = lambda alerts: [{**a, "rca_result": "Root cause analysis"} for a in alerts]
    writer.process_batch.return_value = [
        {
            "incident_id": "1",
            "title": "Incident",
            "severity": "critical",
            "root_cause": "RCA",
        }
    ]

    batches = {
        "service-a": [
            {"alert_id": "1", "service": "service-a", "message": "error 1"},
        ]
    }

    process_batches(batches, triage, correlation, rca, writer, delay_seconds=0)

    # Verify the pipeline flow by checking what was passed to writer
    writer_call_args = writer.process_batch.call_args[0][0]
    assert len(writer_call_args) == 1
    enriched_alert = writer_call_args[0]

    # Alert should have all enrichments
    assert enriched_alert["severity_level"] == "critical"
    assert enriched_alert["blast_radius"] == ["service-b"]
    assert enriched_alert["correlated_incidents"] == [{"title": "Past incident"}]
    assert enriched_alert["rca_result"] == "Root cause analysis"


def test_process_batches_handles_multiple_services():
    """Should process batches for multiple services independently."""
    triage = MagicMock()
    correlation = MagicMock()
    rca = MagicMock()
    writer = MagicMock()

    triage.process.side_effect = lambda a: {**a, "severity_level": "critical"}
    correlation.process_batch.side_effect = lambda alerts: [{**a, "correlated_incidents": []} for a in alerts]
    rca.process_batch.side_effect = lambda alerts: [{**a, "rca_result": "RCA"} for a in alerts]
    writer.process_batch.return_value = []

    batches = {
        "service-a": [
            {"alert_id": "1", "service": "service-a", "message": "error 1"},
            {"alert_id": "2", "service": "service-a", "message": "error 2"},
        ],
        "service-b": [
            {"alert_id": "3", "service": "service-b", "message": "error 3"},
        ],
        "service-c": [
            {"alert_id": "4", "service": "service-c", "message": "error 4"},
            {"alert_id": "5", "service": "service-c", "message": "error 5"},
            {"alert_id": "6", "service": "service-c", "message": "error 6"},
        ],
    }

    process_batches(batches, triage, correlation, rca, writer, delay_seconds=0)

    # Triage should be called 6 times total (2 + 1 + 3)
    assert triage.process.call_count == 6

    # Each batch method should be called 3 times (once per service)
    assert correlation.process_batch.call_count == 3
    assert rca.process_batch.call_count == 3
    assert writer.process_batch.call_count == 3
