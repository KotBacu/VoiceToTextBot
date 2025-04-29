import os
import re
import tempfile
import asyncio
from datetime import datetime, timedelta

import whisper
import ffmpeg
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# Загружаем модель Whisper один раз
MODEL_SIZE = os.getenv("WHISPER_MODEL", "tiny")
model = whisper.load_model(MODEL_SIZE)

# Токен бота
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не задан")

# Парсер временных спецификаций
def parse_time_spec(t: str):
    m = re.match(r"^(\d+)([mh])$", t)
    if m:
        v, unit = int(m.group(1)), m.group(2)
        return timedelta(minutes=v) if unit == "m" else timedelta(hours=v)
    # абсолютное время HH:MM
    now = datetime.now()
    try:
        hh, mm = map(int, t.split(':'))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target
    except ValueError:
        return None

# Хендлер транскрипции команды
async def cmd_transcribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    reply = msg.reply_to_message
    if not reply or not (reply.voice or reply.audio):
        return await msg.reply_text(
            "⚠️ Чтобы транскрибировать, ответьте на голосовое или аудио-сообщение командой /transcribe."
        )
    file_obj = await (reply.voice or reply.audio).get_file()
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "in.ogg")
        wav_path = os.path.join(tmp, "in.wav")
        await file_obj.download_to_drive(in_path)
        ffmpeg.input(in_path).output(wav_path, ar=16000, ac=1).overwrite_output().run(quiet=True)
        res = model.transcribe(wav_path, language="ru")
        text = res.get("text", "").strip() or "❌ Не удалось распознать речь."
    await msg.reply_text(f"📝 Транскрипция:\n{text}")

# Напоминания через JobQueue
async def alarm(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text=f"⏰ Напоминание:\n{job.data['text']}"
    )

async def remind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text(
            "Используйте: /remind <время> <текст>\n"
            "Время: 10m, 2h или HH:MM"
        )
    spec = context.args[0]
    text = " ".join(context.args[1:])
    when = parse_time_spec(spec)
    if when is None:
        return await update.message.reply_text(
            "Неверный формат времени. Используйте 10m, 2h или HH:MM"
        )
    if isinstance(when, timedelta):
        delay = when.total_seconds()
    else:
        delay = (when - datetime.now()).total_seconds()
    job = context.job_queue.run_once(
        alarm,
        when=delay,
        chat_id=update.effective_chat.id,
        name=f"reminder_{update.effective_user.id}_{datetime.now().timestamp()}",
        data={"text": text}
    )
    run_at = (datetime.now() + timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M")
    await update.message.reply_text(f"✅ Напоминание установлено на {run_at}\nID: {job.job_id}")

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = context.job_queue.get_jobs()
    if not jobs:
        return await update.message.reply_text("Нет запланированных напоминаний.")
    now = datetime.now()
    lines = []
    for job in jobs:
        delta = job.next_run_time - now
        mins = int(delta.total_seconds() // 60)
        lines.append(f"{job.job_id}: через {mins} мин → {job.data['text']}")
    await update.message.reply_text("\n".join(lines))

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Используйте /cancel <ID напоминания>")
    job_id = context.args[0]
    job = context.job_queue.get_job(job_id)
    if job:
        job.schedule_removal()
        return await update.message.reply_text(f"❌ Напоминание {job_id} отменено.")
    else:
        return await update.message.reply_text(f"Напоминание с ID {job_id} не найдено.")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для транскрипции и напоминаний.\n\n"
        "- /transcribe (reply на voice-note)\n"
        "- /remind <time> <text>\n"
        "- /listreminders\n"
        "- /cancel <ID>"
    )


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Устанавливаем команды интерфейса
    asyncio.get_event_loop().run_until_complete(
        app.bot.set_my_commands([
            BotCommand("start", "Показать справку"),
            BotCommand("transcribe", "Транскрибировать голосовое сообщение"),
            BotCommand("remind", "Установить напоминание"),
            BotCommand("listreminders", "Список напоминаний"),
            BotCommand("cancel", "Отменить напоминание по ID"),
        ])
    )

    # Регистрируем хендлеры
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("transcribe", cmd_transcribe))
    app.add_handler(CommandHandler("remind", remind_cmd))
    app.add_handler(CommandHandler("listreminders", list_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    print("Бот с транскрипцией и напоминаниями запущен…")
    app.run_polling()


if __name__ == "__main__":
    main()
