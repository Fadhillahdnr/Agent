"""Pencarian hybrid: keyword (tsvector) + semantic (pgvector), digabung dengan Reciprocal Rank Fusion."""
from .config import get_settings
from .db import conn, vec_literal
from .embeddings import get_embedder, query_tokens

RRF_K = 60


def hybrid_search(query: str, k: int = 8, repo: "str | None" = None, path_prefix: "str | None" = None,
                  kinds: "list[str] | None" = None, embedder=None) -> list[dict]:
    toks = query_tokens(query)
    if not toks:
        return []
    embedder = embedder or get_embedder()
    qvec = vec_literal(embedder.embed([query])[0])
    flt, params = "", []
    if repo:
        flt += " AND repo=%s"
        params.append(repo)
    if path_prefix:
        flt += " AND path LIKE %s"
        params.append(path_prefix.replace("%", "") + "%")
    if kinds:
        flt += " AND kind = ANY(%s)"
        params.append(kinds)
    tsq = " | ".join(f"'{t}'" for t in toks[:24])
    pool_n = max(30, k * 4)
    with conn() as c:
        kw = c.execute(
            f"""SELECT id, ts_rank_cd(tsv, q) AS score FROM chunks, to_tsquery('simple', %s) q
                WHERE tsv @@ q {flt} ORDER BY score DESC LIMIT {pool_n}""",
            [tsq, *params],
        ).fetchall()
        sem = c.execute(
            f"""SELECT id, 1 - (embedding <=> %s::vector) AS score FROM chunks
                WHERE TRUE {flt} ORDER BY embedding <=> %s::vector LIMIT {pool_n}""",
            [qvec, *params, qvec],
        ).fetchall()
        fused: dict[int, float] = {}
        for rank, r in enumerate(kw):
            fused[r["id"]] = fused.get(r["id"], 0) + 1 / (RRF_K + rank + 1)
        sem = [r for r in sem if r["score"] >= get_settings().semantic_min_score]  # tetangga terdekat belum tentu relevan
        for rank, r in enumerate(sem):
            fused[r["id"]] = fused.get(r["id"], 0) + 1 / (RRF_K + rank + 1)
        top = sorted(fused, key=fused.get, reverse=True)[:k]
        if not top:
            return []
        rows = {r["id"]: r for r in c.execute(
            "SELECT id, repo, path, kind, start_line, end_line, symbol, text FROM chunks WHERE id = ANY(%s)", (top,)).fetchall()}
    kwids = {r["id"] for r in kw}
    semids = {r["id"] for r in sem}
    out = []
    for i in top:
        r = rows[i]
        r["score"] = round(fused[i], 5)
        r["matched_by"] = [m for m, s in (("keyword", kwids), ("semantic", semids)) if i in s]
        out.append(r)
    return out
