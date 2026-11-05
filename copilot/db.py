"""Koneksi Postgres (pgvector) dan skema."""
import logging
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

log = logging.getLogger(__name__)
_pool = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=True
        )
    return _pool


def reset_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
    _pool = None


@contextmanager
def conn():
    with pool().connection() as c:
        yield c


def vec_literal(v) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in v) + "]"


def schema_sql(dim: int) -> str:
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS repos (
  name TEXT PRIMARY KEY, root_rel TEXT NOT NULL, has_git BOOLEAN NOT NULL DEFAULT FALSE,
  default_branch TEXT, last_indexed TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS files (
  id BIGSERIAL PRIMARY KEY, repo TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
  sha256 TEXT NOT NULL, size BIGINT NOT NULL, mtime_ns BIGINT NOT NULL,
  lang TEXT, kind TEXT NOT NULL, n_lines INT NOT NULL, indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS files_repo ON files(repo);
CREATE TABLE IF NOT EXISTS chunks (
  id BIGSERIAL PRIMARY KEY, file_id BIGINT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  repo TEXT NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL,
  start_line INT NOT NULL, end_line INT NOT NULL, symbol TEXT, text TEXT NOT NULL,
  tsv tsvector NOT NULL, embedding vector({dim}) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin(tsv);
CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file_id);
CREATE INDEX IF NOT EXISTS chunks_emb ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS git_commits (
  repo TEXT NOT NULL, hash TEXT NOT NULL, author TEXT, committed_at TIMESTAMPTZ,
  subject TEXT, body TEXT, files TEXT[] NOT NULL DEFAULT '{{}}', PRIMARY KEY (repo, hash)
);
CREATE INDEX IF NOT EXISTS commits_date ON git_commits(committed_at DESC);
CREATE TABLE IF NOT EXISTS git_branches (
  repo TEXT NOT NULL, name TEXT NOT NULL, head TEXT, base TEXT, ahead INT NOT NULL DEFAULT 0,
  last_commit_at TIMESTAMPTZ, last_subject TEXT, PRIMARY KEY (repo, name)
);
CREATE TABLE IF NOT EXISTS tasks (
  id BIGSERIAL PRIMARY KEY, repo TEXT NOT NULL, source TEXT NOT NULL, key TEXT NOT NULL,
  title TEXT NOT NULL, path TEXT, line INT, present BOOLEAN NOT NULL DEFAULT TRUE,
  checked BOOLEAN, first_seen TIMESTAMPTZ NOT NULL DEFAULT now(), last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_by TEXT, UNIQUE (repo, source, path, key)
);
CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, pw_hash TEXT,
  role TEXT NOT NULL DEFAULT 'member', telegram_id BIGINT UNIQUE, skill_pref TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  channel TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, skill TEXT,
  meta JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_user ON messages(user_id, id DESC);
CREATE TABLE IF NOT EXISTS audit_log (
  id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now(), user_id BIGINT, username TEXT,
  channel TEXT, event TEXT NOT NULL, question TEXT, skill TEXT, files_accessed TEXT[] NOT NULL DEFAULT '{{}}',
  ok BOOLEAN NOT NULL DEFAULT TRUE, detail TEXT
);
CREATE TABLE IF NOT EXISTS index_state (key TEXT PRIMARY KEY, value JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
"""


def init_schema() -> None:
    dim = get_settings().embedding_dim
    with conn() as c:
        c.execute("SELECT pg_advisory_lock(727001)")
        try:
            c.execute(schema_sql(dim))
            c.commit()
        finally:
            c.execute("SELECT pg_advisory_unlock(727001)")
            c.commit()


def set_state(key: str, value: dict) -> None:
    from psycopg.types.json import Jsonb

    with conn() as c:
        c.execute(
            "INSERT INTO index_state(key,value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()",
            (key, Jsonb(value)),
        )


def get_state(key: str):
    with conn() as c:
        r = c.execute("SELECT value, updated_at FROM index_state WHERE key=%s", (key,)).fetchone()
    return r
