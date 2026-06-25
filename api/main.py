"""FastAPI service for triggering incident analysis and retrieving postmortems."""
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent / ".env")
import logging_config
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator
from redis.exceptions import RedisError
import threading
from google import genai
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from prometheus_fastapi_instrumentator import Instrumentator

from infra.kafka_client import get_consumer, get_producer, produce_json
from infra.redis_client import get_redis_client
from infra.weaviate_client import get_client

logger = logging.getLogger(__name__)

_redis_client = None
_consumer_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_producer = None
_weaviate_client = None

def _do_startup():
    """Initialize Redis, Kafka producer, Weaviate client, and start the postmortem consumer thread."""
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

def _do_shutdown():
    """Shutdown Kafka consumer, producer, Weaviate client, and Redis client."""
    _stop_event.set()
    if _consumer_thread:
        _consumer_thread.join(timeout=5)
        if _consumer_thread.is_alive():
            logger.warning("Consumer thread did not terminate within timeout")
    if _producer:
        _producer.flush()
    if _weaviate_client:
        _weaviate_client.close()
    if _redis_client:
        _redis_client.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    _do_startup()
    yield
    _do_shutdown()

app = FastAPI(title="Incident Postmortem API", lifespan=lifespan)

instrumentator = Instrumentator(excluded_handlers=["/metrics"])
instrumentator.instrument(app)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

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
    """Request payload for verifying postmortem root cause and engineer-selected fix.

    Accepts human-verified root cause and one of three mutually-exclusive fix selection modes:
    - `selected_fix_index` (0, 1, or 2): Use one of the AI-ranked fix suggestions from postmortem.
    - `custom_fix`: Supply a custom fix not in the ranked suggestions.
    - `confirmed_fix` (deprecated): Legacy alias for `custom_fix`; treated as custom source.

    Exactly one fix field must be provided.
    """
    confirmed_root_cause: str = Field(..., min_length=1, max_length=4096)
    confirmed_fix: Optional[str] = Field(None, min_length=1, max_length=4096)
    selected_fix_index: Optional[int] = None
    custom_fix: Optional[str] = Field(None, min_length=1, max_length=4096)
    verified_by: str = Field(..., min_length=1, max_length=128)

    @field_validator("confirmed_root_cause")
    @classmethod
    def strip_and_validate_root_cause(cls, v):
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field cannot be empty after stripping whitespace")
        return stripped

    @field_validator("confirmed_fix", "custom_fix")
    @classmethod
    def strip_and_validate_fix_fields(cls, v):
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field cannot be empty after stripping whitespace")
        return stripped

    @model_validator(mode='after')
    def validate_fix_fields(self):
        """Validate that exactly one of confirmed_fix, selected_fix_index, custom_fix is provided."""
        fix_fields = [
            self.confirmed_fix is not None,
            self.selected_fix_index is not None,
            self.custom_fix is not None
        ]
        if sum(fix_fields) == 0:
            raise ValueError("Must provide one of: confirmed_fix, selected_fix_index, or custom_fix")
        if sum(fix_fields) > 1:
            raise ValueError("Cannot provide multiple fix fields; choose one of: confirmed_fix, selected_fix_index, or custom_fix")
        if self.selected_fix_index is not None and self.selected_fix_index not in {0, 1, 2}:
            raise ValueError("selected_fix_index must be 0, 1, or 2")
        return self

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
def _embed_and_upsert_to_weaviate(postmortem: dict, confirmed_root_cause: str, final_fix: str) -> None:
    """Embed engineer-verified postmortem and persist to Weaviate for future incident correlation.

    Combines the postmortem title, confirmed root cause, and selected fix into a single text,
    generates a vector embedding via Gemini `gemini-embedding-001`, and inserts a new entry
    into the Weaviate `PastIncident` collection. This is the only code path that writes verified
    incidents to Weaviate; AI-generated postmortems are never persisted until explicitly verified
    by an engineer. Verified incidents become the training data for ranking future fix suggestions.

    Args:
        postmortem: Dict containing the AI-generated postmortem with keys 'title' (required) and
            'affected_services' (optional list or string).
        confirmed_root_cause: Engineer-verified root cause (non-blank, max 4096 chars).
        final_fix: Engineer-verified or AI-ranked fix description (non-blank, max 4096 chars).

    Raises:
        HTTPException: 503 if embedding generation fails or Weaviate insert fails.
    """
    title = postmortem["title"]
    text = f"{title}. {confirmed_root_cause}. {final_fix}"

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
                "fix": final_fix,
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

    if not postmortem.get("suggested_fixes") or not isinstance(postmortem["suggested_fixes"], list) or len(postmortem["suggested_fixes"]) == 0:
        raise HTTPException(status_code=400, detail="Postmortem predates fix suggestions; re-trigger via /postmortems/trigger to regenerate.")

    # Resolve final fix from request: either one of the AI-ranked suggestions ("ranked")
    # or a custom/legacy fix provided by the engineer ("custom")
    if req.selected_fix_index is not None:
        if req.selected_fix_index >= len(postmortem["suggested_fixes"]):
            raise HTTPException(status_code=400, detail=f"selected_fix_index {req.selected_fix_index} out of bounds; postmortem has {len(postmortem['suggested_fixes'])} suggested fixes.")
        final_fix = postmortem["suggested_fixes"][req.selected_fix_index]["fix"]
        final_fix_source = "ranked"
    elif req.custom_fix is not None:
        final_fix = req.custom_fix
        final_fix_source = "custom"
    else:  # confirmed_fix (deprecated alias)
        final_fix = req.confirmed_fix
        final_fix_source = "custom"

    _embed_and_upsert_to_weaviate(postmortem, req.confirmed_root_cause, final_fix)

    postmortem["verified"] = True
    postmortem["verified_by"] = req.verified_by
    postmortem["verified_at"] = datetime.now(timezone.utc).isoformat()
    postmortem["confirmed_root_cause"] = req.confirmed_root_cause
    postmortem["final_fix"] = final_fix
    postmortem["final_fix_source"] = final_fix_source
    if req.confirmed_fix is not None:
        postmortem["confirmed_fix"] = req.confirmed_fix

    try:
        ttl = int(os.getenv("REDIS_TTL", "86400"))
        _redis_client.set(f"postmortem:{incident_id}", json.dumps(postmortem), ex=ttl)
    except RedisError as e:
        logger.error(f"Redis error in verify_postmortem: {e}")
        raise HTTPException(status_code=503, detail="Cache unavailable")

    return postmortem

# Expose Prometheus metrics endpoint; must be called after all route definitions to capture all handlers
instrumentator.expose(app, endpoint="/metrics")
