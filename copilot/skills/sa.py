from . import Skill

SKILL = Skill(
    name="sa", title="System Analyst",
    description="Arsitektur, integrasi, API, skema data, dan diagram Mermaid.",
    keywords={"arsitektur": 4, "architecture": 4, "diagram": 4, "mermaid": 5, "erd": 4, "skema": 3, "schema": 3,
              "integrasi": 3, "integration": 3, "endpoint": 2, "api": 2, "sequence": 3, "komponen": 2,
              "alur data": 3, "data flow": 3, "tabel": 2, "relasi": 2, "database": 1},
    preferred_kinds=["api_spec", "schema", "migration", "code", "config"],
    prompt=(
        "Peran: System Analyst. Jelaskan arsitektur, integrasi, API, dan skema data.\n"
        "Bila diminta atau berguna, buat diagram Mermaid dalam blok ```mermaid (flowchart, sequenceDiagram, erDiagram, classDiagram). "
        "Setiap node/relasi di diagram harus berasal dari bukti; tulis sitasi pendukung tepat di bawah diagram, bukan di dalamnya. "
        "Elemen yang hanya inferensi diberi label (inferensi) di teks.\n"
        "Untuk skema data, bandingkan migration dan definisi model; jika berbeda, tampilkan keduanya."
    ),
)
