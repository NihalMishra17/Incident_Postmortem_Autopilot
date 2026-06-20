"""RCA agent that performs root cause analysis using DSPy with Gemini."""
import logging
import os
import dspy

logger = logging.getLogger(__name__)

class RCASignature(dspy.Signature):
    """Analyze an incident and determine the root cause."""
    alert_data: str = dspy.InputField(desc="Alert details including service and message")
    blast_radius: str = dspy.InputField(desc="Comma-separated list of affected services")
    correlated_incidents: str = dspy.InputField(desc="JSON-formatted past similar incidents")
    root_cause_analysis: str = dspy.OutputField(desc="Detailed root cause analysis")

class RCAModule(dspy.Module):
    """DSPy module that applies chain-of-thought reasoning to root cause analysis."""
    def __init__(self):
        self.cot = dspy.ChainOfThought(RCASignature)

    def forward(self, alert_data, blast_radius, correlated_incidents):
        return self.cot(
            alert_data=alert_data,
            blast_radius=blast_radius,
            correlated_incidents=correlated_incidents,
        )

class RCAAgent:
    """Synthesizes alert, blast radius, and historical incidents into structured root cause analysis.

    Requires dspy.configure() to be called globally by the caller before instantiation.
    """
    def __init__(self):
        self.module = RCAModule()

    def process_batch(self, alerts: list[dict]) -> list[dict]:
        """Run DSPy ChainOfThought RCA individually per alert, truncating inputs to manage token limits."""
        results = []
        for alert in alerts:
            try:
                service = str(alert.get("service", ""))[:128]
                message = str(alert.get("message", ""))[:2048]
                result = self.module(
                    alert_data=f"service={service} message={message}",
                    blast_radius=", ".join(alert.get("blast_radius", []))[:512],
                    correlated_incidents=str(alert.get("correlated_incidents", []))[:2048],
                )
                if not getattr(result, "root_cause_analysis", None) or not str(result.root_cause_analysis).strip():
                    raise ValueError("DSPy output missing required field: root_cause_analysis")
                results.append({**alert, "rca_result": result.root_cause_analysis})
            except Exception as e:
                logger.warning("RCA failed for alert %s: %s", alert.get("alert_id"), e)
                results.append({**alert, "rca_result": "RCA unavailable due to processing error"})
        return results

    def process(self, alert: dict) -> dict:
        return self.process_batch([alert])[0]

    def close(self):
        pass
