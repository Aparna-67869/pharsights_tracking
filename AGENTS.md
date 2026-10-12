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

## Gotchas

- `backend/app/copilot/agent.py` uses `OrangeBookPatent` — it must stay imported from
  `app.db.models`, or the "generic opportunities" copilot tool throws NameError.
- `backend/app/search/index.py` previously fetched the whole `orange_book_patents` table
  per drug (N+1) and discarded it; it now joins per-drug Orange Book products/patents.
- Ruff: `cd backend && ruff check app tests`. E501 long lines are pre-existing; the
  important classes are F821/F841/F601 (undefined names / dead vars / dup keys).
