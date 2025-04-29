import os
import tempfile
import whisper
import ffmpeg

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    filters,
    ContextTypes,
)

# 1) Загрузка модели один раз при старте
model = whisper.load_model("tiny")

TOKEN = os.getenv("TELEGRAM_TOKEN")  # у тебя уже выставлен

async def cmd_transcribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    # 2) Проверяем, что команда пришла как ответ на голос/аудио
    reply = msg.reply_to_message
    if not reply or not (reply.voice or reply.audio):
        return await msg.reply_text(
            "⚠️ Чтобы транскрибировать, ответь на голосовое или аудио-сообщение командой /transcribe."
        )

    # 3) Берём файл (voice или audio)
    file_obj = await (reply.voice or reply.audio).get_file()

    # 4) Скачиваем, конвертируем и транскрибируем
    with tempfile.TemporaryDirectory() as tmp:
        in_path  = os.path.join(tmp, "in.ogg")
        wav_path = os.path.join(tmp, "in.wav")
        await file_obj.download_to_drive(in_path)

        ffmpeg.input(in_path).output(
            wav_path, ar=16000, ac=1
        ).overwrite_output().run(quiet=True)

        res  = model.transcribe(wav_path, language="ru")
        text = res["text"].strip() or "❌ Не удалось распознать речь."

    # 5) Отправляем результат
    await msg.reply_text(f"📝 Транскрипция:\n\n{text}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # 6) Регистрируем только CommandHandler
    app.add_handler(
        CommandHandler("transcribe", cmd_transcribe, filters=filters.ALL)
    )

    print("Бот запущен…")
    app.run_polling()

if __name__ == "__main__":
    main()
