"""Indexing inkremental: hanya file yang berubah (size/mtime lalu sha256) yang dibaca ulang dan di-embed."""
import hashlib
import logging
import os
import re

from .chunking import chunk_text, classify, detect_lang
from .config import get_settings
from .db import conn, vec_literal
from .embeddings import get_embedder, tokenize
from .scanner import is_binary, scan
from .secrets import redact

log = logging.getLogger(__name__)

TODO_RX = re.compile(r"(?:#|//|/\*|\*|<!--|--|;)\s*(TODO|FIXME|HACK|XXX)\b[:\s(\-]*(.*)")
CHECKBOX_RX = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.+)")


def extract_tasks(text: str, kind: str):
    out = []
    for i, line in enumerate(text.split("\n"), 1):
        m = TODO_RX.search(line)
        if m and kind != "doc":
            title = (m.group(1) + ": " + m.group(2)).strip().rstrip("*/ -->")
            out.append(("todo", i, title[:300], None))
            continue
        if kind == "doc":
            c = CHECKBOX_RX.match(line)
            if c:
                out.append(("doc", i, c.group(2).strip()[:300], c.group(1).lower() == "x"))
            elif TODO_RX.search(line):
                mm = TODO_RX.search(line)
                out.append(("todo", i, (mm.group(1) + ": " + mm.group(2)).strip()[:300], None))
    return out


def _task_key(title: str) -> str:
    return hashlib.sha1(re.sub(r"\W+", " ", title.lower()).strip().encode()).hexdigest()[:16]


def _read_text(abs_path: str, max_bytes: int):
    with open(abs_path, "rb") as f:
        data = f.read(max_bytes + 1)
    if len(data) > max_bytes or is_binary(data):
        return None, None
    return data, data.decode("utf-8", errors="replace")


def _embed_text(path: str, symbol: str, text: str) -> str:
    head = f"{path}" + (f" :: {symbol}" if symbol else "")
    return (head + "\n" + text)[:2000]


def _index_file(c, sf, sha: str, text: str, lang: str, kind: str, embedder):
    text = redact(text)
    chunks = chunk_text(sf.rel, text)
    n_lines = len(text.split("\n")) - (1 if text.endswith("\n") else 0)
    embs = []
    for i in range(0, len(chunks), 32):
        embs.extend(embedder.embed([_embed_text(sf.rel, ch.symbol, ch.text) for ch in chunks[i:i + 32]]))
    row = c.execute(
        """INSERT INTO files(repo,path,sha256,size,mtime_ns,lang,kind,n_lines,indexed_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())
           ON CONFLICT (path) DO UPDATE SET repo=EXCLUDED.repo, sha256=EXCLUDED.sha256, size=EXCLUDED.size,
             mtime_ns=EXCLUDED.mtime_ns, lang=EXCLUDED.lang, kind=EXCLUDED.kind, n_lines=EXCLUDED.n_lines, indexed_at=now()
           RETURNING id""",
        (sf.repo, sf.rel, sha, sf.size, sf.mtime_ns, lang, kind, n_lines),
    ).fetchone()
    fid = row["id"]
    c.execute("DELETE FROM chunks WHERE file_id=%s", (fid,))
    with c.cursor() as cur:
        cur.executemany(
            """INSERT INTO chunks(file_id,repo,path,kind,start_line,end_line,symbol,text,tsv,embedding)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,to_tsvector('simple', %s),%s::vector)""",
            [(fid, sf.repo, sf.rel, kind, ch.start_line, ch.end_line, ch.symbol, ch.text,
              " ".join(tokenize(sf.rel + " " + ch.symbol + " " + ch.text)), vec_literal(e))
             for ch, e in zip(chunks, embs)],
        )
    # sinkronisasi task dari file ini
    seen = set()
    for source, line, title, checked in extract_tasks(text, kind):
        key = _task_key(title)
        seen.add((source, key))
        c.execute(
            """INSERT INTO tasks(repo,source,key,title,path,line,present,checked,first_seen,last_seen)
               VALUES (%s,%s,%s,%s,%s,%s,TRUE,%s,now(),now())
               ON CONFLICT (repo,source,path,key) DO UPDATE SET line=EXCLUDED.line, title=EXCLUDED.title,
                 present=TRUE, checked=EXCLUDED.checked, last_seen=now()""",
            (sf.repo, source, key, title, sf.rel, line, checked),
        )
    c.execute(
        "UPDATE tasks SET present=FALSE WHERE path=%s AND present AND (source,key) NOT IN (SELECT * FROM unnest(%s::text[], %s::text[]))",
        (sf.rel, [s for s, _ in seen], [k for _, k in seen]),
    )
    return len(chunks)


def index_all(embedder=None, root: "str | None" = None) -> dict:
    s = get_settings()
    root = root or s.project_root
    embedder = embedder or get_embedder()
    files, repos = scan(root, s.max_file_bytes)
    stats = {"scanned": len(files), "added": 0, "updated": 0, "unchanged": 0, "removed": 0, "skipped_binary": 0, "chunks": 0}
    with conn() as c:
        existing = {r["path"]: r for r in c.execute("SELECT path, sha256, size, mtime_ns FROM files").fetchall()}
        for r in repos:
            c.execute(
                """INSERT INTO repos(name,root_rel,has_git) VALUES (%s,%s,%s)
                   ON CONFLICT (name) DO UPDATE SET root_rel=EXCLUDED.root_rel, has_git=EXCLUDED.has_git""",
                (r.name, r.root_rel, r.has_git),
            )
        current = {f.rel for f in files}
        gone = [p for p in existing if p not in current]
        if gone:
            c.execute("DELETE FROM files WHERE path = ANY(%s)", (gone,))
            c.execute("UPDATE tasks SET present=FALSE WHERE path = ANY(%s)", (gone,))
            stats["removed"] = len(gone)
        c.commit()
        for sf in files:
            old = existing.get(sf.rel)
            if old and old["size"] == sf.size and old["mtime_ns"] == sf.mtime_ns:
                stats["unchanged"] += 1
                continue
            try:
                data, text = _read_text(sf.abs, s.max_file_bytes)
            except OSError:
                continue
            if data is None:
                stats["skipped_binary"] += 1
                continue
            sha = hashlib.sha256(data).hexdigest()
            if old and old["sha256"] == sha:
                c.execute("UPDATE files SET mtime_ns=%s, size=%s WHERE path=%s", (sf.mtime_ns, sf.size, sf.rel))
                c.commit()
                stats["unchanged"] += 1
                continue
            lang = detect_lang(sf.rel)
            kind = classify(sf.rel, lang)
            try:
                stats["chunks"] += _index_file(c, sf, sha, text, lang, kind, embedder)
                c.commit()
            except Exception:
                c.rollback()
                log.exception("gagal mengindeks %s", sf.rel)
                continue
            stats["updated" if old else "added"] += 1
        c.execute("UPDATE repos SET last_indexed=now() WHERE name = ANY(%s)", ([r.name for r in repos],))
        c.execute("DELETE FROM repos WHERE name <> ALL(%s)", ([r.name for r in repos],))
        c.commit()
    log.info("index: %s", stats)
    return stats
