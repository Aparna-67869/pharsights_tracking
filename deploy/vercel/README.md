# Deploying on Vercel

The platform is a monorepo with two independently deployable halves. Vercel
treats each as **its own project**, and each project's **Root Directory** must
point at the matching subfolder — this is the single most common cause of a
"Deployment failed" on both halves, because a project created at the repo root
finds neither `package.json` (frontend) nor the Python entrypoint (backend).

Create two Vercel projects from the same Git repository.

## 1. Frontend project (Next.js)

- **Root Directory:** `frontend`
- **Framework Preset:** Next.js (auto-detected)
- **Build Command:** `npm run build` (default)
- **Output Directory:** leave default (`.next`)
- **Environment Variables:**
  - `NEXT_PUBLIC_API_BASE_URL` = `https://<your-backend-project>.vercel.app`

  `NEXT_PUBLIC_*` is baked into the client bundle at build time, so set it
  **before** the first build. Changing it later requires a redeploy.

The frontend uses `output: "standalone"` only outside Vercel (for the local
Docker-style server). On Vercel `VERCEL` is set, so it builds normally.

## 2. Backend project (FastAPI on Python Serverless Functions)

- **Root Directory:** `backend`
- **Framework Preset:** Other
- **Functions region:** pick the one nearest your database; it should match the
  frontend region to keep cross-service latency low.
- **Environment Variables:**
  - `ENVIRONMENT` = `production`
  - `JWT_SECRET` = a long random value (`openssl rand -hex 32`)
  - `DATABASE_URL` = a Postgres URL — Vercel functions are stateless, so the
    local SQLite file **cannot** be used (see below)
  - `CORS_ORIGINS` = `["https://<your-frontend-project>.vercel.app"]`
  - Optional, for AI features: `LLM_PROVIDER`, `AZURE_OPENAI_ENDPOINT`,
    `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT`

The entrypoint is `backend/api/index.py`, which exposes the ASGI `app`.
`backend/vercel.json` sets the function memory/time.

### Database

Vercel's filesystem is ephemeral and read-only at runtime, so the bundled
`backend/data/pharma.db` is neither shipped (it is in `.vercelignore`) nor
writable. The backend needs a real Postgres with the `vector` extension
(pgvector). Provision one (Neon, Supabase, RDS, Azure Database for PostgreSQL),
set `DATABASE_URL`, and run migrations once:

```bash
cd backend
DATABASE_URL="postgresql+psycopg://user:pass@host/db" alembic upgrade head
DATABASE_URL="postgresql+psycopg://user:pass@host/db" python -m app.cli seed   # optional
```

### What does not work on serverless

The automatic monitoring scheduler and Airflow DAGs are long-running background
loops. A Vercel function runs only in response to a request, so the in-process
scheduler must be off:

- `SCHEDULER_ENABLED` = `false`

Drive collection from a scheduler that can call an HTTP endpoint instead — Vercel
Cron (a `crons` entry in `backend/vercel.json` hitting a protected route),
Airflow, or any external cron calling `POST /api/v1/pipeline/run`. Also note the
WebSocket live stream needs a stateful host (Container Apps, AKS, Fly, Render);
on Vercel the frontend falls back to polling.

## Quick checklist when a deploy fails

1. **Root Directory** set to `frontend` / `backend` respectively.
2. Frontend: `NEXT_PUBLIC_API_BASE_URL` set before building.
3. Backend: `DATABASE_URL` points at reachable Postgres; `data/` is ignored.
4. Backend: `SCHEDULER_ENABLED=false`.
5. Check the build log — "No `package.json` found" or "entrypoint not found"
   is almost always the Root Directory.
