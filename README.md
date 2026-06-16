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

Consumes alerts from the `alerts` topic and publishes postmortems to `postmortems`.

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
    │              Agent Pipeline (Kafka consumer)            │
    ├──────────────────────────────────────────────────────────┤
    │ TriageAgent: severity classification + Neo4j blast radius│
    │      ↓                                                    │
    │ CorrelationAgent: Weaviate near_vector (top-3)          │
    │      ↓                                                    │
    │ RCAAgent: DSPy ChainOfThought synthesis                  │
    │      ↓                                                    │
    │ PostmortemWriter: structured output → Kafka             │
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

1. **TriageAgent** — Classifies severity (P1→critical, P2→high, P3→medium) and queries Neo4j for affected services (3-hop blast radius via DEPENDS_ON|CALLS edges).

2. **CorrelationAgent** — Embeds alert description using Gemini `gemini-embedding-001`, searches Weaviate for top-3 similar past incidents.

3. **RCAAgent** — Synthesizes logs, dependency graph, and historical incidents using DSPy ChainOfThought and Gemini LLM.

4. **PostmortemWriter** — Generates structured postmortem object and publishes to Kafka `postmortems` topic.

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
