from . import Skill

SKILL = Skill(
    name="devops", title="DevOps",
    description="Konfigurasi deployment, environment, dan dependensi.",
    keywords={"deploy": 4, "deployment": 4, "docker": 4, "compose": 3, "kubernetes": 4, "k8s": 4, "ci/cd": 4, "cicd": 4,
              "pipeline": 3, "environment": 3, "env var": 4, "variabel lingkungan": 4, "dependensi": 3, "dependency": 3,
              "port": 2, "healthcheck": 3, "nginx": 3, "build": 1, "workflow": 2, "infrastruktur": 3, "devops": 5},
    preferred_kinds=["deploy", "config"],
    prompt=(
        "Peran: DevOps. Jelaskan konfigurasi deployment, variabel environment (nama saja, jangan pernah nilai secret), port, "
        "volume, healthcheck, dan dependensi dari file manifest.\n"
        "Daftar environment variable: kumpulkan dari kode (os.environ/process.env), compose, dan .env.example, lalu tandai yang "
        "dipakai di kode tetapi tidak didokumentasikan."
    ),
)
