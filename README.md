# Incident Postmortem Autopilot

Event-driven multi-agent system that autonomously generates incident postmortems from Kafka alerts.

## Stack

- **Kafka** - Event streaming
- **PyFlink** - Stream processing
- **Weaviate** - Vector database for incident correlation
- **Neo4j** - Service dependency graph
- **DSPy** - LLM-based postmortem generation
- **FastAPI** - REST API
- **React** - AI-generated UI

## Quickstart

1. **Copy environment file**
   ```bash
   cp .env.example .env
   ```

2. **Start infrastructure**
   ```bash
   docker-compose up -d
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Seed data**
   ```bash
   python infra/neo4j_client.py
   python data/seed_weaviate.py
   ```

5. **Run incident simulator**
   ```bash
   python simulator/incident_simulator.py --interval 10
   ```

## Kafka Topics

| Topic          | Producer       | Consumer      | Schema                                           |
|----------------|----------------|---------------|--------------------------------------------------|
| `raw-logs`     | Simulator      | Agents        | `{alert_id, timestamp, service, level, message}` |
| `alerts`       | Simulator      | Triage Agent  | `{alert_id, service, severity, timestamp, message}` |
| `postmortems`  | Writer Agent   | FastAPI       | `{incident_id, title, root_cause, fix, ...}`     |

## Architecture

```
Simulator → Kafka (alerts, raw-logs)
              ↓
          [Agents - TBD]
          - Triage Agent → Neo4j blast radius
          - Correlation Agent → Weaviate semantic search
          - RCA Agent → DSPy synthesis
          - Postmortem Writer → Kafka (postmortems)
              ↓
          FastAPI → React UI
```

## Next Steps

Agent implementation phase:
- Triage Agent (severity classification + Neo4j traversal)
- Correlation Agent (Weaviate similarity search)
- RCA Agent (DSPy root cause analysis)
- Postmortem Writer Agent (DSPy structured output)
