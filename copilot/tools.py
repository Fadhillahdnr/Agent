"""Tool yang boleh dipakai agent. Semuanya hanya-baca, terkurung di PROJECT_ROOT, dan hanya untuk file yang terindeks
(sehingga .gitignore, file biner, dan file secret otomatis tidak terjangkau). Isi project dikembalikan sebagai DATA."""
import json
import os
import re

from . import gitutil, tasks
from .config import get_settings
from .db import conn
from .scanner import inside_root
from .search import hybrid_search
from .secrets import is_secret_path, redact

PERMISSIONS = {
    "admin": {"search_project", "read_project_file", "list_directory", "grep_project", "git_log", "git_show", "list_tasks", "project_overview"},
    "member": {"search_project", "read_project_file", "list_directory", "grep_project", "git_log", "git_show", "list_tasks", "project_overview"},
    "viewer": {"search_project", "list_directory", "git_log", "list_tasks", "project_overview"},
}

TOOL_DEFS = [
    {"name": "project_overview", "description": "Ringkasan repo, bahasa, jumlah file per jenis, dan file kunci (README, compose, manifest).",
     "schema": {"type": "object", "properties": {}}},
    {"name": "search_project", "description": "Pencarian hybrid (keyword+semantic) di seluruh isi project. Mengembalikan potongan kode/dokumen dengan path dan nomor baris.",
     "schema": {"type": "object", "properties": {
         "query": {"type": "string"}, "k": {"type": "integer", "description": "jumlah hasil, maks 15"},
         "repo": {"type": "string"}, "path_prefix": {"type": "string"},
         "kinds": {"type": "array", "items": {"type": "string", "enum": ["code", "doc", "config", "schema", "api_spec", "test", "migration", "deploy"]}}},
         "required": ["query"]}},
    {"name": "read_project_file", "description": "Baca rentang baris sebuah file terindeks (maks 200 baris).",
     "schema": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}},
    {"name": "list_directory", "description": "Daftar isi direktori (hanya file terindeks). path kosong = root.",
     "schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "grep_project", "description": "Cari regex pada isi terindeks; mengembalikan path:baris persis. Untuk mencari pemakai suatu simbol.",
     "schema": {"type": "object", "properties": {"pattern": {"type": "string"}, "path_prefix": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "git_log", "description": "Riwayat commit terindeks. Filter opsional: repo, path file, kata di pesan.",
     "schema": {"type": "object", "properties": {"repo": {"type": "string"}, "path": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "git_show", "description": "Detail satu commit (stat + patch, terpotong).",
     "schema": {"type": "object", "properties": {"repo": {"type": "string"}, "rev": {"type": "string"}}, "required": ["repo", "rev"]}},
    {"name": "list_tasks", "description": "Task dari TODO/FIXME, checklist dokumen, branch, dan commit, dengan status berbasis bukti.",
     "schema": {"type": "object", "properties": {"repo": {"type": "string"}, "status": {"type": "string", "enum": ["selesai", "sedang dikerjakan", "belum dikerjakan", "tidak diketahui"]}}}},
]


def wrap(name: str, payload) -> str:
    body = json.dumps(payload, ensure_ascii=False, default=str).replace("</untrusted_data", "<\\/untrusted_data")
    return f'<untrusted_data tool="{name}">\n{redact(body)}\n</untrusted_data>'


class ToolBox:
    def __init__(self, user_role: str, preferred_kinds: "list[str] | None" = None):
        self.role = user_role
        self.allowed = PERMISSIONS.get(user_role, set())
        self.preferred_kinds = preferred_kinds or []
        self.accessed: set[str] = set()
        self.used: list[str] = []

    def definitions(self):
        return [t for t in TOOL_DEFS if t["name"] in self.allowed]

    def call(self, name: str, args: dict) -> str:
        self.used.append(name)
        if name not in self.allowed:
            return wrap(name, {"error": f"tool '{name}' tidak diizinkan untuk peran '{self.role}'"})
        try:
            return wrap(name, getattr(self, "t_" + name)(**{k: v for k, v in (args or {}).items()}))
        except TypeError as e:
            return wrap(name, {"error": f"argumen tidak valid: {e}"})
        except Exception as e:
            return wrap(name, {"error": str(e)[:200]})

    # ---- implementasi ----
    def t_project_overview(self):
        with conn() as c:
            repos = c.execute("SELECT name, has_git, default_branch, last_indexed FROM repos ORDER BY name").fetchall()
            kinds = c.execute("SELECT repo, kind, count(*) n FROM files GROUP BY repo, kind").fetchall()
            langs = c.execute("SELECT repo, lang, count(*) n FROM files GROUP BY repo, lang ORDER BY n DESC").fetchall()
            key = c.execute(
                r"""SELECT repo, path FROM files WHERE lower(path) ~ '(^|/)(readme[^/]*|docker-compose[^/]*|dockerfile|package\.json|requirements\.txt|pom\.xml|go\.mod|composer\.json|pubspec\.yaml|openapi[^/]*|swagger[^/]*)$'
                    ORDER BY length(path) LIMIT 60""").fetchall()
        out = []
        for r in repos:
            out.append({"repo": r["name"], "git": r["has_git"], "default_branch": r["default_branch"],
                        "files_by_kind": {k["kind"]: k["n"] for k in kinds if k["repo"] == r["name"]},
                        "top_languages": [l["lang"] for l in langs if l["repo"] == r["name"]][:4],
                        "key_files": [k["path"] for k in key if k["repo"] == r["name"]][:8]})
        return out

    def t_search_project(self, query: str, k: int = 8, repo=None, path_prefix=None, kinds=None):
        k = max(1, min(int(k), 15))
        res = hybrid_search(query, k=k, repo=repo, path_prefix=path_prefix, kinds=kinds)
        if not res and not kinds and self.preferred_kinds:
            res = []
        for r in res:
            self.accessed.add(r["path"])
        return [{"path": r["path"], "start_line": r["start_line"], "end_line": r["end_line"], "kind": r["kind"],
                 "symbol": r["symbol"], "matched_by": r["matched_by"], "text": r["text"][:1800]} for r in res]

    def _indexed(self, c, path):
        return c.execute("SELECT repo, n_lines FROM files WHERE path=%s", (path,)).fetchone()

    def t_read_project_file(self, path: str, start_line: int = 1, end_line: int = 200):
        s = get_settings()
        if is_secret_path(path):
            raise PermissionError("file secret tidak boleh dibaca")
        full = inside_root(s.project_root, path)
        if not full:
            raise PermissionError("path di luar project")
        with conn() as c:
            row = self._indexed(c, path)
        if not row:
            raise FileNotFoundError("file tidak ditemukan di index (mungkin diabaikan oleh .gitignore atau bukan file teks)")
        start_line = max(1, int(start_line))
        end_line = min(int(end_line), start_line + 199, row["n_lines"])
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            lines = redact(f.read()).split("\n")
        self.accessed.add(path)
        return {"path": path, "start_line": start_line, "end_line": end_line, "total_lines": row["n_lines"],
                "content": "\n".join(f"{i}: {lines[i - 1]}" for i in range(start_line, min(end_line, len(lines)) + 1))}

    def t_list_directory(self, path: str = ""):
        path = path.strip("/")
        prefix = path + "/" if path else ""
        with conn() as c:
            rows = c.execute("SELECT path FROM files WHERE path LIKE %s ORDER BY path LIMIT 5000", (prefix.replace("%", "") + "%",)).fetchall()
        entries = {}
        for r in rows:
            rest = r["path"][len(prefix):]
            head = rest.split("/", 1)
            entries[head[0] + ("/" if len(head) > 1 else "")] = True
        return sorted(entries)[:200]

    def t_grep_project(self, pattern: str, path_prefix: str = ""):
        if len(pattern) > 200:
            raise ValueError("pattern terlalu panjang")
        rx = re.compile(pattern, re.I)
        with conn() as c:
            c.execute("SET LOCAL statement_timeout = 4000")
            rows = c.execute("SELECT path, start_line, text FROM chunks WHERE text ~* %s AND path LIKE %s LIMIT 400",
                             (pattern, path_prefix.replace("%", "") + "%")).fetchall()
        hits, seen = [], set()
        for r in rows:
            for i, line in enumerate(r["text"].split("\n")):
                ln = r["start_line"] + i
                if rx.search(line) and (r["path"], ln) not in seen:
                    seen.add((r["path"], ln))
                    hits.append({"path": r["path"], "line": ln, "text": line.strip()[:200]})
        hits.sort(key=lambda h: (h["path"], h["line"]))
        for h in hits[:40]:
            self.accessed.add(h["path"])
        return hits[:40]

    def t_git_log(self, repo=None, path=None, query=None, limit: int = 15):
        limit = max(1, min(int(limit), 40))
        flt, p = "", []
        if repo:
            flt += " AND repo=%s"
            p.append(repo)
        if query:
            flt += " AND (subject ILIKE %s OR body ILIKE %s)"
            p += [f"%{query}%"] * 2
        if path:
            flt += " AND (%s = ANY(files) OR EXISTS (SELECT 1 FROM unnest(files) f WHERE %s LIKE '%%/' || f))"
            p += [path, path]
        with conn() as c:
            rows = c.execute(f"SELECT repo, hash, author, committed_at, subject, files FROM git_commits WHERE TRUE {flt} ORDER BY committed_at DESC LIMIT {limit}", p).fetchall()
        return [{"repo": r["repo"], "hash": r["hash"][:7], "author": r["author"], "date": r["committed_at"].date().isoformat(),
                 "subject": r["subject"], "files": r["files"][:10]} for r in rows]

    def t_git_show(self, repo: str, rev: str):
        with conn() as c:
            r = c.execute("SELECT root_rel, has_git FROM repos WHERE name=%s", (repo,)).fetchone()
            ok = c.execute("SELECT 1 FROM git_commits WHERE repo=%s AND hash LIKE %s", (repo, rev + "%")).fetchone()
        if not r or not r["has_git"] or not ok:
            raise FileNotFoundError("commit tidak ditemukan di repo tersebut")
        return {"commit": gitutil.show(os.path.normpath(os.path.join(get_settings().project_root, r["root_rel"])), rev)}

    def t_list_tasks(self, repo=None, status=None):
        return tasks.list_tasks(repo=repo, status=status)
