"""Populates Weaviate with historical incident data for correlation and RCA."""
import os
from google import genai
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
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


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception(lambda e: isinstance(e, ClientError) and e.code == 429),
    reraise=True,
)
def _embed_text(genai_client, text: str) -> list[float]:
    """Embed text using Gemini with exponential backoff retry on rate limits."""
    result = genai_client.models.embed_content(
        model="models/text-embedding-004", contents=text
    )
    return result.embeddings[0].values


if __name__ == "__main__":
    client = get_client()
    init_schema(client)

    collection = client.collections.get("PastIncident")

    has_data = len(collection.query.fetch_objects(limit=1).objects) > 0
    if has_data:
        print(f"PastIncident collection already contains data, skipping seed")
        close_client(client)
        exit(0)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is required")
        close_client(client)
        exit(1)
    genai_client = genai.Client(api_key=api_key)

    for incident in INCIDENTS:
        text = f"{incident['title']}. {incident['root_cause']}. {incident['fix']}"
        vector = _embed_text(genai_client, text)
        collection.data.insert(properties=incident, vector=vector)

    print(f"Seeded {len(INCIDENTS)} incidents into Weaviate")
    close_client(client)
