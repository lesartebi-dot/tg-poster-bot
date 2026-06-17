import os, logging
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
MY_ID = os.getenv("MY_ID", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

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

KB_PUBLISH = "✅ Опубликовать"
KB_REGEN = "🔄 Сгенерировать снова"
KB_CANCEL = "❌ Отмена"
KB_HELP = "📋 Помощь"

def idle_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton(KB_HELP)]], resize_keyboard=True)

def preview_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(KB_PUBLISH), KeyboardButton(KB_REGEN)], [KeyboardButton(KB_CANCEL)]],
        resize_keyboard=True,
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот для постинга готов!\n\n"
        "Напиши тему поста текстом — сгенерирую готовый текст.\n"
        "После этого можешь прислать фото — оно прикрепится к посту перед публикацией.\n"
        "Когда всё готово — жми ✅ Опубликовать на клавиатуре внизу.",
        reply_markup=idle_keyboard(),
    )

async def help_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Как пользоваться:\n\n"
        "1. Напиши тему — получишь готовый текст поста\n"
        "2. (опционально) Пришли фото — оно прикрепится к этому посту\n"
        "3. Нажми ✅ Опубликовать на клавиатуре\n"
        "4. 🔄 — другой вариант текста, ❌ — отмена",
        reply_markup=idle_keyboard() if not context.user_data.get("pending_text") else preview_keyboard(),
    )

async def send_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = context.user_data.get("pending_text")
    photo_id = context.user_data.get("pending_photo")
    if photo_id:
        await update.message.reply_photo(photo=photo_id, caption=content, reply_markup=preview_keyboard())
    else:
        await update.message.reply_text(content, reply_markup=preview_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    text = update.message.text.strip()

    if text == KB_HELP:
        await help_text(update, context)
        return
    if text == KB_PUBLISH:
        await do_publish(update, context)
        return
    if text == KB_REGEN:
        await do_regenerate(update, context)
        return
    if text == KB_CANCEL:
        await do_cancel(update, context)
        return
    if text.startswith("/"):
        return

    # любой другой текст = новая тема поста
    await do_generate(update, context, text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    photo_id = update.message.photo[-1].file_id
    caption = (update.message.caption or "").strip()

    if not context.user_data.get("pending_text"):
        if caption:
            context.user_data["pending_photo"] = photo_id
            await do_generate(update, context, caption)
        else:
            await update.message.reply_text("Сначала напиши тему текстом, или пришли фото с подписью-темой 🙂")
        return

    context.user_data["pending_photo"] = photo_id
    await update.message.reply_text("🖼 Фото прикреплено к посту.")
    await send_preview(update, context)

async def do_generate(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str):
    msg = await update.message.reply_text("⏳ Генерирую пост...")
    try:
        content = generate_post(topic)
    except Exception as e:
        log.exception("generate error")
        await msg.edit_text(f"⚠️ Ошибка генерации: {e}")
        return
    context.user_data["pending_text"] = content
    context.user_data["pending_topic"] = topic
    await msg.delete()
    await send_preview(update, context)

async def do_regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = context.user_data.get("pending_topic")
    if not topic:
        await update.message.reply_text("Нет темы для повторной генерации.", reply_markup=idle_keyboard())
        return
    await update.message.reply_text("⏳ Генерирую новый вариант...")
    content = generate_post(topic)
    context.user_data["pending_text"] = content
    await send_preview(update, context)

async def do_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = context.user_data.get("pending_text")
    photo_id = context.user_data.get("pending_photo")
    if not content:
        await update.message.reply_text("Нет поста для публикации. Сначала напиши тему.", reply_markup=idle_keyboard())
        return
    if photo_id:
        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo_id, caption=content)
    else:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=content)
    context.user_data["pending_text"] = None
    context.user_data["pending_photo"] = None
    context.user_data["pending_topic"] = None
    await update.message.reply_text("✅ Пост опубликован в канал!", reply_markup=idle_keyboard())

async def do_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pending_text"] = None
    context.user_data["pending_photo"] = None
    context.user_data["pending_topic"] = None
    await update.message.reply_text("❌ Отменено.", reply_markup=idle_keyboard())

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))
print("🤖 Бот запущен!")
app.run_polling()
