"""Generates synthetic incidents and logs to Kafka for testing the postmortem pipeline."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import os
from dotenv import dotenv_values
for _k, _v in dotenv_values(Path(__file__).parent.parent / ".env").items():
    if not os.environ.get(_k):
        os.environ[_k] = _v or ""
import argparse
import random
import signal
import time
import uuid
from datetime import datetime, timezone, timedelta
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

FAILURE_SCENARIOS = {
    "kafka_lag": {
        "alert_message": "Consumer group '{consumer_group}' lag on topic '{topic}' exceeded {lag} messages (partition {partition})",
        "log_templates": [
            "WARN  KafkaConsumer - Consumer group {consumer_group} lag={lag} on {topic}:{partition}",
            "ERROR KafkaConsumer - Offset commit failed for group {consumer_group}: COORDINATOR_NOT_AVAILABLE",
            "WARN  KafkaConsumer - Rebalance triggered, {rebalance_count} partitions reassigned",
            "ERROR KafkaConsumer - fetch failed: {topic}:{partition} OFFSET_OUT_OF_RANGE",
            "WARN  KafkaProducer - Message queue full, waiting for broker (lag={lag})",
            "ERROR KafkaConsumer - Poll timeout after {poll_timeout_ms}ms, lag still {lag}",
            "WARN  KafkaAdmin   - Under-replicated partitions detected: {topic}:{partition}",
        ],
        "param_generators": {
            "consumer_group": lambda: random.choice(["postmortem-pipeline", "analytics-consumer", "audit-consumer"]),
            "topic": lambda: random.choice(["alerts", "raw-logs", "postmortems", "events"]),
            "lag": lambda: random.randint(8000, 80000),
            "partition": lambda: random.randint(0, 11),
            "rebalance_count": lambda: random.randint(2, 8),
            "poll_timeout_ms": lambda: random.choice([30000, 60000]),
        },
    },
    "db_pool_exhaustion": {
        "alert_message": "Database connection pool exhausted on {db_host}: {active_conns}/{pool_size} connections active",
        "log_templates": [
            "ERROR HikariPool-1 - Connection is not available, request timed out after {wait_timeout_ms}ms",
            "WARN  HikariPool-1 - Pool stats (total={pool_size}, active={active_conns}, idle=0, waiting={waiting})",
            "ERROR JDBC         - Timeout waiting for connection from pool after {wait_timeout_ms}ms",
            "WARN  HikariPool-1 - Apparent connection leak detected on {db_host}",
            "ERROR DataSource   - getConnection() failed: connection pool exhausted ({active_conns} active)",
            "ERROR HikariPool-1 - Connection acquisition timed out; check for connection leaks",
            "WARN  DB           - Slow query detected on {db_host}: {query_time_ms}ms (threshold=500ms)",
        ],
        "param_generators": {
            "db_host": lambda: random.choice(["postgres-primary:5432", "mysql-01:3306", "postgres-replica:5432"]),
            "pool_size": lambda: random.randint(10, 30),
            "active_conns": lambda: random.randint(28, 30),
            "waiting": lambda: random.randint(5, 40),
            "wait_timeout_ms": lambda: random.choice([30000, 60000]),
            "query_time_ms": lambda: random.randint(2000, 15000),
        },
    },
    "memory_pressure": {
        "alert_message": "Heap usage at {heap_pct}% on {pod_name}: {heap_used_mb}MB/{heap_max_mb}MB, GC pause {gc_pause_ms}ms",
        "log_templates": [
            "WARN  GC            - Full GC pause {gc_pause_ms}ms, heap after={heap_used_mb}MB",
            "ERROR JVM           - OutOfMemoryError: Java heap space on {pod_name}",
            "WARN  MemoryMonitor - Heap usage {heap_pct}% exceeds warning threshold (80%)",
            "ERROR Allocator     - Failed to allocate {alloc_mb}MB: insufficient heap",
            "WARN  GC            - Old gen occupancy {heap_pct}%, promotion failure imminent",
            "ERROR Runtime       - GC overhead limit exceeded: {gc_pause_ms}ms pause in last 5s",
            "WARN  Cache         - Evicting {evict_count} entries due to memory pressure on {pod_name}",
        ],
        "param_generators": {
            "pod_name": lambda: f"{random.choice(['api-gateway', 'order-service', 'auth-service'])}-{random.randint(1,3)}",
            "heap_used_mb": lambda: random.randint(3500, 4000),
            "heap_max_mb": lambda: 4096,
            "heap_pct": lambda: random.randint(85, 98),
            "gc_pause_ms": lambda: random.randint(800, 5000),
            "alloc_mb": lambda: random.randint(50, 500),
            "evict_count": lambda: random.randint(1000, 10000),
        },
    },
    "http_5xx_cascade": {
        "alert_message": "HTTP {status_code} error rate {error_rate}% on {endpoint} — upstream {upstream_service} latency {response_time_ms}ms",
        "log_templates": [
            "ERROR HTTP         - {status_code} {endpoint} upstream={upstream_service} latency={response_time_ms}ms",
            "WARN  CircuitBreaker- Half-open state for {upstream_service}: {fail_count} failures in 60s",
            "ERROR Proxy        - Upstream {upstream_service} returned {status_code} after {response_time_ms}ms",
            "WARN  RateLimiter  - {endpoint} request rate {req_per_sec} rps exceeds limit",
            "ERROR LoadBalancer - All {upstream_service} instances unhealthy, circuit OPEN",
            "WARN  HTTP         - Retry {retry_num}/3 for {endpoint}: previous attempt {status_code}",
            "ERROR Nginx        - Upstream timed out ({response_time_ms}ms) while reading response from {upstream_service}",
        ],
        "param_generators": {
            "status_code": lambda: random.choice([502, 503, 504]),
            "endpoint": lambda: random.choice(["/api/v1/orders", "/api/v1/payments", "/api/v1/users", "/api/v1/inventory"]),
            "upstream_service": lambda: random.choice(["payment-service", "inventory-service", "auth-service", "order-service"]),
            "response_time_ms": lambda: random.randint(5000, 30000),
            "error_rate": lambda: random.randint(25, 95),
            "fail_count": lambda: random.randint(10, 50),
            "req_per_sec": lambda: random.randint(500, 5000),
            "retry_num": lambda: random.randint(1, 3),
        },
    },
    "timeout_storm": {
        "alert_message": "Timeout storm on {downstream_service}: {timeout_count} timeouts in 60s, circuit {circuit_state}",
        "log_templates": [
            "ERROR Client       - Request to {downstream_service} timed out after {timeout_ms}ms (attempt {retry_num}/{max_retries})",
            "WARN  CircuitBreaker- {downstream_service} failure rate {fail_rate}%, tripping circuit breaker",
            "ERROR Resilience4j - CircuitBreaker '{downstream_service}' state: OPEN after {fail_count} failures",
            "WARN  ThreadPool   - Executor queue full ({queue_size} pending): {downstream_service} calls backing up",
            "ERROR HTTP         - Connection pool to {downstream_service} exhausted: {timeout_count} pending",
            "WARN  Retry        - Retry #{retry_num} to {downstream_service} after {timeout_ms}ms backoff",
            "ERROR Gateway      - Cascading timeout: {downstream_service} -> {upstream_service} chain broken",
        ],
        "param_generators": {
            "downstream_service": lambda: random.choice(["payment-service", "notification-service", "analytics-service"]),
            "upstream_service": lambda: random.choice(["api-gateway", "order-service", "user-service"]),
            "timeout_ms": lambda: random.choice([5000, 10000, 30000]),
            "retry_num": lambda: random.randint(1, 5),
            "max_retries": lambda: 5,
            "circuit_state": lambda: random.choice(["OPEN", "HALF_OPEN"]),
            "timeout_count": lambda: random.randint(50, 500),
            "fail_rate": lambda: random.randint(60, 100),
            "fail_count": lambda: random.randint(10, 50),
            "queue_size": lambda: random.randint(100, 1000),
        },
    },
}

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

        # Pick a random scenario
        scenario_key = random.choice(list(FAILURE_SCENARIOS.keys()))
        scenario = FAILURE_SCENARIOS[scenario_key]

        # Generate params for the scenario
        params = {k: v() for k, v in scenario["param_generators"].items()}

        # Parse alert timestamp to datetime
        alert_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Build alert with scenario message
        alert = {
            "alert_id": alert_id,
            "service": service,
            "severity": severity,
            "timestamp": timestamp,
            "message": scenario["alert_message"].format(**params)
        }

        produce_json(producer, "alerts", alert, key=alert_id)

        # Generate logs using scenario templates
        num_logs = random.randint(5, 20)
        for _ in range(num_logs):
            log_template = random.choice(scenario["log_templates"])
            log_message = log_template.format(**params)
            log_timestamp = (alert_dt - timedelta(seconds=random.randint(1, 20))).isoformat().replace("+00:00", "Z")

            log = {
                "alert_id": alert_id,
                "timestamp": log_timestamp,
                "service": service,
                "level": random.choices(LOG_LEVELS, weights=LOG_LEVEL_WEIGHTS)[0],
                "message": log_message
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
