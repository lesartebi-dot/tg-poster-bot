import os, asyncio, logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

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

def is_owner(update: Update) -> bool:
    return str(update.effective_user.id) == MY_ID

def main_menu():
    keyboard = [
        [InlineKeyboardButton("✍️ Новый пост", callback_data="new_post")],
        [InlineKeyboardButton("📋 Помощь", callback_data="help")],
    ]
    return InlineKeyboardMarkup(keyboard)

def preview_actions_menu():
    keyboard = [
        [
            InlineKeyboardButton("✅ Опубликовать", callback_data="approve"),
            InlineKeyboardButton("🔄 Сгенерировать снова", callback_data="regenerate"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот для постинга готов!\n\n"
        "Просто напиши тему поста — я сгенерирую текст.\n"
        "Можешь сразу прислать фото с подписью-темой — пост выйдет с картинкой.\n\n"
        "Или используй кнопки ниже 👇",
        reply_markup=main_menu(),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Как пользоваться:\n\n"
        "1. Напиши тему текстом — получишь пост с кнопками\n"
        "2. Пришли фото с подписью (темой) — пост будет с картинкой\n"
        "3. Нажми ✅ Опубликовать когда понравится\n"
        "4. Нажми 🔄 если хочешь другой вариант"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    topic = update.message.text.strip()
    if topic.startswith("/"):
        return
    await generate_and_show(update, context, topic, photo_id=None)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    topic = (update.message.caption or "").strip()
    if not topic:
        await update.message.reply_text("Добавь подпись к фото — это будет тема поста 📝")
        return
    photo_id = update.message.photo[-1].file_id
    await generate_and_show(update, context, topic, photo_id=photo_id)

async def generate_and_show(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, photo_id):
    msg = await update.message.reply_text("⏳ Генерирую пост...")
    content = generate_post(topic)
    context.user_data["pending_text"] = content
    context.user_data["pending_topic"] = topic
    context.user_data["pending_photo"] = photo_id

    await msg.delete()
    if photo_id:
        await update.message.reply_photo(photo=photo_id, caption=content, reply_markup=preview_actions_menu())
    else:
        await update.message.reply_text(content, reply_markup=preview_actions_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != MY_ID:
        await query.answer()
        return
    await query.answer()

    if query.data == "new_post":
        await query.message.reply_text("Напиши тему поста (можно с фото и подписью):")

    elif query.data == "help":
        await help_command(update, context)

    elif query.data == "approve":
        content = context.user_data.get("pending_text")
        photo_id = context.user_data.get("pending_photo")
        if not content:
            await query.message.reply_text("Нет поста для публикации. Сначала напиши тему.")
            return
        if photo_id:
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo_id, caption=content)
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=content)
        context.user_data["pending_text"] = None
        context.user_data["pending_photo"] = None
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ Пост опубликован в канал!")

    elif query.data == "regenerate":
        topic = context.user_data.get("pending_topic")
        photo_id = context.user_data.get("pending_photo")
        if not topic:
            await query.message.reply_text("Нет темы для повторной генерации.")
            return
        await query.message.reply_text("⏳ Генерирую новый вариант...")
        content = generate_post(topic)
        context.user_data["pending_text"] = content
        if photo_id:
            await query.message.reply_photo(photo=photo_id, caption=content, reply_markup=preview_actions_menu())
        else:
            await query.message.reply_text(content, reply_markup=preview_actions_menu())

    elif query.data == "cancel":
        context.user_data["pending_text"] = None
        context.user_data["pending_photo"] = None
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("❌ Отменено.")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
print("🤖 Бот запущен!")
app.run_polling()
