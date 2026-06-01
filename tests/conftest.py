import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer with produce and flush methods."""
    producer = MagicMock()
    producer.produce = MagicMock()
    producer.flush = MagicMock()
    return producer


@pytest.fixture
def mock_kafka_consumer():
    """Mock Kafka consumer with subscribe method."""
    consumer = MagicMock()
    consumer.subscribe = MagicMock()
    return consumer


@pytest.fixture
def mock_weaviate_client():
    """Mock Weaviate client with collections API."""
    client = MagicMock()
    client.collections = MagicMock()
    client.collections.exists = MagicMock(return_value=False)
    client.collections.create = MagicMock()
    client.close = MagicMock()
    return client


@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j driver with session context manager."""
    driver = MagicMock()
    session = MagicMock()
    session.run = MagicMock()
    driver.session = MagicMock(return_value=session)
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.close = MagicMock()
    return driver
