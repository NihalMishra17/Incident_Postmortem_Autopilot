"""Correlation agent that finds similar past incidents via Weaviate semantic search."""
import logging
import os
from google import genai
from infra.weaviate_client import get_client

logger = logging.getLogger(__name__)

class CorrelationAgent:
    """Searches Weaviate for past incidents similar to current alert using vector embeddings."""
    def __init__(self):
        self.genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.weaviate_client = get_client()
        self.collection = self.weaviate_client.collections.get("PastIncident")

    def process(self, alert: dict) -> dict:
        query = f"{alert.get('message', '')} {alert.get('service', '')}"
        incidents = self._find_similar(query)
        return {**alert, "correlated_incidents": incidents}

    def _find_similar(self, query: str) -> list[dict]:
        """Embed alert text using Gemini and query Weaviate for top-3 similar past incidents."""
        try:
            result = self.genai_client.models.embed_content(
                model="models/text-embedding-004", contents=query
            )
            vector = result.embeddings[0].values
            response = self.collection.query.near_vector(
                near_vector=vector,
                limit=3,
                return_properties=["title", "root_cause", "fix", "service"],
            )
            return [obj.properties for obj in response.objects]
        except Exception as e:
            logger.warning("Correlation query failed: %s", e)
            return []

    def close(self):
        self.weaviate_client.close()
