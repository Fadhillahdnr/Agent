"""Verifikasi sitasi pada jawaban: path:baris harus ada di index, commit harus ada di riwayat Git."""
import re

from .db import conn

FILE_CITE = re.compile(r"\[([^\[\]\n]+?):L(\d+)(?:-L?(\d+))?\]")
COMMIT_CITE = re.compile(r"\[commit:([0-9a-fA-F]{7,40})\]")


def verify(answer: str):
    """Mengembalikan (jawaban_dengan_sitasi_tidak_valid_ditandai, sources, warnings)."""
    sources, warnings = [], []
    with conn() as c:
        files = {r["path"]: r["n_lines"] for r in c.execute("SELECT path, n_lines FROM files").fetchall()}

        def file_sub(m):
            path, a, b = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
            n = files.get(path)
            if n is None or a < 1 or b < a or b > n:
                warnings.append(f"sitasi tidak valid: {m.group(0)}")
                return f"[sitasi tidak valid: {path}:L{a}-L{b}]"
            sources.append({"type": "file", "path": path, "start_line": a, "end_line": b})
            return m.group(0)

        def commit_sub(m):
            h = m.group(1).lower()
            r = c.execute("SELECT repo, hash FROM git_commits WHERE hash LIKE %s LIMIT 1", (h + "%",)).fetchone()
            if not r:
                warnings.append(f"commit tidak ditemukan: {h}")
                return f"[commit tidak ditemukan: {h}]"
            sources.append({"type": "commit", "repo": r["repo"], "hash": r["hash"][:12]})
            return m.group(0)

        answer = FILE_CITE.sub(file_sub, answer)
        answer = COMMIT_CITE.sub(commit_sub, answer)
    uniq = list({tuple(sorted(s.items())): s for s in sources}.values())
    return answer, uniq, warnings
