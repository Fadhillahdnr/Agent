import shutil
import time

from copilot import db
from copilot.config import get_settings

from conftest import PROJECT, full_index, snapshot, truncate_all


def paths():
    with db.conn() as c:
        return {r["path"] for r in c.execute("SELECT path FROM files").fetchall()}


def test_indexes_expected_files(state):
    p = paths()
    for want in ["sample-shop/src/pricing.py", "sample-shop/docs/requirements.md", "sample-shop/migrations/001_init.sql",
                 "sample-shop/tests/test_pricing.py", "sample-shop/Dockerfile", "sample-shop/.github/workflows/ci.yml",
                 "sample-shop/.env.example" if False else "sample-shop/README.md"]:
        assert want in p, want


def test_ignores_gitignored_binary_and_secret_files(state):
    p = paths()
    joined = "\n".join(p)
    assert not any(x in joined for x in ["node_modules", "dist/out.js", "logo.bin", "deploy.pem", "/.env", ".git/"])


def test_secrets_never_reach_the_index(state):
    with db.conn() as c:
        blob = " ".join(r["text"] for r in c.execute("SELECT text FROM chunks").fetchall())
        tsv = " ".join(r["t"] for r in c.execute("SELECT tsv::text t FROM chunks").fetchall()).lower()
        msgs = " ".join(r["title"] for r in c.execute("SELECT title FROM tasks").fetchall())
    for leaked in ["S3cretPassw0rd", "SuperSecretEnvValue123", "MIIFAKEFAKE", "abcd1234efgh5678"]:
        assert leaked not in blob and leaked.lower() not in tsv and leaked not in msgs
    assert "[REDACTED" in blob  # DB_PASSWORD di orders.py disamarkan, bukan dihapus diam-diam


def test_project_folder_is_never_modified(state):
    full_index(PROJECT)
    assert snapshot(PROJECT) == state["before"]


def test_incremental_only_changed_files_are_reindexed(mutable):
    root = mutable
    first = full_index(root)
    assert first["added"] > 5
    again = full_index(root)
    assert again["added"] == again["updated"] == again["removed"] == 0
    assert again["unchanged"] == first["added"]
    f = root / "sample-shop" / "src" / "pricing.py"
    time.sleep(0.01)
    f.write_text(f.read_text() + "\n# perubahan baru\n")
    third = full_index(root)
    assert third["updated"] == 1 and third["added"] == 0
    (root / "sample-shop" / "src" / "orders.py").unlink()
    fourth = full_index(root)
    assert fourth["removed"] == 1
    assert "sample-shop/src/orders.py" not in paths()


def test_touch_without_content_change_does_not_rechunk(mutable):
    root = mutable
    full_index(root)
    f = root / "sample-shop" / "README.md"
    f.write_text(f.read_text())  # mtime berubah, isi sama
    s = full_index(root)
    assert s["updated"] == 0 and s["added"] == 0


def test_multi_repo_detection(mutable):
    root = mutable
    other = root / "second"
    other.mkdir()
    (other / "main.py").write_text("def hello():\n    return 1\n")
    s = full_index(root)
    with db.conn() as c:
        repos = {r["name"] for r in c.execute("SELECT name FROM repos").fetchall()}
    assert {"sample-shop", "second"} <= repos
