import os
import tempfile
import whisper
import ffmpeg

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes,
)

# Загружаем модель Whisper
model = whisper.load_model("small")

TOKEN = os.getenv("TELEGRAM_TOKEN", "8034075734:AAE6CQG-iMD86PbzWr2Qe1d3Vvr3dYYKTts")

async def transcribe_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    tg_file = await voice.get_file()
    with tempfile.TemporaryDirectory() as tmp:
        ogg = os.path.join(tmp, "in.ogg")
        wav = os.path.join(tmp, "in.wav")
        await tg_file.download_to_drive(ogg)

        # Конвертация OGG → WAV
        (
            ffmpeg
            .input(ogg)
            .output(wav, ar=16000, ac=1)
            .overwrite_output()
            .run(quiet=True)
        )

        # Транскрипция
        res = model.transcribe(wav, language="ru")
        text = res["text"].strip()

        reply = text or "Не удалось распознать речь."
        await update.message.reply_text(reply)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Фильтруем voice- и audio-сообщения
    app.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, transcribe_voice)
    )

    print("Бот запущен…")
    app.run_polling()

if __name__ == "__main__":
    main()
