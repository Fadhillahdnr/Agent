from copilot.chunking import chunk_text, classify, detect_lang

PY = '''import os


def alpha():
    return 1


@decorator
def beta(x):
    return x


class Gamma:
    def method(self):
        return 2
'''


def test_python_symbol_boundaries_and_lines():
    ch = chunk_text("a.py", PY)
    lines = PY.split("\n")
    for c in ch:  # nomor baris harus cocok dengan isi aslinya
        assert c.text == "\n".join(lines[c.start_line - 1:c.end_line])
    syms = [c.symbol for c in ch]
    assert syms[0] == "" or syms[0] == "alpha" or "alpha" in syms
    big = chunk_text("a.py", "\n".join(f"def f{i}():\n    return {i}\n" + "\n".join("    # filler"for _ in range(30)) for i in range(5)))
    assert {f"f{i}" for i in range(5)} <= {c.symbol for c in big}


def test_decorator_stays_with_function():
    src = "x = 1\n\n\n@route('/a')\ndef handler():\n" + "\n".join(f"    y{i} = {i}" for i in range(90)) + "\n"
    ch = chunk_text("h.py", src)
    handler = [c for c in ch if c.symbol == "handler"][0]
    assert "@route" in handler.text


def test_markdown_split_by_heading():
    md = "# Judul\n" + "\n".join("teks" for _ in range(20)) + "\n## Diskon\n" + "\n".join("aturan" for _ in range(20))
    assert {"Judul", "Diskon"} <= {c.symbol for c in chunk_text("README.md", md)}


def test_large_unstructured_file_uses_overlapping_windows():
    text = "\n".join(f"k{i}: v{i}" for i in range(300))
    ch = chunk_text("data.yaml", text)
    assert len(ch) > 3
    assert ch[0].start_line == 1 and ch[-1].end_line == 300
    assert ch[1].start_line <= ch[0].end_line  # overlap


def test_classify_and_lang():
    assert detect_lang("Dockerfile") == "dockerfile"
    assert classify("tests/test_a.py", "python") == "test"
    assert classify("src/a.spec.ts", "typescript") == "test"
    assert classify("db/migrations/001.sql", "sql") == "migration"
    assert classify("docker-compose.yml", "yaml") == "deploy"
    assert classify("openapi.yaml", "yaml") == "api_spec"
    assert classify("docs/a.md", "markdown") == "doc"
    assert classify("package.json", "json") == "config"
    assert classify("src/app.py", "python") == "code"
