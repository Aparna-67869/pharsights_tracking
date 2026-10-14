# Pharma Intelligence Platform

An automated regulatory-intelligence command center for pharmaceutical
exclusivity and patent monitoring. It watches the FDA, USPTO, and Orange Book
sources defined in the SOP, detects what changed between published versions,
scores the impact, and surfaces only actionable intelligence on an executive
dashboard with an AI copilot.

Users never visit FDA or USPTO pages. The platform does that on a schedule and
tells them what matters.

## What it monitors

| Module | Source | Signal |
| --- | --- | --- |
| **FTF** | FDA Paragraph IV Certifications | New / changed / withdrawn first-to-file certifications |
| **PTE** | USPTO Patent Term Extension | New applications and granted certificates |
| **PDE** | FDA Approved Active Moiety (written requests) | Newly approved active moieties |
| **Orange Book** | FDA cumulative supplement + data files | Product, patent, and exclusivity deltas per edition |

Seven live source endpoints are configured in
`backend/app/collectors/registry.py`. ClinicalTrials.gov, PubMed, Espacenet,
WIPO, EMA, and DailyMed are registered as future sources and plug into the same
collector interface.

## How it works

```
Source published
      │
      ▼
Collector fetches the document (ETag / content-hash guarded)
      │
      ▼
Parser extracts normalized records
      │
      ▼
Validator rejects structurally invalid rows
      │
      ▼
Change engine diffs against the active snapshot
      │  added / updated / removed + field-level deltas
      ▼
DetectedChange rows (full audit history, versioned)
      │
      ▼
AI impact engine → Insight (what / why / who / opportunity / risk / action / priority)
      │
      ▼
Priority-scored Alert → dashboard, email, Teams
```

Every step is idempotent. Re-running a collection over an unchanged source is a
no-op, which is what makes the scheduler safe.

## Repository layout

```
.
├── backend/                     FastAPI service, ETL, intelligence, collectors
│   ├── app/
│   │   ├── api/routers/         REST endpoints (ftf, pte, pde, orange_book, …)
│   │   ├── collectors/          Source registry + HTTP/Playwright collectors
│   │   ├── parsers/             PDF / XLSX / HTML → normalized records
│   │   ├── etl/                 Validation, loading, change recording
│   │   ├── intelligence/        Impact engine, analytics, priority scoring
│   │   ├── graph/               Knowledge-graph builder and entity resolution
│   │   ├── search/              Global search + RAG vector index
│   │   ├── copilot/             AI copilot, embeddings, RAG pipeline
│   │   ├── alerts/              Alert engine + delivery channels
│   │   ├── mcp/                 MCP server for external agents
│   │   ├── services/pipeline.py Orchestration of one full sweep
│   │   └── db/                  Models, repositories, session, bootstrap
│   ├── dags/                    Airflow DAGs (daily, monthly, watchdog)
│   ├── scripts/                 bootstrap.py, seed.py, run_pipeline.py
│   └── tests/                   pytest suite
├── frontend/                    Next.js 15 + TypeScript + Tailwind dashboard
│   └── src/
│       ├── app/(dashboard)/     Executive dashboard and module pages
│       ├── components/          Charts, tables, layout, UI primitives
│       ├── hooks/               React Query data hooks
│       └── lib/                 API client, formatting, types
├── deploy/
│   ├── postgres/init/           pgvector + trigram extension bootstrap
│   ├── k8s/                     Kubernetes manifests
│   └── azure/                   Bicep template + deployment script
├── docs/                        Architecture, data model, AI, API, operations
├── docker-compose.yml           Postgres/pgvector + Redis + Kafka + app
└── .github/workflows/           CI (test/build/validate) and CD (Azure)
```

## Quick start

```bash
# Bring up the full stack (Postgres+pgvector, Redis, Kafka, API, frontend)
docker compose up --build

# First run only: create the schema, seed users and reference data
docker compose exec api python -m scripts.bootstrap
docker compose exec api python -m scripts.seed

# Run one collection sweep for a single module
docker compose exec api python -m scripts.run_pipeline --module ftf
```

The API is on `http://localhost:8000` (docs at `/docs`) and the dashboard on
`http://localhost:3000`. Sign in with the seeded administrator
(`admin@pharma-intel.local` / `AdminPass!234`; `scripts.seed` prints every
seeded account and its role). Change these credentials before any real
deployment.

Without Docker, the backend falls back to SQLite and a NumPy vector store, so
`python -m uvicorn app.main:app --reload` works with no external services.

## Running the tests

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest            # 20 tests: change detection, health, priority, API
```

Tests run against a throwaway SQLite file and never touch real data.

## Deployment

| Target | Guide |
| --- | --- |
| Local / single host | `docker-compose.yml` |
| Kubernetes | `deploy/k8s/` |
| Azure Container Apps | `deploy/azure/README.md` |

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system architecture and data flow
- [`docs/LOW-LEVEL-DESIGN.md`](docs/LOW-LEVEL-DESIGN.md) — module and function design
- [`docs/DATA-MODEL.md`](docs/DATA-MODEL.md) — schema and ER diagram
- [`docs/KNOWLEDGE-GRAPH.md`](docs/KNOWLEDGE-GRAPH.md) — entity model and relationships
- [`docs/AI.md`](docs/AI.md) — impact engine, RAG pipeline, copilot
- [`docs/ALERTING.md`](docs/ALERTING.md) — alert engine and prioritization
- [`docs/API.md`](docs/API.md) — REST API reference
- [`docs/UI-UX.md`](docs/UI-UX.md) — dashboard design and UX principles
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — scheduling, monitoring, runbooks
- [`deploy/azure/README.md`](deploy/azure/README.md) — Azure deployment
