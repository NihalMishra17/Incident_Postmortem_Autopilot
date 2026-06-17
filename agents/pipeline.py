"""Event-driven agent pipeline that consumes alerts from Kafka and publishes postmortems.

Run as: python -m agents.pipeline
"""
import logging_config
import json
import logging
import os
import signal
import threading
from infra.kafka_client import get_consumer
from agents.triage_agent import TriageAgent
from agents.correlation_agent import CorrelationAgent
from agents.rca_agent import RCAAgent
from agents.postmortem_writer import PostmortemWriter

logger = logging.getLogger(__name__)

shutdown_event = threading.Event()

def _handle_signal(signum, frame):
    """Set shutdown event on SIGINT or SIGTERM to trigger graceful cleanup."""
    logger.info("Shutdown signal received, stopping pipeline...")
    shutdown_event.set()

def run():
    """Initialize agents, consume alerts from Kafka, run pipeline sequentially, and publish postmortems."""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    triage = TriageAgent()
    correlation = CorrelationAgent()
    rca = RCAAgent()
    writer = PostmortemWriter()
    consumer = get_consumer("alerts", group_id="postmortem-pipeline")

    logger.info("Pipeline started, consuming from 'alerts' topic")
    try:
        while not shutdown_event.is_set():
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error("Kafka error: %s", msg.error())
                continue
            try:
                alert = json.loads(msg.value().decode("utf-8"))
                logger.info("Processing alert %s", alert.get("alert_id"))
                # Sequential pipeline: each agent enriches alert with structured context
                alert = triage.process(alert)
                alert = correlation.process(alert)
                alert = rca.process(alert)
                writer.process(alert)
            except Exception as e:
                logger.error("Failed to process alert: %s", e)
    finally:
        consumer.close()
        triage.close()
        correlation.close()
        writer.close()
        logger.info("Pipeline shut down cleanly")

if __name__ == "__main__":
    run()
