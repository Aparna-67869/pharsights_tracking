# AGENTS.md

Repository memory for the Pharma Intelligence Platform (FDA / USPTO regulatory monitoring).

## Layout

- `backend/` — FastAPI app (`app/`), pytest suite (`tests/`), Airflow DAGs (`dags/`), SQLite fallback DB at `backend/data/pharma.db`.
- `frontend/` — Next.js 15 app (App Router, `src/app/(dashboard)/*` pages, `src/components`, `src/lib/api.ts`).

## Local run

```bash
# Backend (port 12001)
cd backend && ENVIRONMENT=development JWT_SECRET=demo-secret-please-replace \
  python3 -m uvicorn app.main:app --host 0.0.0.0 --port 12001

# Frontend (port 12000)
# NEXT_PUBLIC_API_BASE_URL is the API ORIGIN ONLY - the client appends /api/v1 itself
cd frontend && NEXT_PUBLIC_API_BASE_URL=https://work-2-<host> \
  npm run build && npx next start -p 12000
```

Note: `NEXT_PUBLIC_API_BASE_URL` is baked into the client bundle at **build** time,
so it must be set for `npm run build` (not just at `next start`). Setting it to a
value that already ends in `/api/v1` produces doubled paths like
`/api/v1/api/v1/auth/token` and a 404 on login.

Tests: `cd backend && python3 -m pytest -q` (22 pass). Frontend typecheck: `npm run typecheck`.

## Auth / RBAC

- Roles and scopes live in `backend/app/core/security.py`.
- `VIEWER` holds `{"read:data"}` only. Every module endpoint (ftf, pte, pde, orange-book,
  dashboard, changes, alerts, sources, graph, pipeline runs) requires `read:data`.
  The copilot (`/copilot/ask`) requires a higher scope and correctly 403s for viewers.
  The 403 body is `{"code":"forbidden","message":"Insufficient permissions for this
  operation","details":{"required_scope":"use:copilot"}}`. Do NOT loosen this to make
  the 403 disappear — `viewer` has `read:data` only, by design. Instead the UI gates on
  `use:copilot`: the sidebar hides the nav item, the Command Center "Ask the Copilot"
  CTA is disabled, and `/copilot` renders a "Copilot access required" panel. Roles with
  `use:copilot`: admin, analyst, regulatory_affairs, ip_counsel, executive.
- Do NOT reintroduce a `read:public` scope — it silently 403s every module page.
- Frontend gates action controls on scopes via `useAuth().hasScope(...)` (see
  `frontend/src/components/layout/sidebar.tsx` and the `Run pipeline now` button in
  `src/app/(dashboard)/sources/page.tsx`, gated on `run:pipeline`).

## Data / pipeline notes

- The live pipeline really fetches FDA/USPTO, stores versioned snapshots, diffs them
  and writes audit rows.
- FTF **facts come from the official FDA Paragraph IV PDF** (`fda_ftf_ppiv_pdf`,
  `fda.gov/media/166048/download`) — this is `MODULE_SOURCE["ftf"]`, so `/ftf/source`,
  `/sources/ftf/document` and `/comparison/ftf` all resolve to the PDF. The Excel
  companion (`fda_ftf_ppiv_excel`) is still collected and versioned for cross-validation
  but is intentionally **not** in the pipeline `LOADERS`; loading both would store every
  filing twice under different `source_code`s. Both parse to the same 1,647 rows / keys.
  `scripts/reingest_ftf.py` re-syncs the PDF facts and purges stale Excel-sourced rows.
- FTF records are drugs + RLD/NDA + dates from the **FDA published Paragraph IV list**.
  That source has no public ANDA applicant / patent number, so those remain `None` —
  this is faithful to the source, not a parse bug.
- FTF list API intentionally omits `applicant`/`patent_number`/`status` from
  `FtfRecordOut` (unpopulated from this source); the UI table matches the source columns.
- No LLM keys configured → copilot runs in deterministic offline mode (disclosed in the UI).

