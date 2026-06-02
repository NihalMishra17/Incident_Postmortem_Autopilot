"""FastAPI service for triggering incident analysis and retrieving postmortems."""
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from infra.kafka_client import get_consumer, get_producer, produce_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Incident Postmortem API")

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

_MAX_POSTMORTEMS = 10_000
postmortems: dict = {}
postmortems_lock = threading.Lock()
_consumer_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_producer = None

class TriggerRequest(BaseModel):
    """Request payload for triggering postmortem analysis."""
    service: str = Field(..., min_length=1, max_length=128)
    severity: str = Field("P2", max_length=2)
    description: str = Field(..., min_length=1, max_length=4096)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v):
        if v not in ("P1", "P2", "P3"):
            raise ValueError("severity must be P1, P2, or P3")
        return v

def _consume_postmortems():
    """Listen for completed postmortems on Kafka and store in memory with FIFO eviction."""
    consumer = get_consumer("postmortems", group_id="postmortem-api-consumer")
    while not _stop_event.is_set():
        msg = consumer.poll(timeout=1.0)
        if msg is None or msg.error():
            continue
        try:
            data = json.loads(msg.value().decode("utf-8"))
            pid = data.get("incident_id", str(uuid.uuid4()))
            with postmortems_lock:
                # Evict oldest postmortem (FIFO) when cache exceeds limit
                if len(postmortems) >= _MAX_POSTMORTEMS:
                    postmortems.pop(next(iter(postmortems)))
                postmortems[pid] = data
            logger.info("Stored postmortem %s", pid)
        except Exception as e:
            logger.error("Failed to store postmortem: %s", e)
    consumer.close()

@app.on_event("startup")
def startup():
    global _consumer_thread, _producer
    _producer = get_producer()
    _consumer_thread = threading.Thread(target=_consume_postmortems, daemon=True)
    _consumer_thread.start()

@app.on_event("shutdown")
def shutdown():
    _stop_event.set()
    if _consumer_thread:
        _consumer_thread.join(timeout=5)
    if _producer:
        _producer.flush()

@app.get("/postmortems")
def list_postmortems():
    """Retrieve all cached postmortems."""
    with postmortems_lock:
        return list(postmortems.values())

@app.get("/postmortems/{incident_id}")
def get_postmortem(incident_id: str):
    """Retrieve a specific postmortem by incident ID or 404 if not found."""
    with postmortems_lock:
        pm = postmortems.get(incident_id)
    if not pm:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    return pm

@app.post("/postmortems/trigger", status_code=202)
def trigger_postmortem(req: TriggerRequest):
    """Create an alert, publish to Kafka, and return immediately (returns 202 Accepted)."""
    alert = {
        "alert_id": str(uuid.uuid4()),
        "service": req.service,
        "severity": req.severity,
        "message": req.description,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    produce_json(_producer, "alerts", alert)
    _producer.flush()
    return {"alert_id": alert["alert_id"], "status": "queued"}
