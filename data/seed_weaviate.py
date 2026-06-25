"""Populates Weaviate with historical incident data for correlation and RCA."""
import json
import os
from pathlib import Path
from google import genai
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from infra.weaviate_client import get_client, init_schema, close_client


_JSON_PATH = Path(__file__).parent / "past_incidents.json"
with open(_JSON_PATH) as _f:
    INCIDENTS = json.load(_f)

_REQUIRED_FIELDS = {"title", "root_cause", "fix", "service"}
for _entry in INCIDENTS:
    _missing = _REQUIRED_FIELDS - set(_entry.keys())
    if _missing:
        raise ValueError(f"past_incidents.json entry missing fields: {_missing}")


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception(lambda e: isinstance(e, ClientError) and e.code == 429),
    reraise=True,
)
def _embed_text(genai_client, text: str) -> list[float]:
    """Embed text using Gemini with exponential backoff retry on rate limits."""
    result = genai_client.models.embed_content(
        model="models/gemini-embedding-001", contents=text
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
