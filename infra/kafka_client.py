"""Kafka producer and consumer initialization with JSON serialization helpers."""
import json
from confluent_kafka import Producer, Consumer


def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")


def get_producer(bootstrap_servers='localhost:9092'):
    """Returns a Kafka producer configured for incident events."""
    config = {
        'bootstrap.servers': bootstrap_servers,
        'client.id': 'incident-producer'
    }
    return Producer(config)


def get_consumer(topic, group_id, bootstrap_servers='localhost:9092', enable_auto_commit=True):
    """Returns a Kafka consumer subscribed to the given topic.

    Args:
        enable_auto_commit: If False, allows manual commit via consumer.commit() for windowed processing.
    """
    config = {
        'bootstrap.servers': bootstrap_servers,
        'group.id': group_id,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': enable_auto_commit
    }
    consumer = Consumer(config)
    consumer.subscribe([topic])
    return consumer


def produce_json(producer, topic, data: dict, key=None):
    """Serializes dict to JSON and produces to topic with optional key."""
    value_bytes = json.dumps(data).encode('utf-8')
    key_bytes = key.encode('utf-8') if key else None
    producer.produce(
        topic=topic,
        key=key_bytes,
        value=value_bytes,
        callback=delivery_report
    )
