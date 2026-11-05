import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.environ.get("DATABASE_URL", "postgresql://copilot:copilot@db:5432/copilot")
TEST_DB = "copilot_test"
TEST_URL = BASE_URL.rsplit("/", 1)[0] + "/" + TEST_DB
SAMPLE_SRC = ROOT / "examples" / "sample-shop"

os.environ.update(
    DATABASE_URL=TEST_URL, EMBEDDING_PROVIDER="hash", LLM_PROVIDER="offline", ADMIN_USERNAME="admin",
    ADMIN_PASSWORD="admin-password-123", INTERNAL_API_TOKEN="internal-test-token", SCAN_INTERVAL_SECONDS="5",
)
tmp_root = Path(tempfile.mkdtemp(prefix="copilot-test-"))
PROJECT = tmp_root / "projects"
os.environ["PROJECT_ROOT"] = str(PROJECT)


def make_project(dest: Path):
    """Salin sample-shop (tanpa .git lama) dan buat riwayat Git baru."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SAMPLE_SRC, dest, ignore=shutil.ignore_patterns(".git"))
    subprocess.run(["sh", str(ROOT / "scripts" / "make_sample_git.sh"), str(dest)], check=True, capture_output=True)


def snapshot(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
    return out


def truncate_all():
    from copilot import db
    with db.conn() as c:
        c.execute("TRUNCATE chunks, files, git_commits, git_branches, tasks, repos, messages, audit_log, sessions, index_state RESTART IDENTITY CASCADE")
        c.commit()


def full_index(root: Path):
    from copilot.embeddings import HashEmbedder
    from copilot.gitsync import sync_git
    from copilot.indexer import index_all
    s = index_all(embedder=HashEmbedder(384), root=str(root))
    s["git"] = sync_git(root=str(root))
    return s


@pytest.fixture(scope="session", autouse=True)
def _db():
    with psycopg.connect(BASE_URL, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {TEST_DB}")
    from copilot import db
    db.reset_pool()
    db.init_schema()
    make_project(PROJECT / "sample-shop")
    yield
    db.reset_pool()
    shutil.rmtree(tmp_root, ignore_errors=True)


@pytest.fixture(scope="session")
def indexed(_db):
    truncate_all()
    before = snapshot(PROJECT)
    stats = full_index(PROJECT)
    return {"stats": stats, "before": before}


@pytest.fixture()
def state(indexed):
    """Index utama dalam keadaan bersih untuk tiap tes."""
    return indexed


@pytest.fixture()
def mutable(_db, tmp_path):
    """Project salinan yang boleh diubah tes; index utama dipulihkan sesudahnya."""
    root = tmp_path / "mp"
    make_project(root / "sample-shop")
    truncate_all()
    yield root
    truncate_all()
    full_index(PROJECT)


@pytest.fixture()
def client(indexed):
    from fastapi.testclient import TestClient
    from copilot import auth
    from copilot.api import app
    with TestClient(app) as c:
        auth.chat_limiter.hits.clear()
        auth.login_failures.hits.clear()
        yield c


def login(client, username="admin", password="admin-password-123"):
    r = client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
