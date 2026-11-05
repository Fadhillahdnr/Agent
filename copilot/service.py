"""Alur satu pertanyaan, dipakai bersama oleh web chat dan Telegram."""
import logging

from psycopg.types.json import Jsonb

from . import audit
from .agent import run_agent
from .auth import chat_limit_for, chat_limiter
from .config import get_settings
from .db import conn
from .secrets import redact

log = logging.getLogger(__name__)


class RateLimited(Exception):
    pass


def history(user_id: int, limit: int) -> list:
    with conn() as c:
        rows = c.execute("SELECT role, content FROM messages WHERE user_id=%s ORDER BY id DESC LIMIT %s", (user_id, limit * 2)).fetchall()
    return list(reversed(rows))


def ask(user: dict, question: str, channel: str, skill: "str | None" = None, provider=None) -> dict:
    question = question.strip()[:4000]
    if not chat_limiter.allow(user["id"], chat_limit_for(user["role"])):
        audit.record("rate_limited", user, channel, question, ok=False)
        raise RateLimited()
    hist = history(user["id"], get_settings().history_turns)
    try:
        res = run_agent(question, user["role"], skill or user.get("skill_pref") or None, hist, provider=provider)
    except Exception as e:
        log.exception("agent gagal")
        audit.record("ask", user, channel, question, ok=False, detail=type(e).__name__)
        raise
    with conn() as c:
        c.execute("INSERT INTO messages(user_id,channel,role,content,skill) VALUES (%s,%s,'user',%s,%s)",
                  (user["id"], channel, redact(question), res["skill"]))
        c.execute("INSERT INTO messages(user_id,channel,role,content,skill,meta) VALUES (%s,%s,'assistant',%s,%s,%s)",
                  (user["id"], channel, res["answer"], res["skill"],
                   Jsonb({"sources": res["sources"], "warnings": res["warnings"], "tools": res["tools_used"]})))
    audit.record("ask", user, channel, question, res["skill"], res["files_accessed"], True)
    return res
