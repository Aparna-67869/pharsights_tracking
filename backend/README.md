# Pharsights Intel Command Center — Backend

Regulatory intelligence platform for FDA / USPTO / Orange Book monitoring.

## Quickstart (local, zero external services)

```bash
cd backend
pip install -r requirements.txt

# SQLite + local filesystem fallbacks are the defaults, so this just works:
python -m scripts.bootstrap      # create schema + seed reference data
python -m scripts.run_pipeline   # run the full collect -> detect -> analyze pipeline
uvicorn app.main:app --port 8000
```

Open http://localhost:8000/docs for the OpenAPI explorer.

## Architecture

```
app/
  core/         config, logging, security, cache, events, errors
  db/           session, base, models (SQLAlchemy 2.0), repositories
  collectors/   source adapters: FTF, PTE, PDE, Orange Book (+ base HTTP client)
  parsers/      pdf / excel / fixed-width parsers producing normalized records
  etl/          normalization, validation, snapshotting, change detection
  intelligence/ analyzers per module + AI impact engine + priority scoring
  graph/        knowledge graph traversal / 360-degree product view
  search/       unified global search across all entity types
  alerts/       alert engine, dedupe, prioritization, channels
  copilot/      RAG pipeline, retrieval, agent orchestration
  api/          FastAPI routers (REST), GraphQL schema, WebSocket hub
  services/     application services used by both API and DAGs
  workers/      pipeline entrypoints invoked by Airflow
```

See `../docs/` for the full architecture, LLD, ER diagram and runbooks.