## SOP conformance (source of truth: the SOP PDF at repo root)

The SOP mandates that each module mirrors what the analyst sees on the source page:

- **FTF** — open the "Paragraph IV Certifications List" PDF; its drugs are listed
  **alphabetically**, and the publication date is printed at the top. So
  `GET /ftf/records` defaults to `sort=drug` (A–Z by `lower(drug_name)`), and
  `GET /ftf/source` returns the parsed `publication_date` / `publication_label`
  (e.g. "September 28, 2026") for the header banner. `sort=submitted` opts into
  newest-first. The CSV export follows the same A–Z order.
- **PTE** — monitor both lists daily (applications filed in the last 5 years, and
  issued certificates).
- **PDE** — the "Approved Active Moiety" Excel, latest update date in brackets.
- **Orange Book** — the Current Cumulative Supplement PDF, published monthly
  (typically the second week); supplement number + month/year at the top.

## Authentication

- **Single-account deployment (default).** The platform holds exactly one
  account, `ALLOWED_LOGIN_EMAIL` (default `pharsightspatent@gmail.com`). It is
  the only address that may sign in (`RESTRICT_LOGIN=true`), the only address
  that may be created, and it cannot be disabled
  (`BLOCK_ADDITIONAL_ACCOUNTS=true`). Any other email is refused with 401;
  register returns 403. Non-authorized attempts are audited as `login_blocked`.
  Set `RESTRICT_LOGIN=false` / `BLOCK_ADDITIONAL_ACCOUNTS=false` to restore the
  normal multi-role accounts.
- **The account is created on the sign-in page.** `POST /auth/register` is
  public (no `Authorization`) *only* in single-account mode, and accepts only
  `ALLOWED_LOGIN_EMAIL`; the created account is a full `admin`. A duplicate is
  409, so the page can never silently overwrite or duplicate the account. With
  the single-account mode off, register reverts to the admin-only flow and
  grants least-privilege `viewer`.
- `GET /auth/config` is public and returns
  `{single_account, allowed_login_email}` so the sign-in page can pre-fill the
  create form before anyone is authenticated.
- `scripts/seed.py` no longer plants a default-password account; set
  `SEED_ADMIN_PASSWORD` if you want bootstrap to create it up front. Reconcile an
  existing database with `python -m scripts.lockdown_accounts` (keeps the
  authorized account, reassigns saved views/subscriptions/conversations, deletes
  the rest, and never creates an account).
- Email validation is deliberately pragmatic so the internal
  `@pharma-intel.local` domain (which strict validators reject) works.
- Password rotation: `POST /auth/password` (`api.changePassword`), surfaced on
  the `/account` page.

## Enterprise shell & design system

- One shell (`components/layout/app-shell.tsx`) wraps every dashboard route:
  a Bloomberg-style top bar with global search, a collapsible grouped left nav
  (`nav-config.ts`), the bottom live activity bar, and the Copilot drawer. Pages
  render only their own body.
- The bottom bar is `components/layout/activity-bar.tsx`, fed by
  `GET /api/v1/activity/today`. It replaced the old `ticker-strip.tsx`, which was
  dead code (never imported, so no bottom bar rendered). Do not reintroduce a
  static ticker of corpus totals — the activity bar reports what the platform
  actually *did* today (sweeps, changes, insights, alerts), which is the point.
- `globals.css` owns the design tokens. Three themes cycle dark → light →
  high-contrast via `theme-provider.tsx` (localStorage key `pharma.theme`).
  Premium primitive classes there: `panel`, `glass`, `ticker`, `live-dot`,
  `data-table`, `scrollbar-thin`. Prefer these over one-off utility soup.
- `components/ui/card.tsx` now renders the `panel` surface so older module pages
  inherit the redesign without edits. `components/common/panel.tsx` is the
  richer variant (icon, tone, actions) used by the newer pages.
- KPI wall uses `components/common/kpi-card.tsx` (label, value, hint, icon,
  tone, trend, series, updatedAt, onClick). `onClick` should navigate to the
  drill-down route, not be a no-op.

