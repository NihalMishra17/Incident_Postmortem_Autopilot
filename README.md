# Incident Postmortem Autopilot

Event-driven multi-agent system that autonomously generates incident postmortems from Kafka alerts. Each agent performs a specialized task: severity classification, blast radius computation, incident correlation, root cause analysis, and structured postmortem generation.

## Stack

- **Kafka** — Event streaming (alerts, postmortems topics)
- **Weaviate** — Vector database for semantic incident correlation
- **Neo4j** — Service dependency graph (blast radius traversal)
- **DSPy** — LLM-powered root cause analysis and postmortem synthesis
- **Gemini** — Embeddings (text-embedding-004) and LLM (gemini-2.0-flash)
- **FastAPI** — REST API for triggering analysis and retrieving postmortems

## Quickstart

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Start infrastructure

```bash
docker-compose up -d
```

Starts Kafka, Weaviate, Neo4j, and Redis on their default ports. Redis provides persistent caching with TTL-based expiration.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Seed data

```bash
# Seed Neo4j with service dependency graph
python infra/neo4j_client.py

# Seed Weaviate with past incidents and embeddings
python data/seed_weaviate.py
```

### 5. Start the agent pipeline

```bash
python -m agents.pipeline
```

Consumes alerts from the `alerts` topic, windows them in 30-second batches per service, and publishes postmortems to `postmortems`. Use `WINDOW_SIZE_SECONDS=5` for faster local testing.

```bash
WINDOW_SIZE_SECONDS=5 python -m agents.pipeline
```

### 6. Start the API server

```bash
uvicorn api.main:app --reload
```

Listens on `http://localhost:8000`.

### 7. Trigger a test alert

```bash
python simulator/incident_simulator.py --count 1
```

Or via API:

```bash
curl -X POST http://localhost:8000/postmortems/trigger \
  -H "Content-Type: application/json" \
  -d '{"service": "auth-service", "severity": "P1", "description": "High error rate"}'
```

### 8. Query postmortems

```bash
curl http://localhost:8000/postmortems
curl http://localhost:8000/postmortems/{incident_id}
```

## Architecture

```
┌─────────────────┐
│   Simulator     │
│ (Kafka producer)│
└────────┬────────┘
         │
    alerts topic
         │
    ┌────▼────────────────────────────────────────────────────┐
    │         Agent Pipeline (windowed Kafka consumer)        │
    ├──────────────────────────────────────────────────────────┤
    │ AlertBatcher: 30s tumbling window per service             │
    │      ↓ (on window close)                                  │
    │ TriageAgent: severity classification + Neo4j blast radius│
    │      ↓                                                    │
    │ CorrelationAgent: 1 embedding/batch → Weaviate (top-3)  │
    │      ↓                                                    │
    │ RCAAgent: DSPy ChainOfThought synthesis                  │
    │      ↓                                                    │
    │ PostmortemWriter: 1 flush/batch → Kafka                 │
    └────┬─────────────────────────────────────────────────────┘
         │
postmortems topic
         │
    ┌────▼──────────────────┐
    │   FastAPI (REST API)  │
    │        ↓              │
    │   Redis (persistent   │
    │   cache, TTL)         │
    └───────────────────────┘
```

Alerts accumulate per-service over `WINDOW_SIZE_SECONDS` (default 30). When a window closes, all agents process the batch at once, reducing redundant embedding and LLM calls. `MAX_ALERTS_PER_WINDOW_PER_SERVICE` (default 100) caps the batch size.

## Kafka Topics

| Topic          | Producer            | Consumer      | Schema                                                 |
|----------------|---------------------|---------------|--------------------------------------------------------|
| `alerts`       | Simulator / API     | Triage Agent  | `{alert_id, service, severity, timestamp, message}`    |
| `postmortems`  | Postmortem Writer   | FastAPI       | `{incident_id, title, root_cause, fix, timeline, ...}` |

## API Endpoints

### GET `/postmortems`

Returns all cached postmortems.

**Response:**
```json
{
  "postmortems": [
    {
      "incident_id": "...",
      "title": "Database connection pool exhaustion",
      "root_cause": "...",
      "fix": "...",
      "timeline": [...],
      "service": "api-gateway"
    }
  ]
}
```

### GET `/postmortems/{incident_id}`

Returns a specific postmortem by ID.

### POST `/postmortems/trigger`

Triggers postmortem analysis for a new alert (returns 202 Accepted immediately).

**Request:**
```json
{
  "service": "auth-service",
  "severity": "P1",
  "description": "Database connection failures"
}
```

**Response:**
```json
{
  "alert_id": "...",
  "status": "queued"
}
```

### PATCH `/postmortems/{incident_id}/verify`

Verifies an AI-generated postmortem with engineer-confirmed root cause and fix. Embeds the verified data into Weaviate for future incident correlation. Only the first verification is persisted to Weaviate; subsequent attempts on the same postmortem are rejected with 409 Conflict.

**Request:**
```json
{
  "confirmed_root_cause": "Max connections reached due to connection leak in ORM layer",
  "confirmed_fix": "Patched connection cleanup and deployed hotfix to production",
  "verified_by": "john.doe@example.com"
}
```

