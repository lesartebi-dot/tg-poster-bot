import os, asyncio, logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
MY_ID = os.getenv("MY_ID", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

logging.basicConfig(level=logging.INFO)

def generate_post(topic):
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": [
            {"role": "system", "content": "Ты автор Telegram-канала. Пиши живые посты на русском с эмодзи. 150-300 слов."},
            {"role": "user", "content": f"Напиши пост на тему: {topic}"}
        ], "max_tokens": 600},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != MY_ID:
        return
    topic = " ".join(context.args)
    if not topic:
        await update.message.reply_text("Напиши тему! Например: /post технологии будущего")
        return
    await update.message.reply_text("⏳ Генерирую пост...")
    content = generate_post(topic)
    await context.bot.send_message(chat_id=CHANNEL_ID, text=content)
    await update.message.reply_text("✅ Пост опубликован в канал!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь /post <тема> чтобы опубликовать пост в канал.")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("post", post_command))
print("🤖 Бот запущен!")
app.run_polling()