## Operations API (added with the enterprise redesign)

- `GET /api/v1/audit` — read the immutable `audit_logs` trail. Ordering and the
  `created_at` output field both derive from the model's `occurred_at`; there is
  no `created_at` column.
- `GET /api/v1/activity/today` — real counts of what ran today (pipeline runs,
  detected changes split material vs baseline, insights, alerts) plus the newest
  events. Powers the bottom activity bar. All figures are queried from the live
  tables; never synthesise them.
- `GET /api/v1/sources/{module}/document/content` — the current source workbook
  parsed into a header + rows for inline viewing (xlsx/xls/csv/txt). PDFs and
  zips return `supported: false` so the UI opens the raw file rather than faking
  a table. Backed by `document_actions.document_rows`.
- `GET /api/v1/opportunities` — scored near-term generic-entry watchlist
  (`{total, by_band, top, sponsor_leaderboard}`).
- `GET/POST/DELETE /api/v1/subscriptions` — per-user alert subscriptions. Delivery
  targets are addressed to the authenticated identity (email + Teams), so users
  configure nothing beyond which modules/priority they care about.
- Alert fan-out: `app/alerts/engine.py` calls
  `alert_dispatcher.dispatch_to_subscribers` after creating each alert. Keep that
  call inside its try/except — subscriber delivery must never break the pipeline.
- `alert_summary()` must return `open`, `critical`, `high`, `medium`, `low`,
  `by_module` **and** `total` — the Alerts KPI cards and the sidebar badge read
  those keys directly. Returning only `open_total`/`by_priority` (the old shape)
  silently left every KPI and the badge at zero. `open_total`/`by_priority` are
  retained for older callers.
- `DetectedChange` uses `document_id` (not `source_document_id`);
  `PipelineRun` uses `trigger` (not `kind`). `PipelineRun` has `alerts_created`.

## Account surface (real data, correct paths)

- The `/account` page (`app/(dashboard)/account/page.tsx`) holds the signed-in
  identity and self-service password rotation. There is no Administration page.
- Correct endpoint paths — do NOT use `/users` or `/notifications/channels` (both
  404): delivery channel config is `/delivery-channels` (`api.deliveryChannels()`).
- There is no account-delete endpoint. The single account cannot be deactivated
  (`BLOCK_ADDITIONAL_ACCOUNTS=true` refuses it). Do not add a destructive delete
  route.
- The alert "Notification channels" panel on `/alerts` reads
  `deliveryChannels()` — it shows which channels are actually configured, not a
  hardcoded list of four.

## Gotchas

- `backend/app/copilot/agent.py` uses `OrangeBookPatent` — it must stay imported from
  `app.db.models`, or the "generic opportunities" copilot tool throws NameError.
- `backend/app/search/index.py` previously fetched the whole `orange_book_patents` table
  per drug (N+1) and discarded it; it now joins per-drug Orange Book products/patents.
- Ruff: `cd backend && ruff check app tests`. E501 long lines are pre-existing; the
  important classes are F821/F841/F601 (undefined names / dead vars / dup keys).

## SQLite concurrency (dev backend)

- SQLite allows one writer. The engine sets `PRAGMA busy_timeout=30000`, `WAL`,
  `foreign_keys=ON`, `synchronous=NORMAL` on every connect.
- `pipeline.run_pipeline` commits between phases and between sources, so the
  write lock is only held for short per-source loads, never for the whole run.
- Do NOT add a global `BEGIN IMMEDIATE` (via `isolation_level=None` + a `begin`
  event). It makes reads take the write lock, deadlocking reflection
  (`reconcile_schema`) and long tests. The correct fix for the "can't upgrade a
  read snapshot to a write" error is to keep telemetry writes (`audit` rows,
  `last_login_at`) off the request session, on a retrying session.
- `db.session.resilient_write(op)` runs `op` in a fresh session and retries lock
  errors. Use it for best-effort writes that must not fail the request. Never
  call it from inside a transaction that already holds the write lock (SQLite
  cannot have two writers) — interior writes must share the caller's session.
