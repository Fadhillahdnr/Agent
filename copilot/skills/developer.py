from . import Skill

SKILL = Skill(
    name="developer", title="Developer",
    description="Lokasi kode, alur eksekusi, analisis bug, dan saran perbaikan.",
    keywords={"dimana": 2, "di mana": 2, "where is": 2, "fungsi": 3, "function": 3, "class": 2, "method": 2,
              "bug": 3, "error": 3, "exception": 3, "crash": 3, "kenapa": 2, "mengapa": 2, "why": 1, "alur eksekusi": 4,
              "call": 1, "dipanggil": 3, "refactor": 3, "perbaiki": 3, "fix": 2, "stack trace": 4, "implementasi": 2,
              "kode": 1, "code": 1},
    preferred_kinds=["code", "test"],
    prompt=(
        "Peran: Developer. Tunjukkan lokasi kode (path:baris), jelaskan alur eksekusi langkah demi langkah, dan analisis bug.\n"
        "Analisis bug: tulis hipotesis penyebab sebagai INFERENSI, lalu bukti pendukung sebagai FAKTA dengan sitasi. "
        "Saran perbaikan ditulis sebagai potongan kode usulan; kamu tidak mengubah file apa pun dan tidak menjalankan kode. "
        "Baca file dengan read_project_file untuk memastikan konteks sebelum menyimpulkan."
    ),
)
