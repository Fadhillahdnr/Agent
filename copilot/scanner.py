"""Pemindai folder project: patuh .gitignore (bertingkat), abaikan build output, biner, dan file secret."""
import os
from dataclasses import dataclass
from pathlib import Path

import pathspec

from .secrets import is_secret_path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor", "dist", "build", "out", "target",
    ".next", ".nuxt", ".output", ".svelte-kit", ".turbo", ".cache", ".parcel-cache", "coverage", ".nyc_output",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".venv", "venv", "env", ".idea",
    ".vscode", ".gradle", ".dart_tool", "Pods", "DerivedData", ".terraform", "bin", "obj", ".DS_Store",
}
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock", "poetry.lock", "Pipfile.lock",
    "Cargo.lock", "Gemfile.lock", "go.sum", ".DS_Store", "Thumbs.db",
}
SKIP_SUFFIXES = (".min.js", ".min.css", ".map", ".lock", ".log", ".pyc")
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svgz", ".pdf", ".zip", ".gz", ".tar", ".tgz", ".7z",
    ".rar", ".jar", ".war", ".class", ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".woff", ".woff2",
    ".ttf", ".eot", ".otf", ".mp3", ".mp4", ".mov", ".avi", ".wav", ".psd", ".sketch", ".fig", ".xlsx", ".xls",
    ".docx", ".doc", ".pptx", ".ppt", ".sqlite", ".db", ".parquet", ".onnx", ".pt", ".h5", ".apk", ".ipa", ".ino.bin",
}


@dataclass
class ScannedFile:
    rel: str
    abs: str
    repo: str
    size: int
    mtime_ns: int


@dataclass
class RepoInfo:
    name: str
    root_rel: str
    has_git: bool


def _load_spec(path: str):
    try:
        if os.path.getsize(path) > 256_000:
            return None
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f.read().splitlines())
    except OSError:
        return None


def _ignored(specs, abs_path: str, is_dir: bool) -> bool:
    for base, spec in specs:
        try:
            rel = os.path.relpath(abs_path, base).replace(os.sep, "/")
        except ValueError:
            continue
        if spec.match_file(rel + "/" if is_dir else rel):
            return True
    return False


def scan(root: str, max_bytes: int):
    """Mengembalikan (files, repos). Tidak pernah menulis ke root."""
    root = os.path.abspath(root)
    files: list[ScannedFile] = []
    repos: dict[str, RepoInfo] = {}

    def rec(dirpath: str, specs: list, repo: "RepoInfo | None"):
        has_git = os.path.exists(os.path.join(dirpath, ".git"))
        if has_git and (repo is None or repo.root_rel != os.path.relpath(dirpath, root)):
            rel = os.path.relpath(dirpath, root)
            name = os.path.basename(root) if rel == "." else rel.replace(os.sep, "/")
            repo = RepoInfo(name, rel, True)
            repos[name] = repo
        gi = os.path.join(dirpath, ".gitignore")
        if os.path.isfile(gi):
            spec = _load_spec(gi)
            if spec:
                specs = specs + [(dirpath, spec)]
        try:
            entries = sorted(os.scandir(dirpath), key=lambda e: e.name)
        except OSError:
            return
        for e in entries:
            if e.is_symlink():
                continue
            if e.is_dir(follow_symlinks=False):
                if e.name in SKIP_DIRS or _ignored(specs, e.path, True):
                    continue
                child_repo = repo
                if repo is None and dirpath == root and not os.path.exists(os.path.join(e.path, ".git")):
                    child_repo = RepoInfo(e.name, e.name, False)
                    repos.setdefault(e.name, child_repo)
                rec(e.path, specs, child_repo)
            elif e.is_file(follow_symlinks=False):
                name = e.name
                low = name.lower()
                if name in SKIP_FILES or low.endswith(SKIP_SUFFIXES) or os.path.splitext(low)[1] in BINARY_EXT:
                    continue
                if is_secret_path(name) or _ignored(specs, e.path, False):
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if st.st_size > max_bytes or st.st_size == 0:
                    continue
                if repo is None:
                    repo_name = "(root)"
                    repos.setdefault(repo_name, RepoInfo(repo_name, ".", False))
                else:
                    repo_name = repo.name
                files.append(ScannedFile(os.path.relpath(e.path, root).replace(os.sep, "/"), e.path, repo_name,
                                         st.st_size, st.st_mtime_ns))

    rec(root, [], None)
    return files, list(repos.values())


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def inside_root(root: str, rel: str) -> "str | None":
    """Path absolut jika rel berada di dalam root (tanpa traversal/symlink keluar), selain itu None."""
    if not rel or rel.startswith("/") or "\x00" in rel:
        return None
    base = os.path.realpath(root)
    full = os.path.realpath(os.path.join(base, rel))
    try:
        if os.path.commonpath([base, full]) != base:
            return None
    except ValueError:
        return None
    return full
