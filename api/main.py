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
from google import genai
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from infra.kafka_client import get_consumer, get_producer, produce_json
from infra.redis_client import get_redis_client
from infra.weaviate_client import get_client

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
_weaviate_client = None

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

class VerifyRequest(BaseModel):
    """Request payload for verifying postmortem root cause and fix."""
    confirmed_root_cause: str = Field(..., min_length=1, max_length=4096)
    confirmed_fix: str = Field(..., min_length=1, max_length=4096)
    verified_by: str = Field(..., min_length=1, max_length=128)

    @field_validator("confirmed_root_cause", "confirmed_fix")
    @classmethod
    def strip_and_validate(cls, v):
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field cannot be empty after stripping whitespace")
        return stripped

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
    global _consumer_thread, _producer, _redis_client, _weaviate_client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("Error: GEMINI_API_KEY environment variable is required")
        raise RuntimeError("GEMINI_API_KEY environment variable is required")
    _redis_client = get_redis_client()
    _redis_client.ping()  # fail fast if Redis is unreachable
    _weaviate_client = get_client()
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
    if _weaviate_client:
        _weaviate_client.close()
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

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception(lambda e: isinstance(e, ClientError) and e.code == 429),
    reraise=True,
)
def _embed_and_upsert_to_weaviate(postmortem: dict, confirmed_root_cause: str, confirmed_fix: str) -> None:
    """Embed postmortem with verified root cause and fix, then insert into Weaviate for future correlation.

    Combines the postmortem title with the confirmed root cause and fix, generates a vector embedding
    via Gemini `gemini-embedding-001`, and upserts a new entry into the Weaviate `PastIncident`
    collection. This is the only code path that writes verified incidents to Weaviate; AI-generated
    postmortems are never persisted to Weaviate until a human verifies them.

    Args:
        postmortem: Dict containing the AI-generated postmortem with keys 'title' (required) and
            'affected_services' (optional list or string).
        confirmed_root_cause: Engineer-verified root cause (non-blank, max 4096 chars).
        confirmed_fix: Engineer-verified fix description (non-blank, max 4096 chars).

    Raises:
        HTTPException: 503 if embedding generation fails or Weaviate insert fails.
    """
    title = postmortem["title"]
    text = f"{title}. {confirmed_root_cause}. {confirmed_fix}"

    api_key = os.getenv("GEMINI_API_KEY")
    genai_client = genai.Client(api_key=api_key)
    try:
        result = genai_client.models.embed_content(
            model="models/gemini-embedding-001", contents=text
        )
        vector = result.embeddings[0].values
    except Exception as e:
        logger.error(f"Embedding service error: {e}")
        raise HTTPException(status_code=503, detail="Embedding service unavailable")

    affected_services = postmortem.get("affected_services", [])
    if isinstance(affected_services, list):
        service_str = ", ".join(affected_services) if affected_services else "unknown"
    else:
        service_str = affected_services if affected_services else "unknown"

    try:
        collection = _weaviate_client.collections.get("PastIncident")
        collection.data.insert(
            properties={
                "title": title,
                "root_cause": confirmed_root_cause,
                "fix": confirmed_fix,
                "service": service_str,
            },
            vector=vector
        )
    except Exception as e:
        logger.error(f"Weaviate insert failed: {e}")
        raise HTTPException(status_code=503, detail="Vector store unavailable")

@app.patch("/postmortems/{incident_id}/verify")
def verify_postmortem(incident_id: str, req: VerifyRequest):
    """Verify a postmortem and persist confirmed root cause and fix to Weaviate.

    Accepts human-verified root cause and fix for an AI-generated postmortem, embeds them into
    Weaviate's `PastIncident` collection for future incident correlation, and updates the Redis
    cache with verification metadata. Prevents duplicate Weaviate writes by rejecting already-verified
    postmortems.

    Args:
        incident_id: UUID of the postmortem to verify.
        req: VerifyRequest with confirmed_root_cause, confirmed_fix, verified_by (all required).

    Returns:
        Updated postmortem dict with verified=true, verified_by, verified_at (ISO 8601),
        confirmed_root_cause, and confirmed_fix fields.

    Raises:
        HTTPException: 404 if incident_id not found in Redis cache.
        HTTPException: 409 if postmortem is already verified (prevents duplicate Weaviate writes).
        HTTPException: 500 if postmortem record is missing a title.
        HTTPException: 503 if Redis, Weaviate, or Gemini embedding service fails.
    """
    try:
        value = _redis_client.get(f"postmortem:{incident_id}")
        if value is None:
            raise HTTPException(status_code=404, detail="Postmortem not found")
        postmortem = json.loads(value)
    except RedisError as e:
        logger.error(f"Redis error in verify_postmortem: {e}")
        raise HTTPException(status_code=503, detail="Cache unavailable")

    if postmortem.get("verified") is True:
        raise HTTPException(status_code=409, detail="Postmortem already verified")

    if not postmortem.get("title"):
        raise HTTPException(status_code=500, detail="Postmortem record is missing a title")

    _embed_and_upsert_to_weaviate(postmortem, req.confirmed_root_cause, req.confirmed_fix)

    postmortem["verified"] = True
    postmortem["verified_by"] = req.verified_by
    postmortem["verified_at"] = datetime.now(timezone.utc).isoformat()
    postmortem["confirmed_root_cause"] = req.confirmed_root_cause
    postmortem["confirmed_fix"] = req.confirmed_fix

    try:
        ttl = int(os.getenv("REDIS_TTL", "86400"))
        _redis_client.set(f"postmortem:{incident_id}", json.dumps(postmortem), ex=ttl)
    except RedisError as e:
        logger.error(f"Redis error in verify_postmortem: {e}")
        raise HTTPException(status_code=503, detail="Cache unavailable")

    return postmortem
