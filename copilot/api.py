"""API + web chat. Dengan compose, hanya terbuka di 127.0.0.1."""
import hmac
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import audit, auth, db, service
from .config import get_settings
from .skills import load_skills

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
COOKIE = "copilot_session"
WEB = os.path.join(os.path.dirname(__file__), "web")


@asynccontextmanager
async def lifespan(app):
    db.init_schema()
    auth.bootstrap_users()
    yield


app = FastAPI(title="Project Copilot", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


class Login(BaseModel):
    username: str
    password: str


class Chat(BaseModel):
    message: str
    skill: str | None = None


class NewUser(BaseModel):
    username: str
    password: str | None = None
    role: str = "member"
    telegram_id: int | None = None


class TgAsk(BaseModel):
    telegram_id: int
    message: str
    skill: str | None = None


def current_user(token: str | None = Cookie(default=None, alias=COOKIE)) -> dict:
    u = auth.user_from_token(token)
    if not u:
        raise HTTPException(401, "belum login")
    return u


def admin_only(u: dict = Depends(current_user)) -> dict:
    if u["role"] != "admin":
        raise HTTPException(403, "hanya admin")
    return u


@app.get("/health")
def health():
    with db.conn() as c:
        c.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    key = (request.client.host if request.client else "?", body.username.lower())
    if auth.login_failures.count(key) >= 5:
        audit.record("login", None, "web", body.username, ok=False, detail="throttled")
        raise HTTPException(429, "terlalu banyak percobaan login, coba beberapa menit lagi")
    token = auth.login(body.username, body.password)
    if not token:
        auth.login_failures.allow(key, 10**6)  # mencatat kegagalan
        audit.record("login", None, "web", body.username, ok=False, detail="gagal")
        raise HTTPException(401, "username atau password salah")
    auth.login_failures.hits.pop(key, None)
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=get_settings().secure_cookies,
                        max_age=get_settings().session_ttl_hours * 3600)
    audit.record("login", {"id": None, "username": body.username}, "web")
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response, token: str | None = Cookie(default=None, alias=COOKIE)):
    if token:
        auth.logout(token)
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(u: dict = Depends(current_user)):
    return {"username": u["username"], "role": u["role"]}


@app.get("/api/skills")
def skills(u: dict = Depends(current_user)):
    return [{"name": s.name, "title": s.title, "description": s.description} for s in load_skills().values()]


def _run(user: dict, message: str, skill: str | None, channel: str):
    if not message.strip():
        raise HTTPException(400, "pertanyaan kosong")
    if skill and skill not in load_skills() and skill != "auto":
        raise HTTPException(400, "skill tidak dikenal")
    try:
        return service.ask(user, message, channel, None if skill in (None, "", "auto") else skill)
    except service.RateLimited:
        raise HTTPException(429, "rate limit terlampaui, coba lagi sebentar lagi")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "gagal memproses pertanyaan (lihat log server)")


@app.post("/api/chat")
def chat(body: Chat, u: dict = Depends(current_user)):
    return _run(u, body.message, body.skill, "web")


@app.get("/api/history")
def history(limit: int = 30, u: dict = Depends(current_user)):
    with db.conn() as c:
        rows = c.execute("SELECT role, content, skill, channel, meta, created_at FROM messages WHERE user_id=%s ORDER BY id DESC LIMIT %s",
                         (u["id"], min(limit, 100) * 2)).fetchall()
    return list(reversed(rows))


@app.get("/api/status")
def status(u: dict = Depends(current_user)):
    with db.conn() as c:
        n = c.execute("SELECT (SELECT count(*) FROM files) files, (SELECT count(*) FROM chunks) chunks, (SELECT count(*) FROM repos) repos, (SELECT count(*) FROM git_commits) commits").fetchone()
    last, hb = db.get_state("last_index"), db.get_state("worker_heartbeat")
    return {**n, "last_index": last["value"] if last else None, "last_index_at": last["updated_at"] if last else None,
            "worker_alive": bool(hb)}


@app.post("/api/admin/reindex")
def reindex(u: dict = Depends(admin_only)):
    db.set_state("reindex_request", {"by": u["username"]})
    audit.record("reindex", u, "web")
    return {"ok": True}


@app.get("/api/admin/audit")
def audit_log(limit: int = 100, u: dict = Depends(admin_only)):
    with db.conn() as c:
        return c.execute("SELECT ts, username, channel, event, question, skill, files_accessed, ok, detail FROM audit_log ORDER BY id DESC LIMIT %s", (min(limit, 500),)).fetchall()


@app.post("/api/admin/users")
def new_user(body: NewUser, u: dict = Depends(admin_only)):
    try:
        r = auth.create_user(body.username, body.password, body.role, body.telegram_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.record("create_user", u, "web", detail=f"{body.username}:{body.role}")
    return r


# ---- Telegram (dipanggil bot lewat jaringan internal compose, dengan token internal) ----
def internal(x_internal_token: str | None = Header(default=None)):
    expected = get_settings().internal_token
    if not expected:
        raise HTTPException(503, "INTERNAL_API_TOKEN belum diatur")
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(403, "token internal salah")


@app.post("/api/telegram/ask", dependencies=[Depends(internal)])
def tg_ask(body: TgAsk):
    u = auth.user_from_telegram(body.telegram_id)
    if not u:
        audit.record("telegram_denied", None, "telegram", "", ok=False, detail=f"id={body.telegram_id}")
        raise HTTPException(403, "user tidak ada di whitelist")
    return _run(u, body.message, body.skill, "telegram")


class TgPref(BaseModel):
    telegram_id: int
    skill: str | None = None


@app.post("/api/telegram/pref", dependencies=[Depends(internal)])
def tg_pref(body: TgPref):
    u = auth.user_from_telegram(body.telegram_id)
    if not u:
        raise HTTPException(403, "user tidak ada di whitelist")
    if body.skill not in (None, "auto") and body.skill not in load_skills():
        raise HTTPException(400, "skill tidak dikenal")
    with db.conn() as c:
        c.execute("UPDATE users SET skill_pref=%s WHERE id=%s", (None if body.skill in (None, "auto") else body.skill, u["id"]))
    return {"ok": True}
