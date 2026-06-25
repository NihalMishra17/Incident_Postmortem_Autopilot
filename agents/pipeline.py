"""Event-driven agent pipeline that consumes alerts from Kafka, windows them by service, and publishes postmortems.

Alerts are accumulated in a tumbling window (default 30 seconds) per service before batch processing.
Run as: python -m agents.pipeline with WINDOW_SIZE_SECONDS and MAX_ALERTS_PER_WINDOW_PER_SERVICE env vars.
"""
import os
from dotenv import dotenv_values
from pathlib import Path
for _k, _v in dotenv_values(Path(__file__).parent.parent / ".env").items():
    if not os.environ.get(_k):  # only fill in vars that are absent or empty
        os.environ[_k] = _v or ""
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
        self.log_buffer: dict[str, list[dict]] = {}
        self.prev_processed_ids: set[str] = set()
        self._MAX_BUFFER_KEYS = 1000

    def add_alert(self, alert: dict):
        service = alert.get("service", "unknown")
        if len(self.batches[service]) >= self.max_per_service:
            logger.warning(
                "Alert dropped for service %s: window cap of %d exceeded",
                service, self.max_per_service
            )
            return
        self.batches[service].append(alert)

    def add_log(self, log: dict) -> None:
        alert_id = log.get("alert_id")
        if not alert_id:
            return
        if alert_id not in self.log_buffer and len(self.log_buffer) >= self._MAX_BUFFER_KEYS:
            oldest = next(iter(self.log_buffer))
            del self.log_buffer[oldest]
        self.log_buffer.setdefault(alert_id, []).append(log)

    def get_logs_for_alerts(self, alerts: list[dict]) -> dict[str, list[dict]]:
        return {
            a["alert_id"]: self.log_buffer.get(a["alert_id"], [])
            for a in alerts
            if a.get("alert_id")
        }

    def flush(self) -> dict:
        batches = dict(self.batches)
        self.batches = defaultdict(list)
        # Clear log buffer entries from the previous window (one-window grace period for late logs)
        for aid in self.prev_processed_ids:
            self.log_buffer.pop(aid, None)
        current_ids = {a["alert_id"] for alerts in batches.values() for a in alerts if a.get("alert_id")}
        self.prev_processed_ids = current_ids
        return batches

def process_batches(batches, triage, correlation, rca, writer, delay_seconds, batcher=None):
    services = list(batches.items())
    for i, (service, alerts) in enumerate(services):
        if not alerts:
            continue
        try:
            enriched = [triage.process(a) for a in alerts]
            enriched = correlation.process_batch(enriched)
            logs_by_id = batcher.get_logs_for_alerts(enriched) if batcher else {}
            enriched = rca.process_batch(enriched, logs_by_alert_id=logs_by_id)
            writer.process_batch(enriched)
        except Exception as e:
            logger.error("Failed to process batch for service %s: %s", service, e)
        if i < len(services) - 1 and delay_seconds > 0:
            time.sleep(delay_seconds)

def run():
    """Initialize agents, consume alerts from Kafka, run pipeline sequentially, and publish postmortems."""
    shutdown_event.clear()  # Module-level Event persists across calls; reset state (e.g., between test runs)
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    WINDOW_SIZE_SECONDS = max(1, min(3600, int(os.getenv("WINDOW_SIZE_SECONDS", "30"))))
    MAX_ALERTS_PER_WINDOW_PER_SERVICE = max(1, min(10000, int(os.getenv("MAX_ALERTS_PER_WINDOW_PER_SERVICE", "100"))))

    import dspy
    lm = dspy.LM(
        f"gemini/{os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')}",
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
    log_consumer = get_consumer("raw-logs", group_id="postmortem-pipeline-logs")

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

            log_msg = log_consumer.poll(timeout=0.05)
            if log_msg and not log_msg.error():
                try:
                    batcher.add_log(json.loads(log_msg.value()))
                except Exception:
                    pass

            if time.time() >= window_start + window_size:
                batches = batcher.flush()
                if batches:
                    process_batches(batches, triage, correlation, rca, writer, SERVICE_BATCH_DELAY_SECONDS, batcher=batcher)
                    try:
                        consumer.commit()
                        log_consumer.commit()
                    except Exception as e:
                        logger.error("Failed to commit offsets after window flush: %s", e)
                window_start = time.time()

        batches = batcher.flush()
        if batches:
            process_batches(batches, triage, correlation, rca, writer, SERVICE_BATCH_DELAY_SECONDS, batcher=batcher)
    finally:
        consumer.close()
        log_consumer.close()
        triage.close()
        correlation.close()
        rca.close()
        writer.close()
        logger.info("Pipeline shut down cleanly")

if __name__ == "__main__":
    run()
