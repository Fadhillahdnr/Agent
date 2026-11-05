"""Akses Git hanya-baca. Semua perintah memakai opsi yang mencegah eksekusi konfigurasi repo
(diff.external, textconv, fsmonitor, pager) karena isi project hanya boleh diperlakukan sebagai data."""
import os
import subprocess

from .secrets import redact

SAFE = ["git", "-c", "core.fsmonitor=false", "-c", "core.pager=cat", "-c", "safe.directory=*",
        "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never"]
ALLOWED = {"log", "for-each-ref", "rev-list", "show", "rev-parse", "symbolic-ref", "merge-base", "cat-file"}


def run_git(repo_abs: str, *args: str, timeout: int = 60) -> str:
    if args[0] not in ALLOWED:
        raise PermissionError(f"perintah git tidak diizinkan: {args[0]}")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": "/tmp", "GIT_OPTIONAL_LOCKS": "0",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C.UTF-8"}
    extra = ["--no-ext-diff", "--no-textconv"] if args[0] in ("show", "log") else []
    p = subprocess.run([*SAFE, "-C", repo_abs, args[0], *extra, *args[1:]], capture_output=True, timeout=timeout, env=env)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:300])
    return p.stdout.decode("utf-8", "replace")


def default_branch(repo_abs: str) -> "str | None":
    try:
        ref = run_git(repo_abs, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
        if ref:
            return ref
    except Exception:
        pass
    heads = [b for b in _heads(repo_abs)]
    for cand in ("main", "master", "develop", "trunk"):
        if cand in heads:
            return cand
    try:
        return run_git(repo_abs, "symbolic-ref", "--short", "HEAD").strip() or (heads[0] if heads else None)
    except Exception:
        return heads[0] if heads else None


def _heads(repo_abs):
    try:
        return [x for x in run_git(repo_abs, "for-each-ref", "--format=%(refname:short)", "refs/heads").split("\n") if x]
    except Exception:
        return []


def commits(repo_abs: str, limit: int):
    fmt = "%x1e%H%x1f%an%x1f%aI%x1f%s%x1f%b%x1f"
    try:
        out = run_git(repo_abs, "log", "--all", f"--max-count={limit}", f"--format={fmt}", "--name-only", timeout=120)
    except Exception:
        return []
    res = []
    for rec in out.split("\x1e"):
        if not rec.strip():
            continue
        parts = rec.split("\x1f")
        if len(parts) < 6:
            continue
        h, author, date, subject, body, names = parts[:6]
        files = [f for f in names.strip().split("\n") if f][:200]
        res.append({"hash": h, "author": author, "date": date, "subject": redact(subject)[:300],
                    "body": redact(body)[:2000], "files": files})
    return res


def branches(repo_abs: str):
    base = default_branch(repo_abs)
    if not base:
        return base, []
    fmt = "%(refname:short)\x1f%(objectname:short)\x1f%(committerdate:iso-strict)\x1f%(subject)"
    seen, res = set(), []
    for ns in ("refs/heads", "refs/remotes"):
        try:
            out = run_git(repo_abs, "for-each-ref", f"--format={fmt}", ns)
        except Exception:
            continue
        for line in out.split("\n"):
            f = line.split("\x1f")
            if len(f) < 4 or f[0].endswith("/HEAD") or (ns.endswith("remotes") and "/" not in f[0]):
                continue  # refs/remotes/origin/HEAD tampil sebagai "origin" tanpa slash
            short = f[0].split("/", 1)[1] if ns.endswith("remotes") else f[0]
            if short in seen or short == base or f[0] == base:
                continue
            seen.add(short)
            try:
                ahead = int(run_git(repo_abs, "rev-list", "--count", f"{base}..{f[0]}").strip())
            except Exception:
                ahead = 0
            res.append({"name": short, "head": f[1], "date": f[2], "subject": redact(f[3])[:200], "ahead": ahead})
    return base, res


def last_commit_touching(repo_abs: str, path_in_repo: str, since_iso: str) -> "str | None":
    try:
        out = run_git(repo_abs, "log", "--all", "-1", f"--since={since_iso}", "--format=%h", "--", path_in_repo)
        return out.strip() or None
    except Exception:
        return None


def show(repo_abs: str, rev: str, max_chars: int = 6000) -> str:
    if not rev.replace("^", "").replace("~", "").isalnum():
        raise ValueError("rev tidak valid")
    out = run_git(repo_abs, "show", "--stat", "--patch", "--format=%h %an %aI%n%s%n%n%b", rev, "--")
    return redact(out)[:max_chars]
