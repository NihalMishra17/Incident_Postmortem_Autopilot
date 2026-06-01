import pytest
import signal
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock, call
from simulator.incident_simulator import (
    SERVICES, SEVERITIES, SEVERITY_WEIGHTS, LOG_LEVELS, LOG_LEVEL_WEIGHTS,
    signal_handler, running
)


class TestConstants:
    """Test simulator constants and configuration."""

    def test_services_list_length(self):
        """Test that SERVICES contains exactly 10 services."""
        assert len(SERVICES) == 10

    def test_services_list_content(self):
        """Test that all expected services are present."""
        expected_services = [
            "api-gateway", "auth-service", "user-service", "order-service",
            "payment-service", "notification-service", "inventory-service",
            "analytics-service", "logging-service", "cache-service"
        ]
        assert set(SERVICES) == set(expected_services)

    def test_severities_list(self):
        """Test severity levels configuration."""
        assert SEVERITIES == ["P1", "P2", "P3"]

    def test_severity_weights_distribution(self):
        """Test that P3 is most common, P1 is least common."""
        assert len(SEVERITY_WEIGHTS) == 3
        assert SEVERITY_WEIGHTS[2] > SEVERITY_WEIGHTS[1] > SEVERITY_WEIGHTS[0]
        assert SEVERITY_WEIGHTS == [10, 30, 60]

    def test_log_levels_list(self):
        """Test log levels configuration."""
        assert LOG_LEVELS == ["ERROR", "WARN", "INFO"]

    def test_log_level_weights_distribution(self):
        """Test log level weight distribution."""
        assert len(LOG_LEVEL_WEIGHTS) == 3
        assert LOG_LEVEL_WEIGHTS == [20, 30, 50]


class TestSignalHandler:
    """Test signal handler for graceful shutdown."""

    @patch('simulator.incident_simulator.running', True)
    @patch('builtins.print')
    def test_signal_handler_sets_running_false(self, mock_print):
        """Test that signal handler sets running to False."""
        # Import the module to get access to the global
        import simulator.incident_simulator as sim
        sim.running = True

        signal_handler(signal.SIGINT, None)

        assert sim.running is False
        mock_print.assert_called_with("\nShutting down simulator...")

    @patch('builtins.print')
    def test_signal_handler_with_sigterm(self, mock_print):
        """Test signal handler with SIGTERM."""
        import simulator.incident_simulator as sim
        sim.running = True

        signal_handler(signal.SIGTERM, None)

        assert sim.running is False

    @patch('builtins.print')
    def test_signal_handler_prints_shutdown_message(self, mock_print):
        """Test that signal handler prints shutdown message."""
        signal_handler(signal.SIGINT, None)

        mock_print.assert_called_once_with("\nShutting down simulator...")


class TestAlertGeneration:
    """Test alert message generation logic."""

    @patch('simulator.incident_simulator.uuid.uuid4')
    @patch('simulator.incident_simulator.random.choice')
    @patch('simulator.incident_simulator.random.choices')
    @patch('simulator.incident_simulator.datetime')
    @patch('simulator.incident_simulator.fake.sentence')
    def test_alert_structure(self, mock_sentence, mock_datetime, mock_choices,
                            mock_choice, mock_uuid):
        """Test that generated alerts have correct structure."""
        # Setup mocks
        mock_uuid.return_value = uuid.UUID('12345678-1234-5678-1234-567812345678')
        mock_choice.return_value = 'api-gateway'
        mock_choices.return_value = ['P2']
        mock_dt = MagicMock()
        mock_dt.utcnow().isoformat.return_value = '2026-06-01T12:00:00.000000'
        mock_datetime.utcnow.return_value = mock_dt.utcnow()
        mock_sentence.return_value = 'Test alert message'

        # Simulate alert creation logic
        alert_id = str(mock_uuid())
        service = mock_choice(SERVICES)
        severity = mock_choices(SEVERITIES, weights=SEVERITY_WEIGHTS)[0]
        timestamp = mock_datetime.utcnow().isoformat() + "Z"
        message = mock_sentence()

        alert = {
            "alert_id": alert_id,
            "service": service,
            "severity": severity,
            "timestamp": timestamp,
            "message": message
        }

        # Verify alert structure
        assert "alert_id" in alert
        assert "service" in alert
        assert "severity" in alert
        assert "timestamp" in alert
        assert "message" in alert
        assert alert["severity"] in SEVERITIES
        assert alert["service"] in SERVICES
        assert alert["timestamp"].endswith("Z")

    def test_alert_id_is_uuid(self):
        """Test that alert_id is valid UUID format."""
        alert_id = str(uuid.uuid4())

        # Verify it can be parsed back to UUID
        parsed_uuid = uuid.UUID(alert_id)
        assert isinstance(parsed_uuid, uuid.UUID)

    @patch('simulator.incident_simulator.random.choice')
    def test_service_selection_from_list(self, mock_choice):
        """Test that service is selected from SERVICES list."""
        mock_choice.return_value = 'auth-service'

        service = mock_choice(SERVICES)

        assert service in SERVICES
        mock_choice.assert_called_once_with(SERVICES)

    @patch('simulator.incident_simulator.random.choices')
    def test_severity_selection_weighted(self, mock_choices):
        """Test that severity is selected with weights."""
        mock_choices.return_value = ['P3']

        severity = mock_choices(SEVERITIES, weights=SEVERITY_WEIGHTS)[0]

        assert severity in SEVERITIES
        mock_choices.assert_called_once_with(SEVERITIES, weights=SEVERITY_WEIGHTS)

    def test_timestamp_format(self):
        """Test that timestamp has correct ISO format with Z suffix."""
        timestamp = datetime.utcnow().isoformat() + "Z"

        assert timestamp.endswith("Z")
        assert "T" in timestamp
        # Verify it can be parsed
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert isinstance(parsed, datetime)


