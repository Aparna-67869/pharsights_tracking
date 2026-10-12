-- Extensions required by the platform's production database.
-- pgvector backs the mirrored embedding column used for RAG / semantic search.
CREATE EXTENSION IF NOT EXISTS vector;
-- Trigram indexes accelerate fuzzy drug / sponsor name lookups in global search.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
