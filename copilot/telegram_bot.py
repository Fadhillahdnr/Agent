"""Bot Telegram (long polling). Tanpa token, service ini idle tetapi tetap sehat. Whitelist diputuskan oleh API."""
import asyncio
import logging
import pathlib
import time

import httpx

from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("telegram")
HEARTBEAT = pathlib.Path("/tmp/telegram.heartbeat")
SKILLS = "auto, ba, qa, sa, developer, pm, devops, general"


def beat():
    HEARTBEAT.write_text(str(time.time()))


def chunks(text: str, n: int = 3800):
    while text:
        yield text[:n]
        text = text[n:]


def format_reply(r: dict) -> str:
    out = r["answer"]
    if r.get("sources"):
        out += "\n\nSumber:\n" + "\n".join(
            f"- {s['path']}:L{s['start_line']}-L{s['end_line']}" if s["type"] == "file" else f"- commit {s['hash']} ({s['repo']})"
            for s in r["sources"][:15])
    if r.get("warnings"):
        out += "\n\nPeringatan: " + "; ".join(r["warnings"][:3])
    return out + f"\n\n[peran: {r['skill']}]"


def main():
    s = get_settings()
    if not s.telegram_bot_token:
        log.warning("TELEGRAM_BOT_TOKEN kosong: bot Telegram dinonaktifkan")
        while True:
            beat()
            time.sleep(15)
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

    headers = {"X-Internal-Token": s.internal_token}

    async def call(path, payload):
        async with httpx.AsyncClient(timeout=180) as cl:
            return await cl.post(f"{s.api_url}{path}", json=payload, headers=headers)

    async def on_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"Project Copilot. ID Telegram Anda: {update.effective_user.id}\n"
            f"Kirim pertanyaan tentang project. Pilih peran dengan /role <{SKILLS}>.")

    async def on_role(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        skill = ctx.args[0].lower() if ctx.args else "auto"
        r = await call("/api/telegram/pref", {"telegram_id": update.effective_user.id, "skill": skill})
        await update.message.reply_text("Peran diatur ke: " + skill if r.status_code == 200 else f"Gagal ({r.status_code}). Pilihan: {SKILLS}")

    async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.chat.send_action("typing")
        r = await call("/api/telegram/ask", {"telegram_id": update.effective_user.id, "message": update.message.text})
        if r.status_code == 403:
            await update.message.reply_text(f"Akses ditolak. Minta admin menambahkan ID Telegram Anda ({update.effective_user.id}).")
        elif r.status_code == 429:
            await update.message.reply_text("Terlalu banyak pertanyaan, coba lagi sebentar lagi.")
        elif r.status_code != 200:
            await update.message.reply_text(f"Gagal memproses ({r.status_code}).")
        else:
            for part in chunks(format_reply(r.json())):
                await update.message.reply_text(part)

    async def tick(ctx):
        beat()

    app = Application.builder().token(s.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("role", on_role))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.job_queue.run_repeating(tick, interval=15, first=0)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
