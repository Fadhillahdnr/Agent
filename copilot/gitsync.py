"""Sinkronisasi riwayat Git (commit, branch) dan resolusi task TODO berdasarkan bukti Git."""
import logging
import os

from . import gitutil
from .config import get_settings
from .db import conn

log = logging.getLogger(__name__)


def sync_git(root: "str | None" = None) -> dict:
    s = get_settings()
    root = root or s.project_root
    stats = {"repos": 0, "commits": 0, "branches": 0, "resolved": 0}
    with conn() as c:
        repos = c.execute("SELECT name, root_rel FROM repos WHERE has_git").fetchall()
        for r in repos:
            repo_abs = os.path.normpath(os.path.join(root, r["root_rel"]))
            try:
                base, brs = gitutil.branches(repo_abs)
                cms = gitutil.commits(repo_abs, s.git_max_commits)
            except Exception:
                log.exception("git gagal untuk %s", r["name"])
                continue
            stats["repos"] += 1
            c.execute("UPDATE repos SET default_branch=%s WHERE name=%s", (base, r["name"]))
            with c.cursor() as cur:
                cur.executemany(
                    """INSERT INTO git_commits(repo,hash,author,committed_at,subject,body,files)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (repo,hash) DO NOTHING""",
                    [(r["name"], x["hash"], x["author"], x["date"], x["subject"], x["body"], x["files"]) for x in cms],
                )
            stats["commits"] += len(cms)
            c.execute("DELETE FROM git_branches WHERE repo=%s", (r["name"],))
            for b in brs:
                c.execute(
                    "INSERT INTO git_branches(repo,name,head,base,ahead,last_commit_at,last_subject) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (r["name"], b["name"], b["head"], base, b["ahead"], b["date"], b["subject"]),
                )
            stats["branches"] += len(brs)
            # TODO yang hilang dari file: selesai hanya jika ada commit yang menyentuh file itu sesudah terakhir terlihat
            gone = c.execute(
                """SELECT t.id, t.path, t.last_seen FROM tasks t JOIN files f ON f.path=t.path
                   WHERE t.repo=%s AND NOT t.present AND t.source='todo' AND t.resolved_by IS NULL""",
                (r["name"],),
            ).fetchall()
            for t in gone:
                rel_in_repo = t["path"] if r["root_rel"] in (".", "") else t["path"][len(r["root_rel"]) + 1:]
                h = gitutil.last_commit_touching(repo_abs, rel_in_repo, t["last_seen"].isoformat())
                if h:
                    c.execute("UPDATE tasks SET resolved_by=%s WHERE id=%s", (h, t["id"]))
                    stats["resolved"] += 1
            c.commit()
    return stats
