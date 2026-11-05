from .db import conn
from .secrets import redact


def record(event: str, user: "dict | None" = None, channel: str = "", question: str = "", skill: str = "",
           files: "list[str] | None" = None, ok: bool = True, detail: str = "") -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO audit_log(user_id,username,channel,event,question,skill,files_accessed,ok,detail)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (user["id"] if user else None, user["username"] if user else None, channel, event,
             redact(question)[:2000], skill, files or [], ok, redact(detail)[:500]))
