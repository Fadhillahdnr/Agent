"""Code-aware chunking: batas simbol per bahasa, heading untuk markdown, jendela baris untuk sisanya."""
import os
import re
from dataclasses import dataclass

MAX_LINES = 80
MIN_LINES = 12
MAX_CHARS = 3500
OVERLAP = 8

LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".vue": "vue", ".svelte": "svelte", ".java": "java",
    ".kt": "kotlin", ".go": "go", ".rs": "rust", ".php": "php", ".rb": "ruby", ".cs": "csharp",
    ".swift": "swift", ".dart": "dart", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
    ".ino": "cpp", ".sql": "sql", ".sh": "shell", ".bash": "shell", ".ps1": "powershell",
    ".md": "markdown", ".mdx": "markdown", ".rst": "markdown", ".txt": "text", ".json": "json",
    ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".ini": "ini", ".xml": "xml", ".html": "html",
    ".css": "css", ".scss": "css", ".graphql": "graphql", ".gql": "graphql", ".proto": "proto", ".tf": "terraform",
}

_BOUNDARY = {
    "python": re.compile(r"^(?:async\s+def|def|class)\s+(\w+)"),
    "javascript": re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\*?|class)\s+(\w+)|^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\(|function|\w+\s*=>)"),
    "java": re.compile(r"^\s{0,4}(?:public|private|protected|static|final|abstract|class|interface|enum|record)\b[^;=]*?\b(\w+)\s*(?:\(|\{|extends|implements)"),
    "go": re.compile(r"^(?:func\s+(?:\([^)]*\)\s*)?(\w+)|type\s+(\w+))"),
    "rust": re.compile(r"^(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|trait|impl|mod)\s+(\w+)"),
    "php": re.compile(r"^\s{0,4}(?:(?:public|private|protected|static|abstract|final)\s+)*(?:function|class|interface|trait)\s+(\w+)"),
    "ruby": re.compile(r"^\s{0,2}(?:def|class|module)\s+([\w.]+)"),
    "swift": re.compile(r"^\s{0,4}(?:(?:public|private|internal|open|final)\s+)*(?:func|class|struct|enum|protocol|extension)\s+(\w+)"),
    "dart": re.compile(r"^(?:abstract\s+)?(?:class|mixin|enum|extension)\s+(\w+)"),
    "cpp": re.compile(r"^(?:[\w:<>\*&]+\s+)+(\w+)\s*\([^;]*$|^(?:class|struct|namespace)\s+(\w+)"),
    "sql": re.compile(r"(?i)^\s*(?:create|alter|drop|insert\s+into|with)\s+(?:or\s+replace\s+)?(?:unique\s+)?(?:table|view|index|function|procedure|trigger|type|extension)?\s*(?:if\s+(?:not\s+)?exists\s+)?([\w.\"`]+)?"),
    "shell": re.compile(r"^(?:function\s+)?(\w+)\s*\(\)\s*\{"),
    "graphql": re.compile(r"^(?:type|input|enum|interface|query|mutation|subscription)\s+(\w+)"),
    "proto": re.compile(r"^(?:message|service|enum|rpc)\s+(\w+)"),
}
for _alias, _base in {"typescript": "javascript", "vue": "javascript", "svelte": "javascript",
                      "kotlin": "java", "csharp": "java"}.items():
    _BOUNDARY[_alias] = _BOUNDARY[_base]
_BOUNDARY["kotlin"] = re.compile(r"^\s{0,4}(?:(?:public|private|internal|data|open|abstract|sealed|suspend)\s+)*(?:fun|class|interface|object|enum\s+class)\s+(?:<[^>]+>\s*)?(\w+)")

_DECORATION = re.compile(r"^\s*(@\w|#\[|///|//\s|#\s|/\*\*|\*\s|\*/)")
_HEADING = re.compile(r"^(#{1,4})\s+(.*)")


@dataclass
class Chunk:
    start_line: int
    end_line: int
    symbol: str
    text: str


def detect_lang(path: str) -> str:
    base = os.path.basename(path).lower()
    if base in ("dockerfile",) or base.startswith("dockerfile."):
        return "dockerfile"
    if base in ("makefile",):
        return "makefile"
    return LANG_BY_EXT.get(os.path.splitext(base)[1], "text")


