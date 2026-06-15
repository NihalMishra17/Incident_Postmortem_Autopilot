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

Starts Kafka, Weaviate, and Neo4j on their default ports.

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
    ┌────▼──────────┐
    │   FastAPI     │
    │   (cache +    │
    │    REST API)  │
    └───────────────┘
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

Returns a specific postmortem.

### POST `/postmortems/trigger`

Triggers postmortem analysis for a new alert.

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
  "status": "processing"
}
```

## Agent Flow

1. **TriageAgent** — Classifies severity (P1→critical, P2→high, P3→medium) and queries Neo4j for affected services (3-hop blast radius via DEPENDS_ON|CALLS edges).

2. **CorrelationAgent** — Embeds alert description using Gemini `text-embedding-004`, searches Weaviate for top-3 similar past incidents.

3. **RCAAgent** — Synthesizes logs, dependency graph, and historical incidents using DSPy ChainOfThought and Gemini LLM.

4. **PostmortemWriter** — Generates structured postmortem object and publishes to Kafka `postmortems` topic.

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

# Gemini API
GEMINI_API_KEY=<your-api-key>
GEMINI_MODEL=gemini-2.0-flash

# API Configuration
CORS_ORIGINS=http://localhost:3000
```

## Known Limitations

- **In-memory cache** — Postmortems are cached in the FastAPI process and lost on restart. For persistence, integrate a database.
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