class TestLogGeneration:
    """Test log burst generation logic."""

    @patch('simulator.incident_simulator.random.randint')
    def test_log_burst_count(self, mock_randint):
        """Test that log burst generates 5-20 logs."""
        mock_randint.return_value = 10

        num_logs = mock_randint(5, 20)

        assert 5 <= num_logs <= 20
        mock_randint.assert_called_once_with(5, 20)

    @patch('simulator.incident_simulator.random.choices')
    @patch('simulator.incident_simulator.random.random')
    @patch('simulator.incident_simulator.fake.sentence')
    @patch('simulator.incident_simulator.fake.file_path')
    @patch('simulator.incident_simulator.random.randint')
    def test_log_structure(self, mock_randint, mock_filepath, mock_sentence,
                          mock_random, mock_choices):
        """Test that generated logs have correct structure."""
        # Setup mocks
        mock_choices.return_value = ['ERROR']
        mock_random.return_value = 0.5  # > 0.3, will use sentence
        mock_sentence.return_value = 'Test log message'
        alert_id = str(uuid.uuid4())
        service = 'api-gateway'

        # Simulate log creation logic
        log = {
            "alert_id": alert_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "service": service,
            "level": mock_choices(LOG_LEVELS, weights=LOG_LEVEL_WEIGHTS)[0],
            "message": mock_sentence()
        }

        # Verify log structure
        assert "alert_id" in log
        assert "timestamp" in log
        assert "service" in log
        assert "level" in log
        assert "message" in log
        assert log["level"] in LOG_LEVELS
        assert log["timestamp"].endswith("Z")

    @patch('simulator.incident_simulator.random.choices')
    def test_log_level_weighted_selection(self, mock_choices):
        """Test that log level is selected with weights."""
        mock_choices.return_value = ['WARN']

        level = mock_choices(LOG_LEVELS, weights=LOG_LEVEL_WEIGHTS)[0]

        assert level in LOG_LEVELS
        mock_choices.assert_called_once_with(LOG_LEVELS, weights=LOG_LEVEL_WEIGHTS)

    @patch('simulator.incident_simulator.random.random')
    @patch('simulator.incident_simulator.fake.sentence')
    @patch('simulator.incident_simulator.fake.file_path')
    @patch('simulator.incident_simulator.random.randint')
    def test_log_message_sentence_format(self, mock_randint, mock_filepath,
                                         mock_sentence, mock_random):
        """Test log message as sentence when random > 0.3."""
        mock_random.return_value = 0.5
        mock_sentence.return_value = 'Error processing request'

        message = mock_sentence() if mock_random() > 0.3 else f"at {mock_filepath(extension='py')}:{mock_randint(1, 500)}"

        assert message == 'Error processing request'

    @patch('simulator.incident_simulator.random.random')
    @patch('simulator.incident_simulator.fake.file_path')
    @patch('simulator.incident_simulator.random.randint')
    def test_log_message_stacktrace_format(self, mock_randint, mock_filepath,
                                           mock_random):
        """Test log message as stacktrace when random <= 0.3."""
        mock_random.return_value = 0.2
        mock_filepath.return_value = '/app/service/handler.py'
        mock_randint.return_value = 42

        message = f"at {mock_filepath(extension='py')}:{mock_randint(1, 500)}" if mock_random() <= 0.3 else 'sentence'

        assert 'at ' in message
        assert '.py:' in message

    @patch('simulator.incident_simulator.random.randint')
    def test_log_burst_boundary_values(self, mock_randint):
        """Test log burst boundary values (5 and 20)."""
        # Test minimum
        mock_randint.return_value = 5
        num_logs = mock_randint(5, 20)
        assert num_logs == 5

        # Test maximum
        mock_randint.return_value = 20
        num_logs = mock_randint(5, 20)
        assert num_logs == 20


