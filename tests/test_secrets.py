from copilot.secrets import contains_secret, is_secret_path, redact


def test_redacts_known_token_formats():
    samples = {
        "aws": "key=AKIAIOSFODNN7EXAMPLE",
        "gh": "t = ghp_" + "a" * 36,
        "anthropic": "sk-ant-api03-" + "x" * 40,
        "telegram": "123456789:" + "A" * 35,
        "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.abcdefghijk",
        "url": "postgres://user:hunter2pass@db:5432/x",
    }
    for name, s in samples.items():
        out = redact(s)
        assert "[REDACTED" in out, name
    assert "hunter2pass" not in redact(samples["url"])


def test_redacts_assignments_but_not_plain_code():
    assert "S3cretPassw0rd" not in redact('DB_PASSWORD = "S3cretPassw0rd-x"')
    assert "abcd1234efgh5678" not in redact("API_TOKEN=abcd1234efgh5678ijkl")
    assert redact("token = request.headers") == "token = request.headers"
    assert redact('password: "${DB_PASSWORD}"') == 'password: "${DB_PASSWORD}"'
    assert redact("password=changeme") == "password=changeme"


def test_private_key_redaction_keeps_line_count():
    text = "a\n-----BEGIN RSA PRIVATE KEY-----\nAAA\nBBB\n-----END RSA PRIVATE KEY-----\nz"
    out = redact(text)
    assert "AAA" not in out and "[REDACTED:private_key]" in out
    assert out.count("\n") == text.count("\n")
    assert out.split("\n")[-1] == "z"


def test_secret_paths():
    for p in [".env", "app/.env.production", "keys/server.pem", "id_rsa", "a/b/credentials.json", "terraform.tfstate"]:
        assert is_secret_path(p), p
    for p in [".env.example", "src/app.py", "README.md"]:
        assert not is_secret_path(p), p


def test_contains_secret():
    assert contains_secret("password = 'Sup3rSecretValue'")
    assert not contains_secret("hello world")
