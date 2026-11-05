"""Satu pertanyaan per peran lewat API (provider offline = retrieval saja). Setiap jawaban harus punya sumber valid."""
import re

import pytest

from conftest import login

QUESTIONS = {
    "ba": "Apa aturan bisnis diskon pesanan?",
    "qa": "Buatkan skenario test untuk fungsi apply_discount",
    "sa": "Bagaimana skema tabel orders di database?",
    "developer": "Di mana fungsi cancel_order didefinisikan?",
    "pm": "Bagaimana progres task dan status pekerjaan?",
    "devops": "Apa konfigurasi Dockerfile dan environment variable PAYMENT_GATEWAY_URL?",
}


@pytest.mark.parametrize("skill,q", QUESTIONS.items())
def test_each_role_answers_with_valid_sources(client, skill, q):
    login(client)
    r = client.post("/api/chat", json={"message": q, "skill": skill})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["skill"] == skill and j["sources"], j
    assert not [w for w in j["warnings"] if "tidak valid" in w], j["warnings"]
    assert re.search(r"\[[^\]]+:L\d+|\[commit:", j["answer"])
    assert "S3cretPassw0rd" not in j["answer"] and "SuperSecretEnvValue123" not in j["answer"]


def test_auto_role_detection_via_api(client):
    login(client)
    assert client.post("/api/chat", json={"message": "Jelaskan deployment docker dan environment", "skill": "auto"}).json()["skill"] == "devops"


def test_not_found_is_reported_not_invented(client):
    login(client)
    j = client.post("/api/chat", json={"message": "zzqqxx kriptografi kuantum"}).json()
    assert "Tidak ditemukan" in j["answer"] and not j["sources"]


def test_invalid_skill_rejected(client):
    login(client)
    assert client.post("/api/chat", json={"message": "x", "skill": "hacker"}).status_code == 400


def test_health_and_localhost_binding_declared(client):
    assert client.get("/health").json() == {"status": "ok"}
    from pathlib import Path
    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text()
    assert '"127.0.0.1:${WEB_PORT:-8080}:8000"' in compose and ":/project:ro" in compose