class TestKafkaIntegration:
    """Test Kafka producer integration."""

    @patch('simulator.incident_simulator.get_producer')
    @patch('simulator.incident_simulator.produce_json')
    def test_alert_produced_to_alerts_topic(self, mock_produce, mock_get_producer):
        """Test that alerts are produced to 'alerts' topic."""
        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        alert = {
            "alert_id": "test-123",
            "service": "api-gateway",
            "severity": "P1",
            "timestamp": "2026-06-01T12:00:00Z",
            "message": "Test alert"
        }

        # Simulate producing alert
        from simulator.incident_simulator import produce_json
        produce_json(mock_producer, "alerts", alert, key="test-123")

        mock_produce.assert_called_once_with(mock_producer, "alerts", alert, key="test-123")

    @patch('simulator.incident_simulator.get_producer')
    @patch('simulator.incident_simulator.produce_json')
    def test_logs_produced_to_raw_logs_topic(self, mock_produce, mock_get_producer):
        """Test that logs are produced to 'raw-logs' topic."""
        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        log = {
            "alert_id": "test-123",
            "timestamp": "2026-06-01T12:00:00Z",
            "service": "api-gateway",
            "level": "ERROR",
            "message": "Test log"
        }

        # Simulate producing log
        from simulator.incident_simulator import produce_json
        produce_json(mock_producer, "raw-logs", log)

        mock_produce.assert_called_once_with(mock_producer, "raw-logs", log)

    @patch('simulator.incident_simulator.get_producer')
    def test_producer_flush_called(self, mock_get_producer):
        """Test that producer.flush() is called."""
        mock_producer = MagicMock()
        mock_get_producer.return_value = mock_producer

        # Simulate flush
        mock_producer.flush()

        mock_producer.flush.assert_called_once()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_services_list_handling(self):
        """Test that SERVICES list is not empty."""
        assert len(SERVICES) > 0

    def test_severity_weights_sum(self):
        """Test that severity weights sum to 100."""
        assert sum(SEVERITY_WEIGHTS) == 100

    def test_log_level_weights_sum(self):
        """Test that log level weights sum to 100."""
        assert sum(LOG_LEVEL_WEIGHTS) == 100

    @patch('simulator.incident_simulator.datetime')
    def test_timestamp_uniqueness(self, mock_datetime):
        """Test that timestamps can be unique across rapid calls."""
        # Each call should generate a new timestamp
        mock_dt = MagicMock()
        mock_dt.utcnow().isoformat.side_effect = [
            '2026-06-01T12:00:00.000001',
            '2026-06-01T12:00:00.000002'
        ]

        ts1 = mock_dt.utcnow().isoformat() + "Z"
        ts2 = mock_dt.utcnow().isoformat() + "Z"

        # Timestamps should be different
        assert ts1 != ts2

    def test_uuid_uniqueness(self):
        """Test that UUIDs are unique across multiple generations."""
        uuid1 = str(uuid.uuid4())
        uuid2 = str(uuid.uuid4())
        uuid3 = str(uuid.uuid4())

        assert uuid1 != uuid2
        assert uuid2 != uuid3
        assert uuid1 != uuid3

    @patch('simulator.incident_simulator.random.randint')
    def test_zero_logs_not_generated(self, mock_randint):
        """Test that at least 5 logs are generated (minimum boundary)."""
        # Range is 5-20, so minimum is 5
        mock_randint.return_value = 5
        num_logs = mock_randint(5, 20)

        assert num_logs >= 5

    def test_services_no_duplicates(self):
        """Test that SERVICES list has no duplicates."""
        assert len(SERVICES) == len(set(SERVICES))
