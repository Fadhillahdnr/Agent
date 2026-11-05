"""Autentikasi (PBKDF2 + sesi di DB), whitelist Telegram, dan pengelolaan user."""
import hashlib
import hmac
import logging
import secrets as pysecrets
import time
from collections import defaultdict, deque

from .config import get_settings
from .db import conn

log = logging.getLogger(__name__)
ROLES = ("admin", "member", "viewer")
ITER = 200_000


def hash_password(pw: str) -> str:
    salt = pysecrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), ITER).hex()
    return f"pbkdf2${ITER}${salt}${h}"


def verify_password(pw: str, stored: "str | None") -> bool:
    if not stored:
        return False
    try:
        _, it, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it)).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


def create_user(username: str, password: "str | None", role: str = "member", telegram_id: "int | None" = None) -> dict:
    if role not in ROLES:
        raise ValueError("role tidak valid")
    if password is not None and len(password) < 10:
        raise ValueError("password minimal 10 karakter")
    with conn() as c:
        return c.execute(
            """INSERT INTO users(username,pw_hash,role,telegram_id) VALUES (%s,%s,%s,%s)
               ON CONFLICT (username) DO UPDATE SET role=EXCLUDED.role, active=TRUE,
                 pw_hash=COALESCE(EXCLUDED.pw_hash, users.pw_hash), telegram_id=COALESCE(EXCLUDED.telegram_id, users.telegram_id)
               RETURNING id, username, role, telegram_id""",
            (username, hash_password(password) if password else None, role, telegram_id)).fetchone()


def bootstrap_users() -> None:
    s = get_settings()
    with conn() as c:
        has_admin = c.execute("SELECT 1 FROM users WHERE role='admin' AND active AND pw_hash IS NOT NULL").fetchone()
    if s.admin_password:
        with conn() as c:
            exists = c.execute("SELECT 1 FROM users WHERE username=%s", (s.admin_username,)).fetchone()
        if not exists:
            create_user(s.admin_username, s.admin_password, "admin")
    elif not has_admin:
        raise RuntimeError("ADMIN_PASSWORD belum diisi di .env (minimal 10 karakter); tidak ada admin untuk login")
    for tid in s.telegram_allowed_ids:
        create_user(f"tg_{tid}", None, "member", tid)


def login(username: str, password: str) -> "str | None":
    with conn() as c:
        u = c.execute("SELECT id, pw_hash FROM users WHERE username=%s AND active", (username,)).fetchone()
        if not u or not verify_password(password, u["pw_hash"]):
            return None
        token = pysecrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (%s,%s, now() + make_interval(hours => %s))",
                  (hashlib.sha256(token.encode()).hexdigest(), u["id"], get_settings().session_ttl_hours))
        c.execute("DELETE FROM sessions WHERE expires_at < now()")
    return token


def user_from_token(token: "str | None") -> "dict | None":
    if not token:
        return None
    with conn() as c:
        return c.execute(
            """SELECT u.id, u.username, u.role, u.skill_pref FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=%s AND s.expires_at > now() AND u.active""",
            (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()


def logout(token: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=%s", (hashlib.sha256(token.encode()).hexdigest(),))


def user_from_telegram(tid: int) -> "dict | None":
    """Whitelist: hanya user aktif dengan telegram_id yang terdaftar."""
    with conn() as c:
        return c.execute("SELECT id, username, role, skill_pref FROM users WHERE telegram_id=%s AND active", (tid,)).fetchone()


class RateLimiter:
    def __init__(self, window: int = 60):
        self.window, self.hits = window, defaultdict(deque)

    def count(self, key) -> int:
        now, q = time.monotonic(), self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return len(q)

    def allow(self, key, limit: int) -> bool:
        now, q = time.monotonic(), self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


chat_limiter = RateLimiter(60)
login_failures = RateLimiter(300)


def chat_limit_for(role: str) -> int:
    s = get_settings()
    return s.rate_limit_viewer if role == "viewer" else s.rate_limit_member
