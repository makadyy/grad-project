-- schema.sql  (A4)  pgvector store for the RAG knowledge base.
-- nomic-embed-text returns 768-dim vectors; change the number here AND EMB_DIM in rag.py together.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id   TEXT PRIMARY KEY,          -- e.g. emp:E1004, proj:P03, sys:sys-erp
    kind       TEXT NOT NULL,             -- employee | department | project | system | customer | vendor | company
    text       TEXT NOT NULL,             -- the fact sentence(s) the LLM will see
    meta       JSONB NOT NULL DEFAULT '{}',
    embedding  vector(768) NOT NULL,
    world_sha  TEXT NOT NULL              -- company content_sha256 this row was built from
);

-- cosine distance index (operator <=>)
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx
    ON kb_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS kb_chunks_kind_idx ON kb_chunks (kind);
