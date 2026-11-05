import json
import subprocess

import pytest

from copilot import auth, db, gitutil, service
from copilot.tools import ToolBox

from conftest import login


def call(box, name, **args):
    out = box.call(name, args)
    return json.loads(out.split("\n", 1)[1].rsplit("\n", 1)[0]), out


def test_read_file_returns_redacted_content_with_lines(state):
    data, raw = call(ToolBox("member"), "read_project_file", path="sample-shop/src/orders.py")
    assert "S3cretPassw0rd" not in raw and "[REDACTED" in data["content"]
    assert data["content"].startswith("1: ")


@pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd", "sample-shop/../../etc/hosts",
                                  "sample-shop/.env", "sample-shop/deploy.pem", "sample-shop/node_modules/x/i.js",
                                  "sample-shop/logo.bin", "sample-shop/.git/config"])
def test_read_file_blocks_traversal_secrets_and_unindexed(state, path):
    data, raw = call(ToolBox("member"), "read_project_file", path=path)
    assert "error" in data and "content" not in data
    assert "SuperSecretEnvValue123" not in raw


def test_viewer_cannot_read_files_or_show_commits(state):
    box = ToolBox("viewer")
    assert "read_project_file" not in {t["name"] for t in box.definitions()}
    assert "tidak diizinkan" in call(box, "read_project_file", path="sample-shop/README.md")[0]["error"]
    assert "tidak diizinkan" in call(box, "git_show", repo="sample-shop", rev="abc1234")[0]["error"]
    assert call(box, "search_project", query="diskon")[0]  # pencarian tetap boleh


def test_list_directory_hides_ignored_and_secret_names(state):
    data, _ = call(ToolBox("member"), "list_directory", path="sample-shop")
    assert "src/" in data and ".env" not in data and "node_modules/" not in data and "deploy.pem" not in data


def test_file_content_is_wrapped_as_untrusted_data(state):
    _, raw = call(ToolBox("member"), "read_project_file", path="sample-shop/docs/injection.md")
    assert raw.startswith('<untrusted_data tool="read_project_file">') and raw.endswith("</untrusted_data>")
    assert raw.count("</untrusted_data>") == 1


def test_git_only_allows_read_commands(state):
    for cmd in ["push", "commit", "config", "checkout", "reset", "fetch", "clean"]:
        with pytest.raises(PermissionError):
            gitutil.run_git("/tmp", cmd)
    assert "show" in gitutil.ALLOWED and "push" not in gitutil.ALLOWED


def test_git_does_not_execute_repo_config(mutable, tmp_path):
    """diff.external/textconv di .git/config project tidak boleh dieksekusi."""
    repo = mutable / "sample-shop"
    marker = tmp_path / "pwned"
    cfg = repo / ".git" / "config"
    cfg.write_text(cfg.read_text() + f'\n[diff]\n\texternal = sh -c "touch {marker}"\n[core]\n\tfsmonitor = "touch {marker}"\n')
    (repo / ".gitattributes").write_text("*.py diff=evil\n")
    cfg.write_text(cfg.read_text() + f'\n[diff "evil"]\n\ttextconv = sh -c "touch {marker}; cat"\n')
    h = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    gitutil.show(str(repo), h)
    gitutil.commits(str(repo), 10)
    assert not marker.exists()


def test_member_can_use_tools_viewer_rate_limit_is_lower(state):
    from copilot.config import get_settings
    s = get_settings()
    assert s.rate_limit_viewer < s.rate_limit_member


def test_unauthenticated_requests_are_rejected(client):
    for method, path in [("get", "/api/me"), ("post", "/api/chat"), ("get", "/api/history"), ("get", "/api/status"),
                         ("post", "/api/admin/reindex"), ("get", "/api/admin/audit")]:
        r = getattr(client, method)(path, **({"json": {"message": "x"}} if method == "post" else {}))
        assert r.status_code == 401, path


def test_wrong_password_and_brute_force_throttle(client):
    for _ in range(5):
        assert client.post("/api/login", json={"username": "admin", "password": "salah-salah-1"}).status_code == 401
    assert client.post("/api/login", json={"username": "admin", "password": "admin-password-123"}).status_code == 429


def test_roles_limit_admin_endpoints(client):
    login(client)
    assert client.post("/api/admin/users", json={"username": "vera", "password": "viewer-pass-123", "role": "viewer"}).status_code == 200
    client.cookies.clear()
    login(client, "vera", "viewer-pass-123")
    assert client.get("/api/admin/audit").status_code == 403
    assert client.post("/api/admin/reindex").status_code == 403
    assert client.post("/api/admin/users", json={"username": "x", "password": "xxxxxxxxxxx", "role": "admin"}).status_code == 403


def test_weak_password_rejected(client):
    login(client)
    assert client.post("/api/admin/users", json={"username": "w", "password": "short", "role": "member"}).status_code == 400


def test_telegram_whitelist_and_internal_token(client):
    h = {"X-Internal-Token": "internal-test-token"}
    body = {"telegram_id": 999001, "message": "diskon"}
    assert client.post("/api/telegram/ask", json=body).status_code == 403          # tanpa token
    assert client.post("/api/telegram/ask", json=body, headers={"X-Internal-Token": "salah"}).status_code == 403
    assert client.post("/api/telegram/ask", json=body, headers=h).status_code == 403  # token benar tapi id tidak di whitelist
    login(client)
    client.post("/api/admin/users", json={"username": "tg_user", "role": "member", "telegram_id": 999001})
    r = client.post("/api/telegram/ask", json=body, headers=h)
    assert r.status_code == 200 and r.json()["sources"]
    with db.conn() as c:
        denied = c.execute("SELECT count(*) n FROM audit_log WHERE event='telegram_denied'").fetchone()["n"]
    assert denied >= 1


def test_rate_limit_enforced(client):
    login(client)
    client.post("/api/admin/users", json={"username": "rl", "password": "rate-limit-pass1", "role": "viewer"})
    client.cookies.clear()
    login(client, "rl", "rate-limit-pass1")
    from copilot.config import get_settings
    codes = [client.post("/api/chat", json={"message": "diskon"}).status_code for _ in range(get_settings().rate_limit_viewer + 2)]
    assert codes[0] == 200 and codes[-1] == 429


def test_audit_log_records_question_and_files(client):
    login(client)
    assert client.post("/api/chat", json={"message": "Di mana fungsi apply_discount?", "skill": "developer"}).status_code == 200
    rows = client.get("/api/admin/audit").json()
    ask = next(r for r in rows if r["event"] == "ask")
    assert "apply_discount" in ask["question"] and ask["files_accessed"] and ask["skill"] == "developer"


def test_secret_in_question_is_redacted_in_audit_and_history(client):
    login(client)
    client.post("/api/chat", json={"message": "kenapa password = 'Sup3rSecretValue9' tidak jalan?"})
    rows = client.get("/api/admin/audit").json()
    hist = client.get("/api/history").json()
    assert "Sup3rSecretValue9" not in json.dumps(rows, default=str) + json.dumps(hist, default=str)


def test_conversation_history_is_per_user(client):
    login(client)
    client.post("/api/chat", json={"message": "pertanyaan milik admin tentang diskon"})
    client.post("/api/admin/users", json={"username": "other", "password": "other-user-pass1", "role": "member"})
    client.cookies.clear()
    login(client, "other", "other-user-pass1")
    assert client.get("/api/history").json() == []
