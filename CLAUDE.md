# Global Development Workflow

## Core rule
Never write or modify code directly. Always route through the agent pipeline.
Never skip any pipeline step regardless of task size. When in doubt, run the step.

## Session start
Read `.claude/memory.md` before anything else. Use it to resume without re-explanation.

## Session end
When user says done/wrapping up/stopping:
1. Delegate to `memory-updater`
2. Delegate to `git-agent` to commit and draft PR

## Pipeline (strict order)

1. **git-agent** — suggest branch name, wait for confirmation, checkout
2. **planner** — produce execution plan, no code
3. **code-reviewer** — review plan. Loop back to planner if NEEDS REVISION
4. **dependency-reviewer** — only if plan touches requirements.txt / pyproject.toml / package.json
   - Must audit the FULL installed dependency tree for conflicts, not just the new addition
   - Must run `pip check` to surface hidden conflicts between existing packages
   - Must verify any script in `data/` or `scripts/` can be invoked with `PYTHONPATH=. python <script>` without import errors
   ⚠️ PAUSE: show the final approved plan to the user and wait for explicit approval ("looks good", "proceed", "yes") before continuing. Do not auto-advance to the implementer.
5. **implementer** — execute approved plan only
6. **env-checker** — run after every implementation, no exceptions
7. **test-writer** — write and run tests
8. **security-auditor** — BLOCK restarts from step 2
9. **code-reviewer** — review diff. NEEDS REVISION reruns steps 6–9
   - If docker-compose.yml changed: explicitly verify no `env_file` passes project-level env vars to services that use strict config validation (e.g. Neo4j, Kafka). Verify all added services start and pass their healthcheck.
10. **runtime-checker** — MANDATORY, no exceptions
   - Boot the relevant stack subset (`docker compose up -d` if infra changed)
   - Exercise the changed code path with a real invocation (curl, python script, etc.)
   - Verify: no import errors, no runtime crashes, no integration failures
   - If anything fails: loop back to implementer (step 5), fix root cause, rerun steps 6–10
   - BLOCKS doc-writer — do not proceed if runtime-checker fails
11. **doc-writer** — docstrings, README, comments
12. **git-agent** — commit message (confirm before committing) + PR description

## On-demand agents
- `debugger` — before any bug fix; restart pipeline after root cause found
- `ml-reviewer` — any DSPy / Weaviate / embedding / agent logic change; insert between steps 3–5
- `schema-reviewer` — any DB / Kafka / Pydantic / API contract change; insert between steps 3–5
- `performance-reviewer` — hot paths, async, vector search; insert between steps 3–5

## Override
If user explicitly says to skip a step, comply. Otherwise never skip.

## Current Project: Incident Postmortem Autopilot

### Overview
Event-driven multi-agent system that autonomously generates incident postmortems.
Kafka alert fires → agents triage → Neo4j blast radius traversal → Weaviate
incident correlation → DSPy postmortem generation → FastAPI output.

### Stack
Kafka, PyFlink, Weaviate, Neo4j, DSPy, FastAPI, React (AI-generated UI)

### Agent Pattern
Event-driven reactive (stateless, Kafka-triggered) — NOT planner-executor:
1. Triage Agent — severity classification + Neo4j blast radius
2. Correlation Agent — Weaviate semantic search over past incidents
3. RCA Agent — DSPy Module synthesizing logs + graph + history
4. Postmortem Writer — DSPy typed output → Kafka `postmortems` topic

### Kafka Topics
raw-logs | alerts | postmortems

### Weaviate Collection
PastIncident: { title, root_cause, fix, service, embedding }

### Neo4j Schema
Nodes: Service | Relationships: DEPENDS_ON, CALLS

### Project Structure
agents/ | infra/ | api/ | simulator/ | data/ | docker-compose.yml