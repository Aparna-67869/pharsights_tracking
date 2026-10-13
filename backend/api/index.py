"""Vercel serverless entrypoint for the FastAPI backend.

Vercel's Python runtime looks for a WSGI/ASGI application named ``app`` in the
entrypoint module. The application itself is unchanged; this module only makes
it importable at the path Vercel expects so the same code runs on Vercel, in
Docker and locally.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Vercel runs this file from ``backend/api/``; the application package lives one
# directory up. Put it on the import path so ``app`` resolves the same way it
# does under uvicorn.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402

__all__ = ["app"]
