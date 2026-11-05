from . import Skill

SKILL = Skill(
    name="qa", title="Quality Assurance",
    description="Skenario uji, test case, edge case, cakupan test, dan area terdampak perubahan.",
    keywords={"test case": 4, "skenario uji": 4, "skenario test": 4, "edge case": 4, "cakupan": 3, "coverage": 3,
              "regresi": 3, "regression": 3, "uji": 2, "testing": 2, "qa": 3, "terdampak": 3, "impact": 2,
              "belum ditest": 4, "bug": 1, "negative case": 3, "test": 1},
    preferred_kinds=["test", "code"],
    prompt=(
        "Peran: QA. Susun skenario uji dengan format: ID | Skenario | Langkah | Hasil yang diharapkan | Jenis (positif/negatif/edge).\n"
        "Turunkan edge case dari kondisi nyata di kode (validasi, cabang if/else, batas angka, error handling) dan kutip barisnya.\n"
        "Untuk cakupan test: cari file kind=test, petakan ke fungsi yang diuji, dan sebut fungsi yang tidak ditemukan test-nya "
        "sebagai 'tidak ditemukan test' (bukan 'tidak ada test'), karena pencarian bisa tidak lengkap.\n"
        "Untuk area terdampak: telusuri pemanggil/pengguna simbol yang berubah memakai search_project dan grep_project."
    ),
)
