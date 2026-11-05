"""Registry skill. Tambah skill baru = tambah satu file .py di folder ini yang mengekspor SKILL."""
import importlib
import pkgutil
import re
from dataclasses import dataclass, field


@dataclass
class Skill:
    name: str
    title: str
    description: str
    prompt: str
    keywords: dict = field(default_factory=dict)  # kata kunci -> bobot
    preferred_kinds: list = field(default_factory=list)  # jenis file yang diprioritaskan saat mencari


_REGISTRY: dict[str, Skill] = {}


def load_skills() -> dict:
    if _REGISTRY:
        return _REGISTRY
    for m in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f"{__name__}.{m.name}")
        skill = getattr(mod, "SKILL", None)
        if isinstance(skill, Skill):
            _REGISTRY[skill.name] = skill
    return _REGISTRY


def detect_skill(question: str) -> str:
    q = question.lower()
    best, score = "general", 0.0
    for name, sk in load_skills().items():
        s = sum(w for kw, w in sk.keywords.items() if re.search(r"(?<![a-z0-9])" + re.escape(kw), q))
        if s > score:
            best, score = name, s
    return best
