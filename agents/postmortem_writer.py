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

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _rank_fixes_from_weaviate(self, root_cause: str) -> list:
        """Embed root cause and search Weaviate for semantically similar incidents to rank fix candidates.

        Generates a vector embedding of the provided root cause, queries the PastIncident
        collection for the 3 most similar verified incidents using cosine distance, and
        derives fix suggestions ranked by similarity confidence. Returns exactly 3 candidates;
        pads with low-confidence fallbacks if fewer than 3 are found.

        Args:
            root_cause: Text description of the incident root cause to embed.

        Returns:
            List of exactly 3 FixCandidate objects, ranked descending by confidence.
            Confidence is derived from cosine distance: 1.0 - (distance / 2.0), bounded [0.0, 1.0].
        """
        try:
            # Embed root cause
            response = self.genai_client.models.embed_content(
                model="models/gemini-embedding-001", contents=root_cause
            )
            vector = response.embeddings[0].values

            # Query for similar incidents
            results = self.weaviate_collection.query.near_vector(
                near_vector=vector,
                limit=3,
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

            # Pad to 3 with fallback if needed
            while len(candidates) < 3:
                candidates.append(
                    FixCandidate(
                        fix="Inspect recent deployments and roll back if necessary",
                        confidence=0.3,
                        reasoning="Generated without historical correlation"
                    )
                )

            return candidates

        except Exception as e:
            logger.warning("Failed to rank fixes from Weaviate: %s", e)
            # Return 3 fallback candidates
            return [
                FixCandidate(
                    fix="Inspect recent deployments and roll back if necessary",
                    confidence=0.3,
                    reasoning="Generated without historical correlation"
                )
            ] * 3

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
