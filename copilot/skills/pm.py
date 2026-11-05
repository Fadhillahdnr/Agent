from . import Skill

SKILL = Skill(
    name="pm", title="Project Manager",
    description="Progres, risiko, dan ringkasan pekerjaan.",
    keywords={"progres": 4, "progress": 4, "status": 2, "risiko": 4, "risk": 4, "ringkasan": 3, "summary": 2,
              "sprint": 3, "timeline": 3, "deadline": 3, "blocker": 3, "selesai": 2, "belum selesai": 3,
              "pekerjaan": 3, "task": 3, "todo": 2, "minggu ini": 3, "laporan": 3, "report": 2},
    preferred_kinds=["doc"],
    prompt=(
        "Peran: Project Manager. Mulai dari list_tasks dan git_log. Ringkas progres per repo: selesai / sedang dikerjakan / "
        "belum dikerjakan / tidak diketahui, masing-masing dengan bukti.\n"
        "Jangan menyatakan task selesai tanpa bukti di kode atau commit. Persentase progres hanya boleh dihitung dari task yang "
        "terlacak, dan sebutkan basis perhitungannya. Risiko (TODO/FIXME menumpuk, branch lama belum ter-merge, area tanpa test, "
        "dokumen vs kode berbeda) ditandai sebagai INFERENSI dengan bukti pemicunya."
    ),
)
