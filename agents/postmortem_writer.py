"""Postmortem writer that generates structured incident reports using DSPy and publishes to Kafka."""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List
import dspy
from pydantic import BaseModel
from weaviate.classes.query import MetadataQuery
import google.genai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from infra.kafka_client import get_producer, produce_json
from infra.weaviate_client import get_client

logger = logging.getLogger(__name__)

class FixCandidate(BaseModel):
    """Ranked fix suggestion with confidence score and historical reasoning."""
    fix: str
    confidence: float
    reasoning: str

class PostmortemSchema(BaseModel):
    """Validation schema for structured postmortem output."""
    title: str
    severity: str
    affected_services: str
    root_cause: str
    timeline: str
    remediation: str
    prevention: str
    suggested_fixes: List[FixCandidate]

class PostmortemSignature(dspy.Signature):
    """DSPy signature for structured incident postmortem generation."""
    alert_data: str = dspy.InputField()
    blast_radius: str = dspy.InputField()
    rca_result: str = dspy.InputField()
    correlated_incidents: str = dspy.InputField()
    title: str = dspy.OutputField(desc="Short descriptive incident title")
    root_cause: str = dspy.OutputField(desc="Root cause in 2-3 sentences")
    timeline: str = dspy.OutputField(desc="Bullet-point incident timeline anchored to the alert timestamp provided in alert_data")
    remediation: str = dspy.OutputField(desc="Steps taken to resolve the incident")
    prevention: str = dspy.OutputField(desc="Recommendations to prevent recurrence")

