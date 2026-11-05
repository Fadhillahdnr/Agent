import anthropic

from ..config import get_settings
from . import LLMProvider, LLMResult


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        s = get_settings()
        if not s.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY belum diisi di .env")
        self.client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=120)
        self.model = s.anthropic_model

    def _convert(self, messages):
        out = []
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                blocks = []
                if m.get("text"):
                    blocks.append({"type": "text", "text": m["text"]})
                for tc in m.get("tool_calls", []):
                    blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]})
                out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "(kosong)"}]})
            else:
                out.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]} for r in m["results"]]})
        return out

    def chat(self, system, messages, tools):
        kw = {}
        if tools:
            kw["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["schema"]} for t in tools]
        resp = self.client.messages.create(
            model=self.model, max_tokens=4096, system=system, messages=self._convert(messages), **kw)
        res = LLMResult()
        for b in resp.content:
            if b.type == "text":
                res.text += b.text
            elif b.type == "tool_use":
                res.tool_calls.append({"id": b.id, "name": b.name, "input": dict(b.input)})
        return res