- The dev SQLite pool is sized `db_pool_size`+`db_max_overflow` (30), because a
  request may briefly hold two sessions (request + telemetry write).
- Route order: a literal route (`/changes/export`) MUST be declared before a
  same-prefix dynamic route (`/changes/{change_id}`), or the dynamic one
  swallows it. See `intelligence.py`; guarded by a smoke test.

## Data integrity: real data only (hard rule)

- Every field shown must come from a real source document (FDA FTF PDF/Excel,
  USPTO PTE, FDA PDE, Orange Book). No mock/fabricated/guessed values.
- A field that a source does not carry MUST stay NULL. Do NOT infer it from
  another field. `graph/resolve.infer_therapy_area` was the violation — it
  guessed therapy areas from drug-name suffixes (`nib`/`mab` -> Oncology) and
  mislabeled drugs; it now returns `None` and the 952 polluted rows were purged.
  FDA sources have no therapy-area column, so `drugs.therapy_area` is NULL and
  therapy-area charts are legitimately empty.
- `patent_family_distribution` attributes listed patents to the Orange Book
  product's applicant (the only real owner signal in the source), not to a
  patent assignee the source lacks.
- When adding a derived chart/metric, confirm each value traces to a source
  column. If it cannot, drop the chart rather than invent the dimension.
- To re-verify FTF fidelity: parse the live PDF (`parsers.ftf.parse_ftf_pdf`)
  and compare against `ftf_records`; counts and drug|NDA keys must match.

## Row counts and source order

- Natural keys must be unique per real source row. Two rows were silently
  dropped by over-narrow keys and the fix is the contract:
  - PDE key is `moiety|sponsor|issue_date` (a moiety recurs for one sponsor on
    different dates, e.g. Divalproex/Abbott 2002 and 2006).
  - PTE application key includes the filing date, so the same application
    number listed twice stays two rows.
- `SourceDocument.record_count` is what the module serves (distinct persisted
  keys, `RecordDelta.stored`), NOT the raw parsed row count. A source row can be
  rejected by validation or collapse as an exact duplicate; `source_record_count`
  holds the raw count so the provenance bar can show `N (of M source rows)`.
- `source_ordinal` preserves the workbook/list order. Routers default to
  `order_by(source_ordinal, <date>)` so the table matches the source file; the
  ordinal is provenance, not a fact, and is never rendered as one.
- Excel float artifacts (`8088378.0`) are stripped via
  `core.text.canonical_identifier`; genuinely punctuated ids (`7.420.051`,
  `RE27757`) pass through untouched.

## PTE source publication date and download link

- The USPTO page states the file's coverage in the anchor text next to the
  download link, verbatim: *"PTE applications during last five years (updated
  through September 8, 2026)"*. `uspto_pte_applications` scrapes that with
  `publication_date_pattern = r"updated through\s+(...)"`, so
  `publication_label="September 8, 2026"` is USPTO's own date, not a guess.
- The publication date is deliberately distinct from `fetched_at` (when the
  platform downloaded the file) and `last_processed_at` (last pipeline touch);
  all three are real and independently sourced.
- Direct file: `https://www.uspto.gov/sites/default/files/documents/pte_past5years.xlsx`
  (`locator.strategy = href_contains "pte_past5years"`).

## Automatic monitoring (scheduler)

- `services/scheduler.py` runs the real `run_pipeline` on a cadence in a daemon
  thread so the platform monitors with no user action; status is exposed at
  `GET /pipeline/scheduler` and shown on the Sources page. Local/dev equivalent
  of the Airflow DAGs; disable with `SCHEDULER_ENABLED=false`. A file lock
  serialises it against the API-triggered run path.
