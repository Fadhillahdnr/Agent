"""Konfigurasi dari environment (.env). Tidak ada path hardcoded."""
import os
from dataclasses import dataclass
from functools import lru_cache


def _int(name: str, default: int) -> int:
    v = os.environ.get(name, "").strip()
    return int(v) if v else default


def _str(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v.strip() if v is not None and v.strip() != "" else default


@dataclass(frozen=True)
class Settings:
    database_url: str
    project_root: str
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    llm_provider: str
    anthropic_api_key: str
    anthropic_model: str
    openai_base_url: str
    openai_api_key: str
    openai_model: str
    max_file_bytes: int
    scan_interval: int
    git_max_commits: int
    max_tool_iterations: int
    history_turns: int
    rate_limit_member: int
    rate_limit_viewer: int
    session_ttl_hours: int
    admin_username: str
    admin_password: str
    internal_token: str
    telegram_bot_token: str
    telegram_allowed_ids: tuple
    api_url: str
    secure_cookies: bool
    semantic_min_score: float


@lru_cache
def get_settings() -> Settings:
    ids = tuple(
        int(x) for x in _str("TELEGRAM_ALLOWED_IDS").replace(";", ",").split(",") if x.strip().isdigit()
    )
    return Settings(
        database_url=_str("DATABASE_URL", "postgresql://copilot:copilot@db:5432/copilot"),
        project_root=_str("PROJECT_ROOT", "/project"),
        embedding_provider=_str("EMBEDDING_PROVIDER", "fastembed"),
        embedding_model=_str("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
        embedding_dim=_int("EMBEDDING_DIM", 384),
        llm_provider=_str("LLM_PROVIDER", "anthropic"),
        anthropic_api_key=_str("ANTHROPIC_API_KEY"),
        anthropic_model=_str("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        openai_base_url=_str("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_api_key=_str("OPENAI_API_KEY"),
        openai_model=_str("OPENAI_MODEL", "gpt-4o"),
        max_file_bytes=_int("MAX_FILE_BYTES", 1_000_000),
        scan_interval=_int("SCAN_INTERVAL_SECONDS", 60),
        git_max_commits=_int("GIT_MAX_COMMITS", 2000),
        max_tool_iterations=_int("MAX_TOOL_ITERATIONS", 8),
        history_turns=_int("HISTORY_TURNS", 6),
        rate_limit_member=_int("RATE_LIMIT_MEMBER_PER_MIN", 20),
        rate_limit_viewer=_int("RATE_LIMIT_VIEWER_PER_MIN", 8),
        session_ttl_hours=_int("SESSION_TTL_HOURS", 12),
        admin_username=_str("ADMIN_USERNAME", "admin"),
        admin_password=_str("ADMIN_PASSWORD"),
        internal_token=_str("INTERNAL_API_TOKEN"),
        telegram_bot_token=_str("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_ids=ids,
        api_url=_str("API_URL", "http://api:8000"),
        secure_cookies=_str("SECURE_COOKIES", "false").lower() == "true",
        semantic_min_score=float(_str("SEMANTIC_MIN_SCORE", "0.30")),
    )
