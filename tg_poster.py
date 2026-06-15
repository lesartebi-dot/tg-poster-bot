import os, asyncio, logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
MY_ID = os.getenv("MY_ID", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

logging.basicConfig(level=logging.INFO)

STYLE_PROMPT = """Ты автор Telegram-канала про ИИ и автоматизацию бизнеса. Пиши посты ТОЧНО в таком стиле:

СТРУКТУРА:
1. Первая строка — цепляющий заголовок с эмодзи 🔥, жирный вопрос или провокация
2. Короткий абзац — боль/проблема читателя, разговорным языком
3. Список проблем через ▸ — конкретные ситуации которые узнаёт читатель
4. Решение — что делает ИИ-агент, список через ▸ с конкретикой
5. Финал — короткий вывод или призыв

СТИЛЬ:
- Разговорный, живой, без официоза
- Обращение на "ты"
- Конкретные цифры и ситуации (3 часа, 24/7, 30 секунд)
- Никаких общих фраз — только конкретика
- Эмодзи только в заголовке и разделах, не везде
- Длина: 250-350 слов

ЗАПРЕЩЕНО:
- Слова "уникальный", "инновационный", "революционный"
- Общие фразы без конкретики
- Корпоративный язык"""

def generate_post(topic):
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": [
            {"role": "system", "content": STYLE_PROMPT},
            {"role": "user", "content": f"Напиши пост на тему: {topic}"}
        ], "max_tokens": 800},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != MY_ID:
        return
    topic = " ".join(context.args)
    if not topic:
        await update.message.reply_text("Напиши тему! Например:\n/post продажи на маркетплейсах")
        return
    await update.message.reply_text("⏳ Генерирую пост...")
    content = generate_post(topic)
    await context.bot.send_message(chat_id=CHANNEL_ID, text=content)
    await update.message.reply_text("✅ Пост опубликован в канал!")

async def preview_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != MY_ID:
        return
    topic = " ".join(context.args)
    if not topic:
        await update.message.reply_text("Напиши тему! Например:\n/preview автоматизация бизнеса")
        return
    await update.message.reply_text("⏳ Генерирую...")
    content = generate_post(topic)
    await update.message.reply_text(f"📝 Предпросмотр:\n\n{content}")
    await update.message.reply_text("Опубликовать? Нажми /approve или напиши /preview снова для новой темы")
    context.user_data["pending"] = content

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != MY_ID:
        return
    content = context.user_data.get("pending")
    if not content:
        await update.message.reply_text("Нет поста для публикации. Сначала /preview <тема>")
        return
    await context.bot.send_message(chat_id=CHANNEL_ID, text=content)
    context.user_data["pending"] = None
    await update.message.reply_text("✅ Пост опубликован!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот для постинга готов!\n\n"
        "/post <тема> — сгенерировать и сразу опубликовать\n"
        "/preview <тема> — сначала посмотреть пост\n"
        "/approve — опубликовать после просмотра"
    )

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("post", post_command))
app.add_handler(CommandHandler("preview", preview_command))
app.add_handler(CommandHandler("approve", approve_command))
print("🤖 Бот запущен!")
app.run_polling()
