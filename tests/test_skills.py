import pytest

from copilot.agent import build_system
from copilot.skills import detect_skill, load_skills


def test_all_role_skills_registered_as_separate_modules():
    assert {"ba", "qa", "sa", "developer", "pm", "devops", "general"} <= set(load_skills())


@pytest.mark.parametrize("q,want", [
    ("Apa aturan bisnis diskon dan apakah sesuai requirement?", "ba"),
    ("Buatkan test case dan edge case untuk pembatalan pesanan", "qa"),
    ("Gambarkan arsitektur dan diagram mermaid ERD database", "sa"),
    ("Di mana fungsi apply_discount dipanggil? ada bug error", "developer"),
    ("Bagaimana progres dan risiko pekerjaan minggu ini?", "pm"),
    ("Jelaskan konfigurasi docker deployment dan environment variable", "devops"),
    ("halo", "general"),
])
def test_role_detection(q, want):
    assert detect_skill(q) == want


def test_system_prompt_has_core_rules_and_role():
    p = build_system("sa")
    assert "Telusuri dulu" in p and "untrusted_data" in p and "mermaid" in p.lower() and "Tidak ditemukan" in p
