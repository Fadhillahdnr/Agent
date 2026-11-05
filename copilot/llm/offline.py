"""Provider tanpa model: hanya retrieval. Dipakai untuk tes otomatis dan sebagai mode darurat tanpa API key.
Jawabannya berupa kutipan bukti yang ditemukan, bukan hasil penalaran."""
import json

from . import LLMProvider, LLMResult


class OfflineProvider(LLMProvider):
    name = "offline"

    def chat(self, system, messages, tools):
        question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        names = {t["name"] for t in tools}
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        if not tool_msgs:
            q = question.split("\n[Pertanyaan]")[-1].strip()
            calls = [{"id": "o1", "name": "search_project", "input": {"query": q, "k": 6}}]
            low = q.lower()
            if "list_tasks" in names and any(w in low for w in ("task", "progres", "progress", "todo", "status", "pekerjaan")):
                calls.append({"id": "o2", "name": "list_tasks", "input": {}})
            if "git_log" in names and any(w in low for w in ("commit", "riwayat", "history", "perubahan")):
                calls.append({"id": "o3", "name": "git_log", "input": {"limit": 8}})
            return LLMResult(tool_calls=calls)
        lines = ["Fakta (hasil penelusuran, mode offline tanpa model AI):"]
        for r in tool_msgs[-1]["results"]:
            body = r["content"]
            try:
                data = json.loads(body.split("\n", 1)[1].rsplit("\n", 1)[0]) if body.startswith("<untrusted_data") else None
            except Exception:
                data = None
            if isinstance(data, list):
                for item in data[:6]:
                    if "path" in item and "start_line" in item:
                        snippet = " ".join(item["text"].split())[:160]
                        lines.append(f"- [{item['path']}:L{item['start_line']}-L{item['end_line']}] {snippet}")
                    elif "evidence" in item:
                        lines.append(f"- {item['status']}: {item['title']} ({item['evidence']})")
                    elif "hash" in item:
                        lines.append(f"- [commit:{item['hash']}] {item['subject']}")
        if len(lines) == 1:
            lines = ["Tidak ditemukan bukti yang relevan di project untuk pertanyaan ini."]
        return LLMResult(text="\n".join(lines))
