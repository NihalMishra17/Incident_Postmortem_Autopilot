import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from api.main import app


@pytest.fixture
def client():
    """Create FastAPI test client."""
    return TestClient(app)


def test_metrics_endpoint_returns_200(client):
    """GET /metrics should return HTTP 200."""
    response = client.get("/metrics")
    assert response.status_code == 200


def test_metrics_endpoint_returns_prometheus_format(client):
    """GET /metrics should return Prometheus text format with # HELP or # TYPE."""
    response = client.get("/metrics")
    body = response.text

    # Prometheus format includes metadata lines starting with # HELP or # TYPE
    assert "# HELP" in body or "# TYPE" in body, \
        "Response should contain Prometheus metric metadata (# HELP or # TYPE)"


def test_metrics_endpoint_contains_http_metrics(client):
    """GET /metrics should include HTTP request metrics from prometheus-fastapi-instrumentator."""
    # Make a request to another endpoint first to generate some metrics
    with patch("api.main._producer"):
        client.post(
            "/postmortems/trigger",
            json={
                "service": "test-service",
                "severity": "P2",
                "description": "Test alert",
            },
        )

    # Now check /metrics
    response = client.get("/metrics")
    body = response.text

    # The instrumentator should track HTTP request count and duration
    # Common metric names include http_requests_total, http_request_duration_seconds
    assert "http_request" in body.lower(), \
        "Metrics should include HTTP request metrics from instrumentator"


def test_metrics_endpoint_not_tracked_in_metrics(client):
    """GET /metrics should NOT appear in its own metrics (excluded_handlers works)."""
    # Make multiple requests to /metrics
    for _ in range(3):
        client.get("/metrics")

    # Get the final metrics
    response = client.get("/metrics")
    body = response.text

    # Parse the metrics to check if /metrics endpoint itself is tracked
    # The excluded_handlers should prevent /metrics from being tracked
    # We'll check by looking for path="/metrics" in the metrics output
    # This is a heuristic check - if metrics are tracked per-path, we should NOT see /metrics

    # Split into lines and look for metric entries with path="/metrics"
    lines = body.split("\n")
    for line in lines:
        # Skip comments
        if line.startswith("#"):
            continue
        # If this is a metric line with labels, check if it references /metrics
        if 'path="/metrics"' in line or "path='/metrics'" in line:
            # Check the metric name - if it's a counter/histogram for requests, this would mean
            # the /metrics endpoint is being tracked (which should NOT happen)
            if "http_request" in line.lower():
                pytest.fail(
                    "Metrics endpoint should not track itself, but found metrics for path=/metrics"
                )


def test_metrics_endpoint_content_type(client):
    """GET /metrics should return appropriate content type for Prometheus."""
    response = client.get("/metrics")

    # Prometheus expects text/plain or a version-specific media type
    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type or "text" in content_type, \
        f"Expected text-based content type for Prometheus metrics, got: {content_type}"
