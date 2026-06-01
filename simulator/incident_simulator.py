"""Generates synthetic incidents and logs to Kafka for testing the postmortem pipeline."""
import argparse
import random
import signal
import time
import uuid
from datetime import datetime, timezone
from faker import Faker
from infra.kafka_client import get_producer, produce_json


SERVICES = [
    "api-gateway", "auth-service", "user-service", "order-service",
    "payment-service", "notification-service", "inventory-service",
    "analytics-service", "logging-service", "cache-service"
]
SEVERITIES = ["P1", "P2", "P3"]
SEVERITY_WEIGHTS = [10, 30, 60]
LOG_LEVELS = ["ERROR", "WARN", "INFO"]
LOG_LEVEL_WEIGHTS = [20, 30, 50]

fake = Faker()
running = True


def signal_handler(sig, frame):
    """Gracefully stops alert generation on SIGINT/SIGTERM."""
    global running
    print("\nShutting down simulator...")
    running = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Incident Simulator")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between alerts")
    parser.add_argument("--count", type=int, default=0, help="Number of alerts to generate (0=infinite)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    producer = get_producer()
    count = 0

    while running:
        alert_id = str(uuid.uuid4())
        service = random.choice(SERVICES)
        severity = random.choices(SEVERITIES, weights=SEVERITY_WEIGHTS)[0]
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        alert = {
            "alert_id": alert_id,
            "service": service,
            "severity": severity,
            "timestamp": timestamp,
            "message": fake.sentence()
        }

        produce_json(producer, "alerts", alert, key=alert_id)

        num_logs = random.randint(5, 20)
        for _ in range(num_logs):
            log = {
                "alert_id": alert_id,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "service": service,
                "level": random.choices(LOG_LEVELS, weights=LOG_LEVEL_WEIGHTS)[0],
                "message": fake.sentence() if random.random() > 0.3 else f"at {fake.file_path(extension='py')}:{random.randint(1, 500)}"
            }
            produce_json(producer, "raw-logs", log)

        producer.flush(timeout=10)
        count += 1
        print(f"Generated alert {count}: {severity} {service} ({num_logs} logs)")

        if args.count > 0 and count >= args.count:
            break

        time.sleep(args.interval)

    producer.flush()
    print("Simulator stopped")
