from . import Skill

SKILL = Skill(
    name="ba", title="Business Analyst",
    description="Alur bisnis, aturan bisnis, dan kesesuaian requirement dengan implementasi.",
    keywords={"requirement": 3, "kebutuhan bisnis": 3, "aturan bisnis": 4, "business rule": 4, "alur bisnis": 4,
              "business flow": 4, "user story": 3, "acceptance": 3, "proses bisnis": 3, "fitur": 1, "bisnis": 2,
              "stakeholder": 2, "sesuai requirement": 4, "diskon": 1, "validasi": 1},
    preferred_kinds=["doc", "code", "schema"],
    prompt=(
        "Peran: Business Analyst. Jelaskan alur bisnis dan aturan bisnis dalam bahasa non-teknis, tetapi tetap dengan sumber.\n"
        "Untuk pertanyaan kesesuaian requirement: cari requirement di dokumen, lalu cari implementasinya di kode, dan buat tabel "
        "[Requirement | Bukti di dokumen | Bukti di kode | Status: sesuai / sebagian / tidak ditemukan / bertentangan].\n"
        "Aturan bisnis (angka, ambang batas, kondisi) harus dikutip persis dari kode dengan sitasi."
    ),
)
