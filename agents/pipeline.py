"""Event-driven agent pipeline that consumes alerts from Kafka, windows them by service, and publishes postmortems.

Alerts are accumulated in a tumbling window (default 30 seconds) per service before batch processing.
Run as: python -m agents.pipeline with WINDOW_SIZE_SECONDS and MAX_ALERTS_PER_WINDOW_PER_SERVICE env vars.
"""
import logging_config
import json
import logging
import os
import signal
import threading
import time
from collections import defaultdict
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

class AlertBatcher:
    def __init__(self, max_per_service: int):
        self.batches = defaultdict(list)
        self.max_per_service = max_per_service

    def add_alert(self, alert: dict):
        service = alert.get("service", "unknown")
        if len(self.batches[service]) >= self.max_per_service:
            logger.warning(
                "Alert dropped for service %s: window cap of %d exceeded",
                service, self.max_per_service
            )
            return
        self.batches[service].append(alert)

    def flush(self) -> dict:
        batches = dict(self.batches)
        self.batches = defaultdict(list)
        return batches

def process_batches(batches, triage, correlation, rca, writer, delay_seconds):
    services = list(batches.items())
    for i, (service, alerts) in enumerate(services):
        if not alerts:
            continue
        try:
            enriched = [triage.process(a) for a in alerts]
            enriched = correlation.process_batch(enriched)
            enriched = rca.process_batch(enriched)
            writer.process_batch(enriched)
        except Exception as e:
            logger.error("Failed to process batch for service %s: %s", service, e)
        if i < len(services) - 1 and delay_seconds > 0:
            time.sleep(delay_seconds)

def run():
    """Initialize agents, consume alerts from Kafka, run pipeline sequentially, and publish postmortems."""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    WINDOW_SIZE_SECONDS = max(1, min(3600, int(os.getenv("WINDOW_SIZE_SECONDS", "30"))))
    MAX_ALERTS_PER_WINDOW_PER_SERVICE = max(1, min(10000, int(os.getenv("MAX_ALERTS_PER_WINDOW_PER_SERVICE", "100"))))

    import dspy
    lm = dspy.LM(
        f"gemini/{os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')}",
        api_key=os.getenv("GEMINI_API_KEY"),
        num_retries=5,
        max_tokens=8192,
    )
    dspy.configure(lm=lm)
    SERVICE_BATCH_DELAY_SECONDS = max(0.0, min(10.0, float(os.getenv("SERVICE_BATCH_DELAY_SECONDS", "1"))))

    triage = TriageAgent()
    correlation = CorrelationAgent()
    rca = RCAAgent()
    writer = PostmortemWriter()
    consumer = get_consumer("alerts", group_id="postmortem-pipeline", enable_auto_commit=False)

    logger.info("Pipeline started, consuming from 'alerts' topic with %ds windows", WINDOW_SIZE_SECONDS)
    try:
        batcher = AlertBatcher(MAX_ALERTS_PER_WINDOW_PER_SERVICE)
        window_start = time.time()
        window_size = WINDOW_SIZE_SECONDS

        while not shutdown_event.is_set():
            msg = consumer.poll(timeout=0.1)
            if msg is not None and not msg.error():
                alert = json.loads(msg.value().decode("utf-8"))
                batcher.add_alert(alert)

            if time.time() >= window_start + window_size:
                batches = batcher.flush()
                if batches:
                    process_batches(batches, triage, correlation, rca, writer, SERVICE_BATCH_DELAY_SECONDS)
                    try:
                        consumer.commit()
                    except Exception as e:
                        logger.error("Failed to commit offsets after window flush: %s", e)
                window_start = time.time()

        batches = batcher.flush()
        if batches:
            process_batches(batches, triage, correlation, rca, writer, SERVICE_BATCH_DELAY_SECONDS)
    finally:
        consumer.close()
        triage.close()
        correlation.close()
        rca.close()
        writer.close()
        logger.info("Pipeline shut down cleanly")

if __name__ == "__main__":
    run()