**Response (200 OK):**
```json
{
  "incident_id": "...",
  "title": "Database connection pool exhaustion",
  "root_cause": "...",
  "fix": "...",
  "affected_services": ["api-gateway", "user-service"],
  "verified": true,
  "verified_by": "john.doe@example.com",
  "verified_at": "2026-06-16T14:30:00Z",
  "confirmed_root_cause": "Max connections reached due to connection leak in ORM layer",
  "confirmed_fix": "Patched connection cleanup and deployed hotfix to production"
}
```

**Error Responses:**
- `404 Not Found` — incident_id not found in cache
- `409 Conflict` — postmortem already verified (prevents duplicate Weaviate entries)
- `500 Internal Server Error` — postmortem record missing title
- `503 Service Unavailable` — Redis, Weaviate, or Gemini embedding service unavailable

## Agent Flow

Alerts are windowed per-service (default 30 seconds). Within each window:

1. **TriageAgent** — Classifies severity per-alert (P1→critical, P2→high, P3→medium) and queries Neo4j for affected services (3-hop blast radius via DEPENDS_ON|CALLS edges).

2. **CorrelationAgent** — Embeds a single concatenated query for the entire batch using Gemini `gemini-embedding-001`, searches Weaviate for top-3 similar past incidents, and attaches results to all alerts.

3. **RCAAgent** — Runs DSPy ChainOfThought per-alert to synthesize logs, dependency graph, and correlated incidents.

4. **PostmortemWriter** — Generates structured postmortem per-alert and flushes Kafka producer once per batch to reduce network round-trips.

## Human Verification Loop

AI-generated postmortems are cached in Redis but **never** written to Weaviate until a human verifies them. The verification endpoint (`PATCH /postmortems/{incident_id}/verify`) accepts engineer-confirmed root cause and fix, embeds them, and upserts a single entry into the Weaviate `PastIncident` collection. This is the **only** code path in the repo that writes verified incidents to Weaviate (besides the one-time `data/seed_weaviate.py` seed script). Duplicate verification is prevented by rejecting postmortems that are already marked `verified=true` (409 Conflict).

## Environment Variables

```bash
# Neo4j Graph Database
NEO4J_AUTH=neo4j/neo4jpassword
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4jpassword

# Kafka Event Streaming
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Alert Windowing (Pipeline)
WINDOW_SIZE_SECONDS=30                      # Tumbling window duration (1-3600 sec)
MAX_ALERTS_PER_WINDOW_PER_SERVICE=100       # Max alerts per service per window (1-10000)
SERVICE_BATCH_DELAY_SECONDS=1               # Seconds between service batch LLM calls to avoid rate limits (0-10)

# Weaviate Vector Database
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080

# Gemini API (required for embeddings and LLM)
GEMINI_API_KEY=<your-api-key>
GEMINI_MODEL=gemini-2.0-flash

# Redis Cache
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_TTL=86400

# API Configuration
CORS_ORIGINS=http://localhost:3000
```

## Observability

**Structured Logging** — All application logs (agents and API) emit JSON to stdout via structlog, enabling container aggregation and log searching.

**Prometheus Metrics** — The FastAPI service exposes request latency, throughput, and error rates at `GET /metrics` (Prometheus-compatible format). In production, restrict `/metrics` to internal networks via a reverse proxy or network policies.

## Known Limitations

- **Single-instance pipeline** — The agent pipeline runs on one process. For horizontal scaling, use Kafka consumer groups.
- **No API rate limiting** — API endpoints are not rate-limited. Add throttling for production use.
- **Synchronous processing** — Agents process alerts sequentially. For high-throughput scenarios, parallelize via multiple Kafka partitions and consumer group instances.

## Gemini Rate Limit Handling

The **CorrelationAgent** and **RCAAgent** implement exponential backoff retry logic using Tenacity for Gemini API rate limits (HTTP 429). Requests are retried up to 5 times with backoff between 1–60 seconds. Data seeding via `seed_weaviate.py` also uses the same retry mechanism.

## Development

### Project Structure

```
agents/              # Multi-agent pipeline
├── triage_agent.py
├── correlation_agent.py
├── rca_agent.py
├── postmortem_writer.py
└── pipeline.py

infra/               # Infrastructure clients
├── kafka_client.py
├── neo4j_client.py
└── weaviate_client.py

api/                 # FastAPI service
└── main.py

simulator/           # Test alert generator
└── incident_simulator.py

data/                # Data seeding
└── seed_weaviate.py

docker-compose.yml   # Local infrastructure
```

### Testing

Run the simulator to trigger alerts:

```bash
python simulator/incident_simulator.py --count 5 --interval 2
```

Monitor pipeline logs:

```bash
python -m agents.pipeline
```

Check API cache and query postmortems as they arrive.

### Frontend Tests

Run the React component test suite (Vitest 2.x + React Testing Library + happy-dom):

```bash
cd frontend && npm run test
```

54 tests across 9 files covering ThemeProvider, BlastRadiusGraph, FixCandidateList, VerifyPanel, IncidentFeed, and PostmortemDetail components.
