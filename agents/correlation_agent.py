"""Correlation agent that finds similar past incidents via Weaviate semantic search."""
import logging
import os
from google import genai
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from infra.weaviate_client import get_client

logger = logging.getLogger(__name__)

class CorrelationAgent:
    """Searches Weaviate for past incidents similar to current alert using vector embeddings."""
    def __init__(self):
        self.genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.weaviate_client = get_client()
        self.collection = self.weaviate_client.collections.get("PastIncident")

    def process_batch(self, alerts: list[dict]) -> list[dict]:
        """Embed batch query once, then attach correlated incidents to all alerts for efficiency.

        Concatenates all messages and services into a single query to share one embedding call.
        """
        query_parts = []
        for alert in alerts:
            query_parts.append(alert.get('message', ''))
            query_parts.append(alert.get('service', ''))
        query = ' '.join(query_parts)[:4096]
        incidents = self._find_similar(query)
        return [{**alert, "correlated_incidents": incidents} for alert in alerts]

    def process(self, alert: dict) -> dict:
        return self.process_batch([alert])[0]

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception(lambda e: isinstance(e, ClientError) and e.code == 429),
        reraise=True,
    )
    def _embed_query(self, query: str) -> list[float]:
        """Embed query text using Gemini with exponential backoff retry on rate limits."""
        result = self.genai_client.models.embed_content(
            model="models/gemini-embedding-001", contents=query
        )
        return result.embeddings[0].values

    # TODO: Extract dedup logic to shared utils module (agents/utils/dedup.py) — duplicated in postmortem_writer.py
    def _normalize_fix(self, fix: str) -> str:
        """Lowercase and collapse whitespace for case-insensitive fix deduplication."""
        return " ".join(fix.lower().split())

    def _jaccard(self, a: str, b: str) -> float:
        """Compute Jaccard similarity between two whitespace-split token sets."""
        sa, sb = set(a.split()), set(b.split())
        if not sa and not sb:
            return 1.0
        return len(sa & sb) / len(sa | sb)

    def _deduplicate_fixes(self, incidents: list[dict], threshold: float = 0.85) -> list[dict]:
        """Remove semantically similar fixes (exact then Jaccard), return up to 3 unique incidents."""
        seen_normalized: list[str] = []
        unique: list[dict] = []
        for inc in incidents:
            fix = inc.get("fix", "") or ""
            norm = self._normalize_fix(fix)
            # Phase 1: exact normalized match
            if norm in seen_normalized:
                continue
            # Phase 2: Jaccard similarity against all seen
            if any(self._jaccard(norm, s) >= threshold for s in seen_normalized):
                continue
            seen_normalized.append(norm)
            unique.append(inc)
            if len(unique) == 3:
                break
        return unique

    def _find_similar(self, query: str) -> list[dict]:
        """Embed alert text using Gemini and query Weaviate for top-3 similar past incidents."""
        try:
            vector = self._embed_query(query)
            response = self.collection.query.near_vector(
                near_vector=vector,
                limit=10,
                return_properties=["title", "root_cause", "fix", "service"],
            )
            results = [obj.properties for obj in response.objects]
            return self._deduplicate_fixes(results)
        except Exception as e:
            logger.warning("Correlation query failed: %s", e)
            return []

    def close(self):
        self.weaviate_client.close()
