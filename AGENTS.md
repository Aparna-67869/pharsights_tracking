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
cd frontend && NEXT_PUBLIC_API_BASE_URL=https://work-2-<host>/api/v1 \
  npx next start -p 12000
```

Tests: `cd backend && python3 -m pytest -q` (22 pass). Frontend typecheck: `npm run typecheck`.

## Auth / RBAC

- Roles and scopes live in `backend/app/core/security.py`.
- `VIEWER` holds `{"read:data"}` only. Every module endpoint (ftf, pte, pde, orange-book,
  dashboard, changes, alerts, sources, graph, pipeline runs) requires `read:data`.
  The copilot (`/copilot/ask`) requires a higher scope and correctly 403s for viewers.
- Do NOT reintroduce a `read:public` scope — it silently 403s every module page.
- Frontend gates action controls on scopes via `useAuth().hasScope(...)` (see
  `frontend/src/components/layout/sidebar.tsx` and the `Run pipeline now` button in
  `src/app/(dashboard)/sources/page.tsx`, gated on `run:pipeline`).

## Data / pipeline notes

- The live pipeline really fetches FDA/USPTO (e.g. `fda_ftf_ppiv_excel` → ~1,640 FTF rows,
  `fda_ftf_ppiv_pdf`), stores versioned snapshots, diffs them and writes audit rows.
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

- Seeded passwords (development only, see `scripts/seed.py`):
  `admin/admin@pharma-intel.local AdminPass!234`, `analyst@… AnalystPass!234`,
  `ra@… RAPass!234`, `ip@… IPPass!234`, `exec@… ExecPass!234`,
  `viewer@… ViewerPass!234`.
- Self-registration: `POST /auth/register` (frontend "Create an account" on the
  login page). It always grants the least-privilege `viewer` role. Controlled by
  `settings.allow_self_registration` (env `ALLOW_SELF_REGISTRATION`, default true;
  set false in production). Email validation is deliberately pragmatic so the
  internal `@pharma-intel.local` domain (which strict validators reject) works.

## Gotchas

- `backend/app/copilot/agent.py` uses `OrangeBookPatent` — it must stay imported from
  `app.db.models`, or the "generic opportunities" copilot tool throws NameError.
- `backend/app/search/index.py` previously fetched the whole `orange_book_patents` table
  per drug (N+1) and discarded it; it now joins per-drug Orange Book products/patents.
- Ruff: `cd backend && ruff check app tests`. E501 long lines are pre-existing; the
  important classes are F821/F841/F601 (undefined names / dead vars / dup keys).
