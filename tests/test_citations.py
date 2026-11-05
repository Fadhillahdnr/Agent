from copilot.citations import verify
from copilot.db import conn


def n_lines(path):
    with conn() as c:
        return c.execute("SELECT n_lines FROM files WHERE path=%s", (path,)).fetchone()["n_lines"]


def test_valid_file_and_commit_citations_pass(state):
    with conn() as c:
        h = c.execute("SELECT hash FROM git_commits LIMIT 1").fetchone()["hash"][:7]
    ans, sources, warns = verify(f"Ambang diskon [sample-shop/src/pricing.py:L2-L3] dan [commit:{h}].")
    assert not warns and len(sources) == 2
    assert "tidak valid" not in ans


def test_invalid_citations_are_flagged_not_trusted(state):
    n = n_lines("sample-shop/src/pricing.py")
    bad = f"[sample-shop/src/pricing.py:L1-L{n + 50}] [tidak/ada.py:L1-L2] [commit:deadbeef00]"
    ans, sources, warns = verify(bad)
    assert sources == [] and len(warns) == 3
    assert "sitasi tidak valid" in ans and "commit tidak ditemukan" in ans


def test_last_line_is_valid_and_zero_is_not(state):
    p = "sample-shop/src/pricing.py"
    n = n_lines(p)
    assert verify(f"[{p}:L{n}]")[1]
    assert not verify(f"[{p}:L0-L3]")[1]
    assert not verify(f"[{p}:L5-L3]")[1]
