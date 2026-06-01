import json
import pytest
from unittest.mock import patch, MagicMock, call
from infra.kafka_client import get_producer, get_consumer, produce_json, delivery_report


class TestGetProducer:
    """Test Kafka producer initialization."""

    @patch('infra.kafka_client.Producer')
    def test_get_producer_default_bootstrap(self, mock_producer_class):
        """Test producer creation with default bootstrap servers."""
        mock_instance = MagicMock()
        mock_producer_class.return_value = mock_instance

        result = get_producer()

        mock_producer_class.assert_called_once_with({
            'bootstrap.servers': 'localhost:9092',
            'client.id': 'incident-producer'
        })
        assert result == mock_instance

    @patch('infra.kafka_client.Producer')
    def test_get_producer_custom_bootstrap(self, mock_producer_class):
        """Test producer creation with custom bootstrap servers."""
        mock_instance = MagicMock()
        mock_producer_class.return_value = mock_instance

        result = get_producer('kafka1:9092,kafka2:9092')

        mock_producer_class.assert_called_once_with({
            'bootstrap.servers': 'kafka1:9092,kafka2:9092',
            'client.id': 'incident-producer'
        })
        assert result == mock_instance


class TestGetConsumer:
    """Test Kafka consumer initialization."""

    @patch('infra.kafka_client.Consumer')
    def test_get_consumer_default_bootstrap(self, mock_consumer_class):
        """Test consumer creation with default bootstrap servers."""
        mock_instance = MagicMock()
        mock_consumer_class.return_value = mock_instance

        result = get_consumer('test-topic', 'test-group')

        mock_consumer_class.assert_called_once_with({
            'bootstrap.servers': 'localhost:9092',
            'group.id': 'test-group',
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': True
        })
        mock_instance.subscribe.assert_called_once_with(['test-topic'])
        assert result == mock_instance

    @patch('infra.kafka_client.Consumer')
    def test_get_consumer_custom_bootstrap(self, mock_consumer_class):
        """Test consumer creation with custom bootstrap servers."""
        mock_instance = MagicMock()
        mock_consumer_class.return_value = mock_instance

        result = get_consumer('alerts', 'alert-processor', 'kafka1:9092')

        mock_consumer_class.assert_called_once_with({
            'bootstrap.servers': 'kafka1:9092',
            'group.id': 'alert-processor',
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': True
        })
        mock_instance.subscribe.assert_called_once_with(['alerts'])
        assert result == mock_instance

    @patch('infra.kafka_client.Consumer')
    def test_get_consumer_subscribes_to_topic(self, mock_consumer_class):
        """Test that consumer subscribes to the specified topic."""
        mock_instance = MagicMock()
        mock_consumer_class.return_value = mock_instance

        get_consumer('raw-logs', 'log-consumer')

        mock_instance.subscribe.assert_called_once_with(['raw-logs'])


class TestProduceJson:
    """Test JSON message production to Kafka."""

    def test_produce_json_without_key(self, mock_kafka_producer):
        """Test producing JSON message without a key."""
        data = {'alert_id': '123', 'service': 'api-gateway', 'severity': 'P1'}

        produce_json(mock_kafka_producer, 'alerts', data)

        expected_value = json.dumps(data).encode('utf-8')
        mock_kafka_producer.produce.assert_called_once_with(
            topic='alerts',
            key=None,
            value=expected_value,
            callback=delivery_report
        )

    def test_produce_json_with_key(self, mock_kafka_producer):
        """Test producing JSON message with a key."""
        data = {'alert_id': '456', 'service': 'auth-service', 'severity': 'P2'}
        key = 'alert-456'

        produce_json(mock_kafka_producer, 'alerts', data, key=key)

        expected_value = json.dumps(data).encode('utf-8')
        expected_key = key.encode('utf-8')
        mock_kafka_producer.produce.assert_called_once_with(
            topic='alerts',
            key=expected_key,
            value=expected_value,
            callback=delivery_report
        )

    def test_produce_json_nested_data(self, mock_kafka_producer):
        """Test producing nested JSON structure."""
        data = {
            'alert': {
                'id': '789',
                'metadata': {
                    'service': 'order-service',
                    'tags': ['urgent', 'production']
                }
            }
        }

        produce_json(mock_kafka_producer, 'postmortems', data, key='post-789')

        expected_value = json.dumps(data).encode('utf-8')
        expected_key = 'post-789'.encode('utf-8')
        mock_kafka_producer.produce.assert_called_once_with(
            topic='postmortems',
            key=expected_key,
            value=expected_value,
            callback=delivery_report
        )

    def test_produce_json_empty_data(self, mock_kafka_producer):
        """Test producing empty JSON object."""
        data = {}

        produce_json(mock_kafka_producer, 'test-topic', data)

        expected_value = json.dumps(data).encode('utf-8')
        assert expected_value == b'{}'
        mock_kafka_producer.produce.assert_called_once()

    def test_produce_json_special_characters_in_key(self, mock_kafka_producer):
        """Test producing message with special characters in key."""
        data = {'test': 'value'}
        key = 'key-with-special-chars-!@#$%'

        produce_json(mock_kafka_producer, 'test-topic', data, key=key)

        expected_key = key.encode('utf-8')
        mock_kafka_producer.produce.assert_called_once()
        call_args = mock_kafka_producer.produce.call_args
        assert call_args[1]['key'] == expected_key


class TestDeliveryReport:
    """Test Kafka delivery report callback."""

    @patch('builtins.print')
    def test_delivery_report_on_error(self, mock_print):
        """Test delivery report logs errors."""
        error = Exception("Connection failed")
        msg = MagicMock()

        delivery_report(error, msg)

        mock_print.assert_called_once_with(f"Message delivery failed: {error}")

    @patch('builtins.print')
    def test_delivery_report_on_success(self, mock_print):
        """Test delivery report does nothing on success."""
        msg = MagicMock()

        delivery_report(None, msg)

        mock_print.assert_not_called()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_produce_json_unicode_data(self, mock_kafka_producer):
        """Test producing message with Unicode characters."""
        data = {'message': 'Hello 世界 🌍', 'service': 'test'}

        produce_json(mock_kafka_producer, 'test-topic', data)

        expected_value = json.dumps(data).encode('utf-8')
        mock_kafka_producer.produce.assert_called_once()
        call_args = mock_kafka_producer.produce.call_args
        assert call_args[1]['value'] == expected_value

    def test_produce_json_large_payload(self, mock_kafka_producer):
        """Test producing large JSON payload."""
        data = {'logs': ['log line ' + str(i) for i in range(1000)]}

        produce_json(mock_kafka_producer, 'raw-logs', data)

        mock_kafka_producer.produce.assert_called_once()
        call_args = mock_kafka_producer.produce.call_args
        assert call_args[1]['topic'] == 'raw-logs'

    def test_produce_json_numeric_values(self, mock_kafka_producer):
        """Test producing message with various numeric types."""
        data = {
            'int_value': 42,
            'float_value': 3.14159,
            'negative': -100,
            'zero': 0
        }

        produce_json(mock_kafka_producer, 'metrics', data)

        expected_value = json.dumps(data).encode('utf-8')
        call_args = mock_kafka_producer.produce.call_args
        assert call_args[1]['value'] == expected_value
