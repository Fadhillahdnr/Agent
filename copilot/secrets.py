"""Deteksi dan penyamaran secret. Penyamaran menjaga jumlah baris agar nomor baris tetap valid."""
import fnmatch
import re

_PLACEHOLDER = re.compile(r"(?i)^(your[_-]|change[_-]?me|xxx+|<.*>|\$\{.*\}|\{\{.*\}\}|example|dummy|placeholder|none|null|true|false)")

_SIMPLE = [
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("telegram_token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.=]{20,}")),
]
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----.*?(?:-----END [A-Z ]*PRIVATE KEY(?: BLOCK)?-----|\Z)", re.S
)
_URL_CRED = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+:)([^\s@/]{3,})(@)")
_ASSIGN = re.compile(
    r"""(?ix)
    \b([A-Za-z0-9_.\-]*(?:password|passwd|pwd|secret|token|api[_\-]?key|apikey|access[_\-]?key|private[_\-]?key|credential)[A-Za-z0-9_.\-]*)
    (["']?\s*[:=]\s*)
    (?:"([^"\n]{6,})"|'([^'\n]{6,})'|([^\s"'#,;\)\(\{\}<>$]{8,}))
    """
)

# Nama file yang tidak boleh diindeks, dibaca, atau ditampilkan sama sekali.
SECRET_FILE_PATTERNS = [
    ".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*.kdbx", ".npmrc", ".pypirc", ".netrc",
    ".git-credentials", "credentials", "credentials.*", "secrets.*", "*.tfstate", "*.tfstate.*",
    "service-account*.json", "*serviceaccount*.json", "*.ovpn", ".htpasswd", "token.json",
]
_SAFE_ENV_TEMPLATES = (".env.example", ".env.sample", ".env.template", ".env.dist", "example.env", "sample.env")


def is_secret_path(path: str) -> bool:
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name in _SAFE_ENV_TEMPLATES:
        return False
    return any(fnmatch.fnmatch(name, p) for p in SECRET_FILE_PATTERNS)


def _blank_like(m: "re.Match", label: str) -> str:
    n = m.group(0).count("\n")
    return f"[REDACTED:{label}]" + "\n" * n


def redact(text: str) -> str:
    if not text:
        return text
    text = _PRIVATE_KEY.sub(lambda m: _blank_like(m, "private_key"), text)
    for label, rx in _SIMPLE:
        text = rx.sub(f"[REDACTED:{label}]", text)
    text = _URL_CRED.sub(r"\1[REDACTED:password]\3", text)

    def assign(m: "re.Match") -> str:
        quoted = m.group(3) or m.group(4)
        val = quoted or m.group(5)
        if _PLACEHOLDER.match(val):
            return m.group(0)
        if not quoted and not (re.search(r"\d", val) or len(val) >= 12):
            return m.group(0)  # mis. token = request.headers (kemungkinan kode, bukan secret)
        if not quoted and re.fullmatch(r"[A-Za-z_][\w.]*", val) and not re.search(r"\d", val):
            return m.group(0)
        q = '"' if m.group(3) else ("'" if m.group(4) else "")
        return f"{m.group(1)}{m.group(2)}{q}[REDACTED:secret]{q}"

    return _ASSIGN.sub(assign, text)


def contains_secret(text: str) -> bool:
    return redact(text) != text
