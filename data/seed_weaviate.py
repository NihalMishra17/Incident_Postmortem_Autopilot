"""Populates Weaviate with historical incident data for correlation and RCA."""
from infra.weaviate_client import get_client, init_schema, close_client


INCIDENTS = [
    {
        "title": "Payment service DB connection pool exhaustion",
        "root_cause": "Connection pool size too small for peak traffic; connections not released after timeout",
        "fix": "Increased pool size from 10 to 50, added connection timeout and retry logic",
        "service": "payment-service",
    },
    {
        "title": "Auth service memory leak under sustained load",
        "root_cause": "JWT token cache growing unbounded; no TTL or eviction policy configured",
        "fix": "Added LRU cache with 10k entry limit and 1-hour TTL; restart schedule added",
        "service": "auth-service",
    },
    {
        "title": "API gateway rate limiter false positives",
        "root_cause": "Rate limit counter shared across regions due to misconfigured Redis key prefix",
        "fix": "Added region prefix to Redis keys; limits now scoped per-region",
        "service": "api-gateway",
    },
    {
        "title": "Notification service Kafka consumer lag spike",
        "root_cause": "Consumer group rebalance storm triggered by rolling deploy with no graceful shutdown",
        "fix": "Added SIGTERM handler to commit offsets and leave group gracefully before pod shutdown",
        "service": "notification-service",
    },
    {
        "title": "Cache service stampede on cold start",
        "root_cause": "All cache keys expired simultaneously after restart; upstream services flooded order-service",
        "fix": "Implemented probabilistic early expiration (PER) and staggered TTLs across key groups",
        "service": "cache-service",
    },
]


if __name__ == "__main__":
    client = get_client()
    init_schema(client)

    collection = client.collections.get("PastIncident")

    has_data = len(collection.query.fetch_objects(limit=1).objects) > 0
    if has_data:
        print(f"PastIncident collection already contains data, skipping seed")
        close_client(client)
        exit(0)

    for incident in INCIDENTS:
        collection.data.insert(properties=incident)

    print(f"Seeded {len(INCIDENTS)} incidents into Weaviate")
    close_client(client)
