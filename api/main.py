"""FastAPI service for triggering incident analysis and retrieving postmortems."""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from redis.exceptions import RedisError
import threading

from infra.kafka_client import get_consumer, get_producer, produce_json
from infra.redis_client import get_redis_client

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

_redis_client = None
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
    """Consume postmortems from Kafka 'postmortems' topic, store JSON in Redis with TTL, and maintain postmortem:index set."""
    consumer = get_consumer("postmortems", group_id="postmortem-api-consumer")
    ttl = int(os.getenv("REDIS_TTL", "86400"))
    while not _stop_event.is_set():
        msg = consumer.poll(timeout=1.0)
        if msg is None or msg.error():
            continue
        try:
            data = json.loads(msg.value().decode("utf-8"))
            pid = data.get("incident_id", str(uuid.uuid4()))
            _redis_client.set(f"postmortem:{pid}", json.dumps(data), ex=ttl)
            _redis_client.sadd("postmortem:index", pid)
            logger.info("Stored postmortem %s", pid)
        except Exception as e:
            logger.error("Failed to store postmortem: %s", e)
    consumer.close()

@app.on_event("startup")
def startup():
    """Initialize Redis, Kafka producer, and start postmortem consumer thread; ping Redis for fail-fast on connection error."""
    global _consumer_thread, _producer, _redis_client
    _redis_client = get_redis_client()
    _redis_client.ping()  # fail fast if Redis is unreachable
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
    if _redis_client:
        _redis_client.close()

@app.get("/postmortems")
def list_postmortems():
    """Retrieve all cached postmortems from Redis; returns 503 on cache error; cleans stale entries from index."""
    try:
        ids = _redis_client.smembers("postmortem:index")
        ids = list(ids)[:1000]  # cap at 1000
        if not ids:
            return []
        values = _redis_client.mget([f"postmortem:{i}" for i in ids])
        stale = [ids[j] for j, v in enumerate(values) if v is None]
        if stale:
            _redis_client.srem("postmortem:index", *stale)
        return [json.loads(v) for v in values if v is not None]
    except RedisError as e:
        logger.error(f"Redis error in list_postmortems: {e}")
        raise HTTPException(status_code=503, detail="Cache unavailable")

@app.get("/postmortems/{incident_id}")
def get_postmortem(incident_id: str):
    """Retrieve a specific postmortem from Redis by incident ID; returns 404 if not found or 503 on cache error."""
    try:
        value = _redis_client.get(f"postmortem:{incident_id}")
        if value is None:
            raise HTTPException(status_code=404, detail="Postmortem not found")
        return json.loads(value)
    except RedisError as e:
        logger.error(f"Redis error in get_postmortem: {e}")
        raise HTTPException(status_code=503, detail="Cache unavailable")

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
