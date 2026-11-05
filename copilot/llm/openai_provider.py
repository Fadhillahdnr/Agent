import json

import httpx

from ..config import get_settings
from . import LLMProvider, LLMResult


class OpenAICompatProvider(LLMProvider):
    """Endpoint /chat/completions (OpenAI, Ollama, vLLM, LM Studio, dsb.)."""
    name = "openai"

    def __init__(self):
        s = get_settings()
        self.base, self.key, self.model = s.openai_base_url.rstrip("/"), s.openai_api_key, s.openai_model

    def _convert(self, system, messages):
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                msg = {"role": "assistant", "content": m.get("text") or None}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"id": t["id"], "type": "function",
                                          "function": {"name": t["name"], "arguments": json.dumps(t["input"])}}
                                         for t in m["tool_calls"]]
                out.append(msg)
            else:
                out.extend({"role": "tool", "tool_call_id": r["id"], "content": r["content"]} for r in m["results"])
        return out

    def chat(self, system, messages, tools):
        body = {"model": self.model, "messages": self._convert(system, messages)}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                               "parameters": t["schema"]}} for t in tools]
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        r = httpx.post(f"{self.base}/chat/completions", json=body, headers=headers, timeout=120)
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        res = LLMResult(text=msg.get("content") or "")
        for tc in msg.get("tool_calls") or []:
            res.tool_calls.append({"id": tc["id"], "name": tc["function"]["name"],
                                   "input": json.loads(tc["function"]["arguments"] or "{}")})
        return res
