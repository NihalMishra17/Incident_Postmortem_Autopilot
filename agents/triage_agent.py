"""Triage agent that classifies alert severity and computes blast radius via Neo4j graph traversal."""
import logging
from infra.neo4j_client import get_driver

logger = logging.getLogger(__name__)

SEVERITY_MAP = {"P1": "critical", "P2": "high", "P3": "medium"}

class TriageAgent:
    """Determines incident severity level and identifies affected services through Neo4j relationships."""
    def __init__(self):
        self.driver = get_driver()

    def process(self, alert: dict) -> dict:
        severity = SEVERITY_MAP.get(alert.get("severity", ""), "low")
        blast_radius = self._get_blast_radius(alert.get("service", ""))
        return {**alert, "severity_level": severity, "blast_radius": blast_radius}

    def _get_blast_radius(self, service: str) -> list[str]:
        """Query Neo4j to find all services within 3 hops via DEPENDS_ON or CALLS relationships."""
        if not service:
            return []
        query = """
            MATCH (s:Service {name: $service})-[:DEPENDS_ON|CALLS*1..3]-(affected:Service)
            WHERE affected.name <> $service
            RETURN DISTINCT affected.name AS name
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, service=service)
                return [r["name"] for r in result]
        except Exception as e:
            logger.warning("Neo4j blast radius query failed for %s: %s", service, e)
            return []

    def close(self):
        self.driver.close()