def classify(path: str, lang: str) -> str:
    p = "/" + path.lower()
    base = os.path.basename(p)
    if re.search(r"/(tests?|__tests__|spec|specs|e2e|cypress)/", p) or re.search(r"(^|[._-])(test|spec)s?[._-]|_test\.|\.(test|spec)\.|test_", base):
        return "test"
    if "/migrations/" in p or "/migrate/" in p or "/alembic/versions/" in p or "/db/migrate/" in p:
        return "migration"
    if (base.startswith(("openapi", "swagger")) or "/api-docs" in p or lang in ("proto", "graphql")
            or base.endswith((".openapi.yml", ".openapi.yaml", ".openapi.json"))):
        return "api_spec"
    if (lang in ("dockerfile",) or base.startswith(("docker-compose", "compose.")) or "/.github/workflows/" in p
            or "/k8s/" in p or "/kubernetes/" in p or "/helm/" in p or lang == "terraform"
            or base in ("jenkinsfile", ".gitlab-ci.yml", "nginx.conf", "procfile", "makefile")):
        return "deploy"
    if lang == "sql" and re.search(r"schema|ddl|init", base):
        return "schema"
    if lang == "markdown" or base.startswith(("readme", "changelog", "license")) or "/docs/" in p:
        return "doc"
    if lang in ("json", "yaml", "toml", "ini", "xml") or base.startswith(".") or base.endswith((".config.js", ".config.ts")) \
            or base in ("package.json", "requirements.txt", "pom.xml", "go.mod", "composer.json", "pubspec.yaml"):
        return "config"
    if lang == "sql":
        return "schema"
    return "code"


def _window(lines, base_line, symbol):
    """Pecah segmen besar menjadi jendela dengan overlap."""
    out = []
    i = 0
    n = len(lines)
    while i < n:
        j = min(n, i + MAX_LINES)
        while j > i + 1 and sum(len(x) + 1 for x in lines[i:j]) > MAX_CHARS:
            j -= 1
        out.append(Chunk(base_line + i, base_line + j - 1, symbol, "\n".join(lines[i:j])))
        if j >= n:
            break
        i = max(i + 1, j - OVERLAP)
    return out


def _split_segments(lines, starts):
    """starts: list of (line_index, symbol). Mengembalikan segmen [(start, end_exclusive, symbol)]."""
    segs = []
    if not starts or starts[0][0] > 0:
        segs.append((0, starts[0][0] if starts else len(lines), ""))
    for k, (s, sym) in enumerate(starts):
        e = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        segs.append((s, e, sym))
    return [x for x in segs if x[1] > x[0]]


def _merge_and_emit(lines, segs):
    chunks, cur = [], None
    for s, e, sym in segs:
        size = e - s
        if size > MAX_LINES or sum(len(x) + 1 for x in lines[s:e]) > MAX_CHARS:
            if cur:
                chunks.append(cur)
                cur = None
            chunks.extend(_window(lines[s:e], s + 1, sym))
            continue
        if cur and (cur.end_line - cur.start_line + 1) + size <= MAX_LINES and \
                (cur.end_line - cur.start_line + 1) < MIN_LINES and \
                len(cur.text) + sum(len(x) + 1 for x in lines[s:e]) <= MAX_CHARS:
            cur = Chunk(cur.start_line, e, cur.symbol or sym, "\n".join(lines[cur.start_line - 1:e]))
        else:
            if cur:
                chunks.append(cur)
            cur = Chunk(s + 1, e, sym, "\n".join(lines[s:e]))
    if cur:
        chunks.append(cur)
    return chunks


def _boundaries(lines, lang):
    rx = _BOUNDARY.get(lang)
    if not rx:
        return []
    starts = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if lang == "python" and line[0] in " \t":
            continue
        m = rx.match(line)
        if not m:
            continue
        sym = next((g for g in m.groups() if g), "")
        k = i
        indent = len(line) - len(line.lstrip())
        while (k > 0 and _DECORATION.match(lines[k - 1]) and (not starts or k - 1 > starts[-1][0])
               and len(lines[k - 1]) - len(lines[k - 1].lstrip()) == indent):
            k -= 1
        starts.append((k, sym))
    return starts


def _markdown(lines):
    starts = []
    in_code = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else _HEADING.match(line)
        if m:
            starts.append((i, m.group(2).strip()[:80]))
    return starts


def chunk_text(path: str, text: str):
    """Mengembalikan list[Chunk]; nomor baris 1-based dan inklusif."""
    lang = detect_lang(path)
    lines = text.split("\n")
    if text.endswith("\n"):
        lines = lines[:-1]
    if not lines:
        return []
    if lang == "markdown":
        starts = _markdown(lines)
    elif lang in _BOUNDARY:
        starts = _boundaries(lines, lang)
    else:
        starts = []
    if not starts:
        return _window(lines, 1, "") if len(lines) > MAX_LINES or len(text) > MAX_CHARS else [Chunk(1, len(lines), "", "\n".join(lines))]
    return _merge_and_emit(lines, _split_segments(lines, starts))
