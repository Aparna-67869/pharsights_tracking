# Operations

How the platform runs itself, how to watch it, and what to do when a source
misbehaves.

## Scheduling

Airflow orchestrates the sweeps in `backend/dags/`. The DAGs are thin: they
invoke the same `run_pipeline` used by the API and the CLI, so there is one
implementation of the work.

| DAG | Cadence | What it does |
| --- | --- | --- |
| `pharma_daily_regulatory_sweep` | Daily, 05:00 UTC | FTF and PDE — the sources that change most often |
| `pharma_monthly_orange_book` | Monthly, 3rd at 04:00 UTC | Orange Book cumulative supplement and data files |
| `pharma_hourly_health_watchdog` | Hourly | Checks source health and raises an alert for any source that is stale or erroring |

Cadence lives on each `SourceDefinition.cadence`; the registry is the source of
truth for what a given sweep should touch.

### Running a sweep manually

```bash
# CLI — one module, or everything
python -m scripts.run_pipeline --module ftf
python -m scripts.run_pipeline

# API — asynchronous, same code path
curl -X POST "$API/api/v1/pipeline/run" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"modules": ["pte"]}'
```

`POST /pipeline/run` returns immediately; poll `GET /pipeline/runs` for the
outcome. The request is audited.

## Observability

| Signal | Where |
| --- | --- |
| Structured JSON logs | stdout, collected by Azure Monitor / Log Analytics |
| Pipeline runs | `GET /api/v1/pipeline/runs` — counts, duration, error per sweep |
| Collection runs | `GET /api/v1/sources/{code}/runs` — per-source fetch history |
| Source health | `GET /api/v1/sources` — `last_checked_at`, `last_success_at`, `last_error` |
| Live events | `WS /ws/events` |
| Alerts | `GET /api/v1/alerts/summary` |
| Audit trail | `GET /api/v1/audit-logs` |

Recommended Azure Monitor alerts:

- API 5xx rate over threshold for 5 minutes.
- Container App replica count at the maximum (capacity pressure).
- Postgres CPU / storage / connection saturation.
- A `CollectionRun` failing for the same source three times in a row.
- No successful `PipelineRun` within the expected window (the watchdog covers
  this in the database; alert on the watchdog's own absence too).

## Health endpoints

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | Process is up (liveness) |
| `GET /ready` | Database reachable and schema present (readiness) |

Container Apps probes point at `/health` for liveness and `/ready` for
readiness, so a replica with a broken database connection is pulled out of
rotation rather than serving errors.

## Runbooks

### A source stopped updating

1. `GET /api/v1/sources/{code}` — read `last_error` and `last_success_at`.
2. `GET /api/v1/sources/{code}/runs` — find the first failing run and its error.
3. Common causes: the landing page changed its markup (the locator strategy
   found no link), the server is rate-limiting, or the artifact moved. Open the
   source URL and compare with the `locator` in
   `app/collectors/registry.py`.
4. Fix the locator or the direct URL, then trigger
   `POST /api/v1/pipeline/run` with `{"source_codes": ["<code>"]}`.

### A parse produced zero records

1. `GET /api/v1/sources/{code}/documents` — the latest document has
   `parse_status = failed` and the artifact is downloadable.
2. Download it via the document download endpoint and inspect the real format.
3. Update the parser in `app/parsers/`, add a fixture to
   `backend/tests/`, redeploy, and re-run the source.

### Alerts are too noisy

Raise `alert_min_priority_to_notify` (default 40). Events below the new
threshold still land in the change history and insights; they just stop
notifying. If only one module is noisy, adjust that module's weights in
`app/intelligence/priority.py`.

### The database needs restoring

1. Restore the Postgres flexible server from the latest backup.
2. Run `python -m scripts.bootstrap` to ensure the schema and any additive
   columns exist.
3. Re-trigger a full sweep. The content-hash guard means unchanged sources are
   no-ops; only genuine gaps are filled. History is never duplicated.

## Capacity and scaling

- The API is stateless; scale replicas horizontally. Session state is in the
  database, not the process.
- The pipeline is CPU-bound on parsing. Run it as a separate Container Apps Job
  or an AKS CronJob so parsing never competes with request serving.
- Vector search scales with the database; move to a dedicated index if
  `document_chunks` grows beyond the working set.

## Security operations

- **Secrets** live in Key Vault, injected via managed identity. No secret is in
  an image or a repository.
- **Rotation** — rotate the Postgres password, JWT signing key, and webhook URLs
  on the standard schedule; the deployment reads them from Key Vault at release.
- **Audit** — every mutating call and every pipeline trigger writes to
  `audit_logs` with actor, action, resource, status, IP, and user agent.
- **Least privilege** — the database user has DML rights on its schema only, no
  DDL; the pipeline identity has Blob read/write on the artifact container only.

## Backup and disaster recovery

| Asset | Strategy | Target |
| --- | --- | --- |
| PostgreSQL | Managed automated backups + geo-redundant storage | RPO 15 min, RTO 1 h |
| Blob artifacts | GRS replication | RPO ~15 min |
| Configuration | Bicep in version control | Redeploy from `main` |
| Secrets | Key Vault soft-delete + purge protection | — |

Because every artifact is stored and every collection run is idempotent, a
restored database plus a re-run reconstructs the platform's state without data
loss beyond the backup window.
