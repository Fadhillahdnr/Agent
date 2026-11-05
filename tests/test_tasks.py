import subprocess

from copilot import db, tasks

from conftest import full_index


def by_title(items, needle):
    return [t for t in items if needle in t["title"]]


def test_todo_and_fixme_found_with_path_and_line(state):
    items = tasks.list_tasks()
    todo = by_title(items, "integrasi pembayaran dengan gateway")[0]
    assert todo["status"] == "belum dikerjakan" and "sample-shop/src/orders.py:L" in todo["evidence"]
    assert by_title(items, "FIXME")


def test_unmerged_branch_is_in_progress_with_evidence(state):
    br = [t for t in tasks.list_tasks() if t["source"] == "branch"]
    assert br and br[0]["status"] == "sedang dikerjakan" and "feature/payment" in br[0]["title"]
    assert "[commit:" in br[0]["evidence"]


def test_commits_with_conventional_prefix_are_done_with_hash(state):
    done = [t for t in tasks.list_tasks() if t["source"] == "commit"]
    assert done and all(t["status"] == "selesai" and t["evidence"].startswith("[commit:") for t in done)


def test_doc_checkbox_checked_is_not_assumed_done(state):
    item = by_title(tasks.list_tasks(), "Modul diskon")[0]
    assert item["status"] == "tidak diketahui"
    assert by_title(tasks.list_tasks(), "Integrasi pembayaran")[0]["status"] == "belum dikerjakan"


def test_removed_todo_without_commit_is_unknown_then_done_with_commit(mutable):
    root = mutable
    full_index(root)
    f = root / "sample-shop" / "src" / "orders.py"
    f.write_text(f.read_text().replace("    # TODO: integrasi pembayaran dengan gateway\n", ""))
    full_index(root)
    t = by_title(tasks.list_tasks(), "integrasi pembayaran dengan gateway")[0]
    assert t["status"] == "tidak diketahui"  # dihapus dari file, tetapi belum ada commit sebagai bukti
    repo = str(root / "sample-shop")
    env = {"GIT_AUTHOR_DATE": "2035-01-01T00:00:00", "GIT_COMMITTER_DATE": "2035-01-01T00:00:00", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    subprocess.run(["git", "-C", repo, "-c", "user.email=a@b.c", "-c", "user.name=x", "commit", "-qam", "feat: pembayaran selesai"],
                   check=True, capture_output=True, env=env)
    full_index(root)
    t = by_title(tasks.list_tasks(), "integrasi pembayaran dengan gateway")[0]
    assert t["status"] == "selesai" and "[commit:" in t["evidence"]


def test_remote_with_origin_head_does_not_break_git_sync(mutable, tmp_path):
    """Regresi: repo yang punya refs/remotes/origin/HEAD pernah membuat sinkronisasi Git gagal total."""
    root = mutable
    repo = root / "sample-shop"
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    run("update-ref", "refs/remotes/origin/main", "HEAD")
    run("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    run("update-ref", "refs/remotes/origin/feature/payment", "feature/payment")
    stats = full_index(root)["git"]
    assert stats["repos"] == 1 and stats["commits"] >= 3
    assert [t for t in tasks.list_tasks() if t["source"] == "branch"]
