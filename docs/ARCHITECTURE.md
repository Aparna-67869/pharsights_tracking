# Architecture

## Design principles

1. **The source is the truth; the database is a cache of it.** Every collected
   document is stored byte-for-byte as an artifact, so any record can be traced
   back to the exact file and edition it came from.
2. **Idempotent and replayable.** Collections are guarded by content hash and
   ETag. Re-running a sweep over unchanged sources writes nothing. A failed run
   can be retried without duplicating history.
3. **Append-only history.** Records are never hard-deleted. A row that leaves the
   source is flagged `is_active = false`; the change event records what vanished.
4. **Alert only on meaning.** A baseline (first-ever) snapshot produces no
   alerts. Trivial deltas are filtered by the priority gate before a human sees
   them.
5. **Degrade gracefully.** Postgres + pgvector in production; SQLite + NumPy
   locally. Missing Redis, Kafka, or an LLM key narrows features rather than
   crashing the platform.

## Layer view

```
                    External sources
   ┌──────────┬──────────┬──────────────┬─────────────┐
   │   FDA    │  USPTO   │ Orange Book  │ Future (CT, │
   │ FTF, PDE │   PTE    │  editions    │ PubMed, EU) │
   └────┬─────┴────┬─────┴──────┬───────┴──────┬──────┘
        │          │            │              │
        ▼          ▼            ▼              ▼
   ┌───────────────────────────────────────────────────┐
   │ Collection layer   app/collectors, app/parsers     │
   │ HTTP + Playwright, PDF/Excel/HTML parsing,        │
   │ artifact store, content-hash + ETag guards         │
   └───────────────────────┬───────────────────────────┘
                           ▼
   ┌───────────────────────────────────────────────────┐
   │ ETL layer          app/etl                        │
   │ validate → load → versioned diff → DetectedChange  │
   └───────────────────────┬───────────────────────────┘
                           ▼
   ┌───────────────────────────────────────────────────┐
   │ Event layer        app/core/events.py              │
   │ Domain bus (in-process); Kafka / Service Bus in prod│
   └───────────────────────┬───────────────────────────┘
                           ▼
   ┌───────────────────────────────────────────────────┐
   │ Intelligence       app/intelligence               │
   │ Impact engine, analytics, priority scoring         │
   └───────────────────────┬───────────────────────────┘
                           ▼
   ┌───────────────────────────────────────────────────┐
   │ Knowledge graph    app/graph                      │
   │ Drug · Patent · NDA · ANDA · Sponsor · Moiety      │
   └───────────────────────┬───────────────────────────┘
                           ▼
   ┌───────────────────────────────────────────────────┐
   │ Persistence        app/db                         │
   │ PostgreSQL + pgvector + Redis (SQLite fallback)    │
   └───────────────────────┬───────────────────────────┘
                           ▼
   ┌───────────────────────────────────────────────────┐
   │ API + AI           app/api, app/copilot, app/mcp  │
   │ FastAPI, WebSockets, GraphQL, MCP, RAG copilot     │
   └───────────────────────┬───────────────────────────┘
                           ▼
   ┌───────────────────────────────────────────────────┐
   │ Dashboard          frontend (Next.js 15)           │
   └───────────────────────────────────────────────────┘
```

## Runtime topology

| Concern | Local (`docker-compose`) | Production (Azure) |
| --- | --- | --- |
| API | uvicorn container | Azure Container Apps (3–12 replicas) |
| Frontend | Next.js container | Azure Container Apps (2–8 replicas) |
| Database | Postgres 16 + pgvector | Azure PostgreSQL Flexible Server, zone-redundant |
| Cache | Redis 7 | Azure Cache for Redis (Premium, TLS) |
| Events | Kafka (single broker) | Azure Service Bus topics |
| Artifacts | Local filesystem volume | Azure Blob Storage (identity-auth) |
| Scheduler | Airflow (or manual) | Airflow on AKS / Container Apps Jobs |
| Secrets | `.env` | Azure Key Vault via managed identity |
| Observability | Structured JSON logs | App Insights + Log Analytics |

## Control flow of one sweep

`app/services/pipeline.py` orchestrates a run. For each enabled source of a
module:

1. **Resolve** the current document URL from the landing page (`locator`
   strategy in the source spec), falling back to the last known direct URL.
2. **Fetch** with conditional headers. If the content hash matches the current
   document, stop — nothing to do.
3. **Persist** the artifact and a new `SourceDocument` version, flipping
   `is_current` on the previous version.
4. **Parse** into normalized records (`app/parsers`).
5. **Validate** and drop invalid rows (`app/etl/validate.py`).
6. **Reconcile** against active rows: compute added / updated / removed with
   field-level diffs (`app/db/repositories.py`).
7. **Record** one `DetectedChange` per delta entry, publishing a domain event.
8. After all sources: **analyze** unprocessed changes into `Insight` rows,
   **score** priorities, **create alerts** past the threshold, **notify** on the
   configured channels, and **index** updated entities into the search/RAG store.
9. **Build** the knowledge graph incrementally for touched entities.

The `CollectionRun` and `PipelineRun` rows capture counts, durations, and errors
for every step, which is what the Sources and operations views render.

## Key design decisions

**Why versioned fact rows instead of a staging diff?** Each fact table carries
`source_key`, `content_hash`, `first_seen_at`, `last_seen_at`, and `is_active`.
Diffing is a single indexed lookup per natural key, and history is preserved
without a separate shadow table. The alternative — truncate-and-reload — loses
the audit trail the SOP requires.

**Why record changes separately from the fact rows?** `DetectedChange` is the
event log. It survives even when the underlying fact row is later removed, and
it is the join point between "the data changed" and "here is why it matters"
(`Insight`) and "here is what we told the user" (`Alert`).

**Why an in-process event bus with a Kafka adapter?** Local development should
not require a broker. The bus interface (`app/core/events.py`) is the same in
both cases; production swaps the transport, not the call sites.

**Why pgvector with a JSON mirror?** `document_chunks.embedding` is stored both
as a pgvector column (for SQL `<=>` ordering) and as JSON (so the SQLite/Numpy
fallback works from the same rows). One write path, two read paths.

## Failure and recovery

- **Source unreachable** → the `CollectionRun` is marked failed, the source
  registry records `last_error`, and the watchdog DAG raises a stale-source
  alert. One bad source never aborts the others.
- **Parse failure** → the document is stored with `parse_status = failed`; the
  artifact remains downloadable for manual triage.
- **LLM unavailable** → insight generation falls back to the deterministic
  narrative path; alerts are still produced from the priority score.
- **Vector store unavailable** → search falls back to keyword full-text.
- **Database restored from backup** → replay any `CollectionRun` by re-running
  the pipeline for that source; hashes prevent duplicate records.
