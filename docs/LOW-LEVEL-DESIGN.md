# Low-Level Design

Function-level design of the backend. For the layer view and rationale, see
[`ARCHITECTURE.md`](ARCHITECTURE.md); for the schema, see
[`DATA-MODEL.md`](DATA-MODEL.md).

## Module map

```
app/
├── collectors/     registry, base, http + playwright collectors, change monitor
├── parsers/        source-specific PDF / XLSX / HTML → record dicts
├── etl/            validate, load, record_changes
├── intelligence/   engine (impact), analytics, priority, narrative
├── graph/          builder, resolve (entity resolution)
├── search/         index (RAG corpus), global_search
├── copilot/        agent, embeddings, llm, rag
├── alerts/         engine, channels
├── api/            deps, ws, routers/*
├── services/       pipeline (orchestration)
├── mcp/            MCP server surface
├── db/             models, repositories, session, bootstrap
└── core/           config, security, events, text, errors, logging
```

## Collection

**`app/collectors/registry.py`** — `SourceSpec` is the declarative contract for
a source: `code`, `name`, `module`, `url`, `document_kind`, `cadence`,
`locator`, `direct_url`, `entity_type`. `ALL_SOURCES` and `SOURCES_BY_CODE` are
the registries. `FUTURE_SOURCES` documents not-yet-enabled sources.

**`app/collectors/base.py`**

| Symbol | Responsibility |
| --- | --- |
| `CollectedDocument` | Fetch result: content bytes, filename, content type, publication label, ETag, last-modified |
| `BaseCollector` | Template: resolve → fetch → return `CollectedDocument`. Subclasses implement the transport |
| `ensure_source_definition()` | Idempotently registers the source row on first use |

**`app/collectors/http.py`** — the default transport: conditional headers
(`If-None-Match`, `If-Modified-Since`), retries with backoff, and a
`304 Not Modified` short-circuit. **`app/collectors/storage.py`** persists
artifacts and deduplicates by content hash. **`app/collectors/modules.py`**
maps a module name to its source specs.

## Parsing

One parser module per document shape, each exposing
`parse(content, source) -> list[dict]`. PDFs use pdfplumber/PyMuPDF with Camelot
for ruled tables; spreadsheets use pandas + OpenPyXL; HTML uses BeautifulSoup.
Every parser is pure — it never touches the database — so each is unit-testable
against a stored artifact fixture.

## ETL

**`app/etl/validate.py`** — required-field and format checks per entity type.
Invalid rows are dropped and counted; a row missing a natural key is never
silently loaded.

**`app/etl/load.py`**

| Function | Responsibility |
| --- | --- |
| `load_ftf` | Upsert Paragraph IV filings, linking drug/patent/sponsor |
| `load_pte_applications` | Upsert PTE applications |
| `load_pte_certificates` | Upsert granted certificates |
| `load_active_moieties` | Upsert approved active moieties |
| `load_orange_book_*` | Upsert products, patents, exclusivity, supplement summary |
| `record_changes` | Given a diff result, write `DetectedChange` rows and publish events |

**`app/db/repositories.py`**

| Symbol | Responsibility |
| --- | --- |
| `RecordDelta` | Added / updated / removed sets with field-level diffs |
| `diff_fields` | Compare two record dicts, ignoring volatile columns |
| `sync_versioned_records` | Reconcile parsed records against active rows: insert, update, deactivate |

`sync_versioned_records` is the heart of change detection. For each parsed
record it computes a `content_hash`; a matching hash against the active row is a
no-op, a differing hash is an update (old values captured), a missing source
key is a removal (`is_active = false`).

## Intelligence

**`app/intelligence/engine.py`** — `analyze_pending_changes()` scans
unprocessed, non-baseline changes, computes affected entities, builds the
Insight narrative, stores the score breakdown, and marks the change processed.
Baseline changes are marked processed without an insight.

**`app/intelligence/analytics.py`** — aggregate queries behind every chart
endpoint (expiry timeline, sponsor leaderboard, therapy areas, monthly activity,
opportunity heatmap, family distribution).

**`app/intelligence/priority.py`** — `compute_priority(**signals)` returns a
`PriorityScore` with six weighted `ScoreComponent`s, a clamped total, a band
label, and a serializable breakdown. Pure function; exhaustively unit-tested.

## Graph, search, copilot

| Module | Key entry points |
| --- | --- |
| `graph/builder.py` | Build/refresh nodes and edges for touched entities |
| `graph/resolve.py` | Normalize and resolve drug/sponsor/patent to canonical rows |
| `search/index.py` | Flatten records into `document_chunks` with embeddings |
| `search/global_search.py` | Cross-entity query returning ranked hits |
| `copilot/rag.py` | Retrieve top-k chunks with filters and citations |
| `copilot/agent.py` | Tool-using loop: plan → tools → synthesize + cite |
| `copilot/embeddings.py` | Provider abstraction (Azure OpenAI or local hashing) |

## API and orchestration

**`app/api/deps.py`** — `Principal`, `require_scope(scope)`, session and
principal dependencies.

**`app/api/routers/*.py`** — thin controllers: parse query params, call a
repository or analytics function, return a Pydantic model. No business logic.

**`app/api/ws.py`** — `ConnectionManager` broadcasting domain events; drops
events for slow clients rather than blocking the publisher.

**`app/services/pipeline.py`** — `run_pipeline(modules, source_codes, trigger,
skip_graph, skip_index, skip_alerts)`. Creates a `PipelineRun`, iterates
sources, runs collect → parse → validate → load → change, then
analyze → alert → graph → index, and finalizes the run with counts and duration.
This function is the single implementation used by the CLI, the API, and
Airflow.

## Concurrency and transactions

- One database session per unit of work; the pipeline commits per source so a
  later failure does not roll back earlier successes.
- Change recording and entity-link backfill share a transaction so a record and
  its `DetectedChange` are consistent.
- The API runs reads on pooled connections; the pipeline run triggered via the
  API executes in a background task, never inline.

## Error taxonomy

`app/core/errors.py` defines `PharmaError` and subclasses (`NotFoundError`,
`ValidationError`, `ParserError`, `SourceUnavailableError`, …), each mapped to
an HTTP status by a handler in `app/main.py`. Internal exceptions are logged
with context and returned as an opaque `500` — no stack trace reaches a client.
