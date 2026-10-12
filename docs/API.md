# API Reference

Base URL: `{API_BASE}/api/v1` (`settings.api_prefix`). Interactive docs are
served at `/docs` (Swagger) and `/redoc`. The frontend consumes the same API,
so anything the dashboard shows is reachable programmatically.

## Authentication

Every route except `/health`, `/ready`, and the OpenAPI docs requires a JWT
bearer token.

```bash
TOKEN=$(curl -s -X POST "$API/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username":"analyst@pharma-intel.local","password":"AnalystPass!234"}' \
  | jq -r .access_token)

curl -s "$API/api/v1/dashboard/kpis" -H "Authorization: Bearer $TOKEN"
```

### Roles and scopes

| Role | Scope posture |
| --- | --- |
| `admin` | Everything, including `run:pipeline` and user administration |
| `analyst` | Full read plus pipeline runs |
| `regulatory_affairs` | Read across all modules |
| `ip_counsel` | Read across all modules, patent-centric views |
| `executive` | Read, dashboard-focused |
| `viewer` | Read-only, capped to non-sensitive read scopes |

Scopes are enforced by `require_scope` (`app/api/deps.py`). The frontend
degrades gracefully when a scope is missing — the control is hidden, and the
API returns `403` if it is called anyway.

## Endpoints

### Auth — `/auth`

| Method | Path | Description |
| --- | --- | --- |
| POST | `/auth/token` | Exchange credentials for a JWT |
| GET | `/auth/me` | Current user profile and scopes |

### Executive dashboard — `/dashboard`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/dashboard/kpis` | KPI strip: drugs monitored, patents expiring soon, new FTF/PTE/PDE, Orange Book updates, open alerts, high-risk opportunities |
| GET | `/dashboard/module-summaries` | Per-module KPI summaries |
| GET | `/dashboard/charts/patent-expiry-timeline` | Expiry timeline |
| GET | `/dashboard/charts/sponsor-leaderboard` | Sponsor leaderboard |
| GET | `/dashboard/charts/therapy-areas` | Therapy area analysis |
| GET | `/dashboard/charts/monthly-fda-activity` | Monthly activity across modules |
| GET | `/dashboard/charts/generic-opportunity-heatmap` | Generic opportunity heatmap |
| GET | `/dashboard/charts/patent-family-distribution` | Patent family distribution |
| GET | `/dashboard/charts/all` | Every chart in one payload (single round-trip for the dashboard) |
| GET/POST/DELETE | `/dashboard/views[/{id}]` | Saved views and custom dashboards |

### First-to-file — `/ftf`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/ftf/records` | Paginated Paragraph IV filings (filter by drug, ANDA, applicant, patent, date) |
| GET | `/ftf/records/{id}` | One filing |
| GET | `/ftf/summary` | FTF KPIs |
| GET | `/ftf/analytics/monthly-trend` | Filings per month |
| GET | `/ftf/analytics/therapy-areas` | Filings by therapy area |
| GET | `/ftf/export` | CSV export of the current filter |

### Patent term extension — `/pte`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/pte/applications` | Paginated applications |
| GET | `/pte/certificates` | Paginated granted certificates |
| GET | `/pte/summary` | PTE KPIs |
| GET | `/pte/analytics/monthly-trend` | Applications per month |
| GET | `/pte/analytics/extension-distribution` | Granted extension length distribution |
| GET | `/pte/export/applications`, `/pte/export/certificates` | CSV exports |

### Approved active moiety — `/pde`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/pde/moieties` | Paginated approved active moieties |
| GET | `/pde/summary` | PDE KPIs |
| GET | `/pde/analytics/yearly-trend` | Approvals by year |
| GET | `/pde/analytics/top-sponsors` | Sponsors by approved moieties |
| GET | `/pde/export` | CSV export |

### Orange Book — `/orange-book`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/orange-book/products` | Listed products |
| GET | `/orange-book/patents` | Patent listings |
| GET | `/orange-book/exclusivity` | Exclusivity grants |
| GET | `/orange-book/supplements` | Supplement edition history |
| GET | `/orange-book/supplements/compare` | Diff the two most recent editions |
| GET | `/orange-book/supplement/history` | Edition deltas over time |
| GET | `/orange-book/documents` | Downloadable source artifacts |
| GET | `/orange-book/documents/{id}/download` | Download an archived artifact |
| GET | `/orange-book/summary`, `/orange-book/export/products` | KPIs and CSV export |

### Change history and intelligence — `/api/v1` (intelligence router)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/changes` | Detected change history (filter by module, type, date) |
| GET | `/changes/{id}` | One change |
| GET | `/changes/{id}/versions` | Before/after comparison |
| GET | `/changes/export` | CSV export |
| GET | `/insights` | AI impact analyses with priority |
| GET | `/insights/{id}` | One analysis with its score breakdown |
| GET | `/audit-logs` | Audit trail |

### Alerts — `/alerts`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/alerts` | Alert queue (filter by severity, status) |
| GET | `/alerts/summary` | Counts by priority and status |
| GET | `/alerts/{id}` | One alert |
| GET | `/alerts/{id}/notifications` | Delivery attempts per channel |

### Search and knowledge graph — `/api/v1` (search router)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/search` | Unified search across drugs, patents, NDAs, ANDAs, sponsors, moieties, NCT ids |
| GET | `/drugs/{id}/360` | 360-degree product view |
| GET | `/drugs`, `/patents`, `/sponsors` | Canonical entity lists |
| GET | `/graph/stats` | Knowledge graph statistics |

### Copilot — `/copilot`

| Method | Path | Description |
| --- | --- | --- |
| POST | `/copilot/ask` | Ask a question; returns an answer with citations |
| GET | `/copilot/suggested-questions` | Example questions |
| GET | `/copilot/conversations` | The caller's threads |
| GET | `/copilot/conversations/{id}` | One thread with messages |

### Sources and pipeline — `/sources`, `/pipeline`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/sources` | Monitored source registry with health |
| GET | `/sources/{code}` | One source |
| GET | `/sources/{code}/documents` | Document versions |
| GET | `/sources/{code}/runs` | Collection history |
| GET | `/pipeline/runs`, `/pipeline/runs/{id}` | Pipeline run history |
| POST | `/pipeline/run` | Trigger a sweep (scope `run:pipeline`); runs in the background |

### System

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (checks the database) |
| GET | `/api/v1/meta` | Platform metadata and enabled capabilities |
| WS | `/ws/events` | Live domain events for the dashboard |

## Conventions

- **Pagination** — list endpoints return `Page[T]`: `{ items, total, page, page_size }`.
  `page` starts at 1; `page_size` is capped (commonly 200, 500 for run history).
- **Filtering** — module lists accept `q` (free text), entity filters, and a
  `start` / `end` date range. The same parameters work on the matching
  `/export` endpoint, so "what I see is what I export".
- **Errors** — JSON body `{ "detail": "..." }` with a standard status code.
  `401` missing/expired token, `403` insufficient scope, `404` not found,
  `422` validation error. Internal errors never leak stack traces.
- **Idempotency** — `POST /pipeline/run` is safe to call repeatedly; the
  content-hash guard means an unchanged source is a no-op.

## WebSocket

`/ws/events` streams the domain events published by the pipeline (`pharma.*`
topics such as `pharma.alert.created`, `pharma.ftf.record_added`,
`pharma.pipeline.run`). The frontend subscribes to live-update the dashboard
without polling. Slow consumers are dropped rather than back-pressuring the
pipeline.
