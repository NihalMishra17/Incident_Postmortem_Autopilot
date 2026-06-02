"""Postmortem writer that generates structured incident reports using DSPy and publishes to Kafka."""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
import dspy
from pydantic import BaseModel
from infra.kafka_client import get_producer, produce_json

logger = logging.getLogger(__name__)

class PostmortemSchema(BaseModel):
    """Validation schema for structured postmortem output."""
    title: str
    severity: str
    affected_services: str
    root_cause: str
    timeline: str
    remediation: str
    prevention: str

class PostmortemSignature(dspy.Signature):
    """DSPy signature for structured incident postmortem generation."""
    alert_data: str = dspy.InputField()
    blast_radius: str = dspy.InputField()
    rca_result: str = dspy.InputField()
    correlated_incidents: str = dspy.InputField()
    title: str = dspy.OutputField(desc="Short descriptive incident title")
    root_cause: str = dspy.OutputField(desc="Root cause in 2-3 sentences")
    timeline: str = dspy.OutputField(desc="Bullet-point incident timeline")
    remediation: str = dspy.OutputField(desc="Steps taken to resolve the incident")
    prevention: str = dspy.OutputField(desc="Recommendations to prevent recurrence")

class PostmortemWriter:
    """Synthesizes alert analysis into a structured postmortem and publishes to Kafka."""
    def __init__(self):
        self.producer = get_producer()
        self.predictor = dspy.Predict(PostmortemSignature)

    def process(self, alert: dict) -> dict:
        """Invoke DSPy prediction, format postmortem, and publish to Kafka with optimistic flushing."""
        try:
            # Truncate inputs to manage token limits
            service = str(alert.get("service", ""))[:128]
            message = str(alert.get("message", ""))[:2048]
            result = self.predictor(
                alert_data=f"service={service} message={message}",
                blast_radius=", ".join(alert.get("blast_radius", []))[:512],
                rca_result=str(alert.get("rca_result", ""))[:4096],
                correlated_incidents=str(alert.get("correlated_incidents", []))[:2048],
            )
            postmortem = {
                "incident_id": alert.get("alert_id", str(uuid.uuid4())),
                "title": result.title,
                "severity": alert.get("severity_level", "unknown"),
                "affected_services": alert.get("blast_radius", []),
                "root_cause": result.root_cause,
                "timeline": result.timeline,
                "remediation": result.remediation,
                "prevention": result.prevention,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            produce_json(self.producer, "postmortems", postmortem)
            self.producer.flush()
            logger.info("Postmortem published for incident %s", postmortem["incident_id"])
            return postmortem
        except Exception as e:
            logger.error("PostmortemWriter failed: %s", e)
            raise

    def close(self):
        self.producer.flush()