class PostmortemWriter:
    """Synthesizes alert analysis into a structured postmortem and publishes to Kafka."""
    def __init__(self):
        self.producer = get_producer()
        self.predictor = dspy.Predict(PostmortemSignature)
        self.weaviate_client = get_client()
        self.weaviate_collection = self.weaviate_client.collections.get("PastIncident")
        self.genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    # TODO: Extract dedup logic to shared utils module (agents/utils/dedup.py) — duplicated from correlation_agent.py
    def _normalize_fix(self, fix: str) -> str:
        """Normalize fix text: lowercase and collapse whitespace for case-insensitive deduplication."""
        return " ".join(fix.lower().split())

    def _jaccard(self, a: str, b: str) -> float:
        """Compute Jaccard similarity between two strings as token sets (intersection / union). Returns 1.0 if both are empty."""
        sa, sb = set(a.split()), set(b.split())
        if not sa and not sb:
            return 1.0
        return len(sa & sb) / len(sa | sb)

    def _deduplicate_fixes(self, candidates: list, threshold: float = 0.85) -> list:
        """Remove semantically similar fixes using two-phase dedup: exact match, then Jaccard; return up to 3 unique FixCandidate objects."""
        seen_normalized: list[str] = []
        unique: list = []
        for candidate in candidates:
            fix_text = candidate.fix
            norm = self._normalize_fix(fix_text)
            # Phase 1: reject exact normalized match (case-insensitive, whitespace-collapsed)
            if norm in seen_normalized:
                continue
            # Phase 2: reject semantically similar fixes (Jaccard token similarity >= 0.85)
            if any(self._jaccard(norm, s) >= threshold for s in seen_normalized):
                continue
            seen_normalized.append(norm)
            unique.append(candidate)
            if len(unique) == 3:
                break
        return unique

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _rank_fixes_from_weaviate(self, root_cause: str) -> list:
        """Rank fix suggestions using semantic search and deduplication.

        Over-fetches 10 similar incidents from Weaviate, applies two-phase deduplication
        (exact normalized match + Jaccard ≥ 0.85), and returns up to 3 unique FixCandidate
        objects ranked by vector similarity confidence. Falls back to single generic fix on error.

        Process:
        1. Embed root_cause via Gemini embedding model.
        2. Query PastIncident collection with limit=10 (over-fetch for dedup headroom).
        3. Build FixCandidate objects with confidence derived from cosine distance.
        4. Deduplicate using exact + Jaccard heuristic, return ≤ 3 unique.
        5. On any error, return fallback generic fix (confidence 0.3).

        Args:
            root_cause: Text description of the incident root cause to embed.

        Returns:
            List of ≤ 3 FixCandidate objects, ranked descending by confidence.
            Confidence is: 1.0 - (distance / 2.0), clamped to [0.0, 1.0].
        """
        try:
            # Embed root cause
            response = self.genai_client.models.embed_content(
                model="models/gemini-embedding-001", contents=root_cause
            )
            vector = response.embeddings[0].values

            # Query for similar incidents - over-fetch to allow for deduplication
            results = self.weaviate_collection.query.near_vector(
                near_vector=vector,
                limit=10,
                return_metadata=MetadataQuery(distance=True),
                return_properties=["fix", "title", "root_cause"]
            )

            # Build candidate list
            candidates = []
            for obj in results.objects:
                # Map cosine distance to confidence: distance 0 (perfect match) → confidence 1.0,
                # distance 2 (orthogonal) → confidence 0.0, clamped to [0.0, 1.0]
                confidence = max(0.0, min(1.0, 1.0 - (obj.metadata.distance / 2.0)))
                reasoning = f"Similar to: {obj.properties['title']} — {obj.properties['root_cause']}"
                fix = obj.properties["fix"]
                candidates.append(FixCandidate(fix=fix, confidence=confidence, reasoning=reasoning))

            # Deduplicate to return up to 3 unique fixes
            return self._deduplicate_fixes(candidates, threshold=0.85)

        except Exception as e:
            logger.warning("Failed to rank fixes from Weaviate: %s", e)
            # Return single fallback candidate
            return [
                FixCandidate(
                    fix="Inspect recent deployments and roll back if necessary",
                    confidence=0.3,
                    reasoning="Generated without historical correlation"
                )
            ]

    def process_batch(self, alerts: list[dict]) -> list[dict]:
        """Generate postmortems for all alerts and flush Kafka producer once per batch.

        Produces individual postmortems per alert, then calls producer.flush() once at the end
        to reduce network overhead vs flushing after each message.
        """
        postmortems = []
        for alert in alerts:
            try:
                service = str(alert.get("service", ""))[:128]
                message = str(alert.get("message", ""))[:2048]
                timestamp = str(alert.get("timestamp", ""))[:32]
                result = self.predictor(
                    alert_data=f"service={service} timestamp={timestamp} message={message}",
                    blast_radius=", ".join(alert.get("blast_radius", []))[:512],
                    rca_result=str(alert.get("rca_result", ""))[:4096],
                    correlated_incidents=str(alert.get("correlated_incidents", []))[:2048],
                )

                # Validate all required fields to prevent publishing malformed postmortems.
                required_fields = {
                    "title": getattr(result, "title", None),
                    "root_cause": getattr(result, "root_cause", None),
                    "timeline": getattr(result, "timeline", None),
                    "remediation": getattr(result, "remediation", None),
                    "prevention": getattr(result, "prevention", None),
                }
                missing_fields = [k for k, v in required_fields.items() if not v or not str(v).strip()]
                if missing_fields:
                    raise ValueError(f"DSPy output missing required fields: {', '.join(missing_fields)}")

                suggested_fixes = self._rank_fixes_from_weaviate(required_fields["root_cause"])

                postmortem = {
                    "incident_id": alert.get("alert_id", str(uuid.uuid4())),
                    "title": required_fields["title"],
                    "severity": alert.get("severity_level", "unknown"),
                    "service": alert.get("service") or (alert.get("blast_radius") or [""])[0] or "unknown",
                    "affected_services": alert.get("blast_radius", []),
                    "root_cause": required_fields["root_cause"],
                    "timeline": required_fields["timeline"],
                    "remediation": required_fields["remediation"],
                    "prevention": required_fields["prevention"],
                    "suggested_fixes": [f.model_dump() for f in suggested_fixes],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                produce_json(self.producer, "postmortems", postmortem)
                logger.info("Postmortem published for incident %s", postmortem["incident_id"])
                postmortems.append(postmortem)
            except Exception as e:
                logger.error("PostmortemWriter failed: %s", e)
                raise
        self.producer.flush()
        return postmortems

    def process(self, alert: dict) -> dict:
        return self.process_batch([alert])[0]

    def close(self):
        self.producer.flush()
        self.weaviate_client.close()
