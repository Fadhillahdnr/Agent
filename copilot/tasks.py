"""Status task berbasis bukti. Tidak ada task 'selesai' tanpa bukti di kode atau riwayat Git."""
from .db import conn

DONE, WIP, TODO, UNKNOWN = "selesai", "sedang dikerjakan", "belum dikerjakan", "tidak diketahui"
CONV = r"^(feat|fix|refactor|perf|docs|test|chore|build|ci)(\(.*\))?!?:"
TICKET = r"\m[A-Z][A-Z0-9]+-[0-9]+\M"


def list_tasks(repo: "str | None" = None, status: "str | None" = None, limit: int = 60) -> list[dict]:
    out = []
    flt, p = ("AND repo=%s", [repo]) if repo else ("", [])
    with conn() as c:
        for t in c.execute(f"SELECT * FROM tasks WHERE TRUE {flt} ORDER BY repo, path, line", p).fetchall():
            if t["source"] == "todo":
                if t["present"]:
                    st, ev = TODO, f"[{t['path']}:L{t['line']}] penanda masih ada di kode"
                elif t["resolved_by"]:
                    st, ev = DONE, f"penanda dihapus dari {t['path']}; file diubah di [commit:{t['resolved_by']}]"
                else:
                    st, ev = UNKNOWN, f"penanda tidak ada lagi di {t['path']} tetapi tidak ada commit yang membuktikan penyelesaian"
            else:  # checklist di dokumen
                if t["present"] and not t["checked"]:
                    st, ev = TODO, f"[{t['path']}:L{t['line']}] checklist dokumen belum dicentang"
                elif t["present"]:
                    st, ev = UNKNOWN, f"[{t['path']}:L{t['line']}] dokumen menyatakan selesai, belum ada bukti di kode/Git"
                else:
                    st, ev = UNKNOWN, f"item hilang dari {t['path']}"
            out.append({"source": t["source"], "repo": t["repo"], "title": t["title"], "status": st, "evidence": ev})
        for b in c.execute(f"SELECT * FROM git_branches WHERE ahead>0 {flt} ORDER BY repo, last_commit_at DESC", p).fetchall():
            out.append({"source": "branch", "repo": b["repo"], "title": f"branch {b['name']}", "status": WIP,
                        "evidence": f"{b['ahead']} commit di depan {b['base']}; terakhir [commit:{b['head']}] \"{b['last_subject']}\""})
        for cm in c.execute(
            f"""SELECT repo, hash, subject FROM git_commits WHERE (subject ~ %s OR subject ~ %s) {flt}
                ORDER BY committed_at DESC LIMIT 40""", [CONV, TICKET, *p]).fetchall():
            out.append({"source": "commit", "repo": cm["repo"], "title": cm["subject"], "status": DONE,
                        "evidence": f"[commit:{cm['hash'][:7]}]"})
    if status:
        out = [t for t in out if t["status"] == status]
    return out[:limit]