- Alert email uses `email_service.deliver`, which picks implicit TLS (465) vs
  STARTTLS (587) by port so any relay works. `serve.sh` passes `SMTP_*`,
  `ALERT_EMAIL_RECIPIENTS`, `ALLOWED_LOGIN_EMAIL`, `BLOCK_ADDITIONAL_ACCOUNTS`,
  `TEAMS_WEBHOOK_URL`, `SLACK_WEBHOOK_URL` and `SCHEDULER_INTERVAL_MINUTES`
  through from the environment.
- After each sweep the pipeline emails a **change digest** (`email_service.
  send_change_digest`, called from `services/pipeline.py`) to
  `ALERT_EMAIL_RECIPIENTS` (default `pharsightspatent@gmail.com`). It lists every
  non-baseline detected change with its field-level diff — not just the alerts
  above `ALERT_MIN_PRIORITY_TO_NOTIFY` — so the mailbox is a complete record.
  Delivery needs `SMTP_HOST` (+ `SMTP_USERNAME`/`SMTP_PASSWORD`); for Gmail use
  `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=465`, `SMTP_USE_TLS=false` and an app
  password as `SMTP_PASSWORD`. Without SMTP the digest is recorded `skipped` and
  the sweep still completes.

## Vercel deployment

- The monorepo deploys as **two Vercel projects** from the same repo, each with
  **Root Directory** set: `frontend` and `backend`. A project created at the
  repo root fails on both — no `package.json` for the frontend, no entrypoint
  for the backend. This is the usual cause of "Deployment failed" on both.
- Backend entrypoint is `backend/api/index.py` (exposes ASGI `app`); it puts
  `backend/` on `sys.path` so `from app.main import app` resolves. `backend/
  vercel.json` sets function memory/timeout.
- `backend/.vercelignore` excludes `data/` — the local SQLite DB is ~560 MB and
  would break the upload. Vercel's FS is read-only, so the backend needs a real
  Postgres (`psycopg[binary]` is in requirements for `postgresql+psycopg://`).
- Frontend `next.config.js` sets `output: "standalone"` **only** when `VERCEL`
  is unset, so the local/Docker supervisor still works while Vercel builds
  normally. Set `NEXT_PUBLIC_API_BASE_URL` before the first build (it is baked
  in).
- Serverless caveats: `SCHEDULER_ENABLED=false` (long-running loop), no
  WebSockets (live stream falls back to polling), pgvector optional. Full guide:
  `deploy/vercel/README.md`.

## Frontend static serving (standalone)

- `scripts/serve.sh` must `rm -rf` the standalone `.next/static` and `public`
  before copying, otherwise a rebuild leaves stale chunks and the server keeps
  serving the old bundle (its manifest points at new hashes, so pages 404 their
  chunks).

## Orange Book data-file fidelity and run serialisation

- **Natural keys must include every field that distinguishes a published row.**
  The Orange Book data files list one row per (application, product, patent,
  use code) and per (application, product, exclusivity code, date). Omitting
  `patent_use_code` from `patent_source_key` collapsed 22,438 published patent
  rows to 17,748 on load; omitting `exclusivity_date` did the same for
  exclusivity. Both now include the extra field (`app/parsers/orange_book.py`).
  When a key looks correct but a load stores fewer rows than the parser
  produced, the difference is a key collision - investigate, don't assume dedup.
- **`sync_versioned_records` logs "duplicate natural key" at WARNING** for every
  collapse. That warning count is the signal that a key is losing real rows.
- **Only one pipeline may run at a time.** `run_pipeline` holds
  `app.services.pipeline._pipeline_lock` for its whole duration; the scheduler,
  the API trigger and the CLI all share it. Without it a scheduled sweep and a
  manual `/pipeline/run` overlap, which on SQLite raises `database is locked`
  and leaves a run stuck in `running`. The API probes `pipeline_is_running()`
  first and returns 409; the scheduler treats `ConflictError` as a skipped tick.
- **`scripts/rebaseline_orange_book.py`** purges non-baseline OB change artifacts
  and reloads the datasets from the archived document. FK delete order is
  `notification_logs` -> `alerts` -> `insights` -> `detected_changes`; all
  `IN (...)` deletes are chunked (SQLite bound-parameter limit).

