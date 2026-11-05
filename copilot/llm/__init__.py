"""Abstraksi provider LLM. Format pesan netral:
  {"role":"user","content":str} | {"role":"assistant","text":str,"tool_calls":[{id,name,input}]}
  | {"role":"tool","results":[{id,name,content}]}
"""
from dataclasses import dataclass, field

from ..config import get_settings


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list = field(default_factory=list)


class LLMProvider:
    name = "base"

    def chat(self, system: str, messages: list, tools: list) -> LLMResult:  # pragma: no cover
        raise NotImplementedError


def get_provider() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    if s.llm_provider in ("openai", "openai_compatible", "ollama"):
        from .openai_provider import OpenAICompatProvider
        return OpenAICompatProvider()
    if s.llm_provider == "offline":
        from .offline import OfflineProvider
        return OfflineProvider()
    raise RuntimeError(f"LLM_PROVIDER tidak dikenal: {s.llm_provider}")
