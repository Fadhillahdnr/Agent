from copilot.embeddings import HashEmbedder
from copilot.search import hybrid_search


def top(q, **kw):
    return hybrid_search(q, embedder=HashEmbedder(384), **kw)


def test_keyword_finds_discount_logic(state):
    res = top("apply_discount DISCOUNT_THRESHOLD")
    assert res and "sample-shop/src/pricing.py" in [r["path"] for r in res[:3]]
    assert "keyword" in res[0]["matched_by"]


def test_camelcase_and_identifier_splitting(state):
    res = top("cancel order window")  # cocok dengan cancel_order / CANCEL_WINDOW
    assert any(r["path"] == "sample-shop/src/orders.py" for r in res)


def test_indonesian_query_hits_docs(state):
    res = top("diskon pesanan", kinds=["doc"])
    assert res and all(r["kind"] == "doc" for r in res)
    assert any("requirements.md" in r["path"] or "README" in r["path"] for r in res)


def test_filters_by_kind_and_path(state):
    assert all(r["kind"] == "test" for r in top("discount", kinds=["test"]))
    assert all(r["path"].startswith("sample-shop/src/") for r in top("order", path_prefix="sample-shop/src/"))


def test_results_carry_line_ranges(state):
    r = top("reduce_stock")[0]
    assert r["start_line"] >= 1 and r["end_line"] >= r["start_line"] and r["text"]


def test_empty_and_stopword_queries(state):
    assert top("yang dan di") == []
    assert top("zzzzqqqq_tidak_ada_apa_apa", k=3) is not None
