import os, logging
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.error import TelegramError
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
MY_ID = os.getenv("MY_ID", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

CAPTION_LIMIT = 1024

STYLE_PROMPT = """Ты пишешь посты для Telegram-канала АПЭТ (ассоциация продавцов электронной торговли) — про e-commerce, маркетплейсы, продавцов, регулирование рынка и инвестиции.

СТРУКТУРА:
1. Заголовок — короткий, по существу, без эмодзи и кликбейта
2. Вводный абзац — что произошло и о чём речь (1-2 предложения)
3. Раскрытие темы — 1-2 коротких абзаца аналитики
4. Список через 🔹 — 3-5 конкретных пунктов
5. Короткий практический вывод для селлеров
6. Финал — один итоговый тезис

СТИЛЬ:
- Деловой, экспертный, спокойный тон, без "ты"
- Без кликбейта и восклицательных знаков
- Эмодзи только как маркеры списка 🔹
- Термины: маркетплейсы, селлеры, МСП, ПВЗ, e-commerce
- СТРОГО до 850 символов всего текста — это жёсткий лимит, считай символы
- Короткие абзацы с пустыми строками между ними

ЗАПРЕЩЕНО: эмодзи в заголовке, восклицательные знаки, разговорный тон, превышение 850 символов""" 

def generate_post(topic):
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": [
            {"role": "system", "content": STYLE_PROMPT},
            {"role": "user", "content": f"Напиши пост на тему: {topic}"}
        ], "max_tokens": 500},
        timeout=30
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
    # подстраховка - жёстко обрезаем если модель не уложилась
    if len(text) > CAPTION_LIMIT:
        text = text[:CAPTION_LIMIT - 1].rsplit(" ", 1)[0] + "…"
    return text

def is_owner(update: Update) -> bool:
    return str(update.effective_user.id) == MY_ID

KB_NEW = "✍️ Новый пост"
KB_PUBLISH = "✅ Опубликовать"
KB_REGEN = "🔄 Сгенерировать снова"
KB_REMOVE_MEDIA = "🗑 Убрать медиа"
KB_CANCEL = "❌ Отмена"
KB_HELP = "📋 Помощь"

def idle_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton(KB_NEW), KeyboardButton(KB_HELP)]], resize_keyboard=True)

def preview_keyboard(has_media: bool):
    rows = [[KeyboardButton(KB_PUBLISH), KeyboardButton(KB_REGEN)]]
    if has_media:
        rows.append([KeyboardButton(KB_REMOVE_MEDIA)])
    rows.append([KeyboardButton(KB_CANCEL)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def current_keyboard(context):
    return preview_keyboard(bool(context.user_data.get("pending_media"))) if context.user_data.get("pending_text") else idle_keyboard()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🤖 Бот для постинга АПЭТ готов.\n\n"
        "Нажми ✍️ Новый пост и пришли тему.\n"
        "После генерации текста можешь прислать фото или видео — прикреплю прямо к посту одним сообщением.\n"
        "Когда всё готово — жми ✅ Опубликовать.",
        reply_markup=idle_keyboard(),
    )

async def help_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Как пользоваться:\n\n"
        "✍️ Новый пост — начать с темы\n"
        "Пришли фото или видео — прикрепится прямо к посту\n"
        "✅ Опубликовать — отправить в канал одним сообщением\n"
        "🔄 Сгенерировать снова — другой вариант текста\n"
        "🗑 Убрать медиа — снять прикреплённое фото/видео\n"
        "❌ Отмена — сбросить текущий пост",
        reply_markup=current_keyboard(context),
    )

async def send_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = context.user_data.get("pending_text")
    media = context.user_data.get("pending_media")
    kb = preview_keyboard(bool(media))
    try:
        if media:
            kind, file_id = media
            if kind == "photo":
                await update.message.reply_photo(photo=file_id, caption=content, reply_markup=kb)
            else:
                await update.message.reply_video(video=file_id, caption=content, reply_markup=kb, write_timeout=180, read_timeout=180)
        else:
            await update.message.reply_text(content, reply_markup=kb)
    except TelegramError as e:
        log.exception("send_preview failed")
        context.user_data["pending_media"] = None
        await update.message.reply_text(f"⚠️ Не получилось показать медиа: {e}\nТекст поста сохранён без медиа.")
        await update.message.reply_text(content, reply_markup=preview_keyboard(False))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    text = update.message.text.strip()

    if text == KB_HELP:
        await help_text(update, context); return
    if text == KB_NEW:
        await update.message.reply_text("Напиши тему поста:")
        return
    if text == KB_PUBLISH:
        await do_publish(update, context); return
    if text == KB_REGEN:
        await do_regenerate(update, context); return
    if text == KB_REMOVE_MEDIA:
        context.user_data["pending_media"] = None
        await update.message.reply_text("🗑 Медиа убрано.")
        await send_preview(update, context)
        return
    if text == KB_CANCEL:
        await do_cancel(update, context); return
    if text.startswith("/"):
        return

    await do_generate(update, context, text)

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    try:
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            kind = "photo"
        elif update.message.video:
            v = update.message.video
            if v.file_size and v.file_size > 50 * 1024 * 1024:
                await update.message.reply_text("⚠️ Видео больше 50 МБ — бот не сможет его отправить. Сожми видео.")
                return
            file_id = v.file_id
            kind = "video"
        else:
            return
        caption = (update.message.caption or "").strip()
    except Exception as e:
        log.exception("handle_media error")
        await update.message.reply_text(f"⚠️ Не смог обработать файл: {e}")
        return

    if not context.user_data.get("pending_text"):
        if caption:
            context.user_data["pending_media"] = (kind, file_id)
            await do_generate(update, context, caption)
        else:
            await update.message.reply_text("Сначала напиши тему текстом, или пришли медиа с подписью-темой 🙂")
        return

    context.user_data["pending_media"] = (kind, file_id)
    label = "Фото" if kind == "photo" else "Видео"
    await update.message.reply_text(f"📎 {label} прикреплено к посту.")
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
    try:
        content = generate_post(topic)
    except Exception as e:
        log.exception("regenerate error")
        await update.message.reply_text(f"⚠️ Ошибка генерации: {e}")
        return
    context.user_data["pending_text"] = content
    await send_preview(update, context)

async def do_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = context.user_data.get("pending_text")
    media = context.user_data.get("pending_media")
    if not content:
        await update.message.reply_text("Нет поста для публикации. Нажми ✍️ Новый пост.", reply_markup=idle_keyboard())
        return
    try:
        if media:
            kind, file_id = media
            if kind == "photo":
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=file_id, caption=content)
            else:
                await context.bot.send_video(chat_id=CHANNEL_ID, video=file_id, caption=content, write_timeout=180, read_timeout=180)
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=content)
    except TelegramError as e:
        log.exception("publish failed")
        await update.message.reply_text(f"⚠️ Не удалось опубликовать: {e}")
        return
    context.user_data.clear()
    await update.message.reply_text("✅ Пост опубликован в канал!", reply_markup=idle_keyboard())

async def do_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено.", reply_markup=idle_keyboard())

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media))
app.add_handler(MessageHandler(filters.TEXT, handle_text))
print("🤖 Бот запущен!")
app.run_polling(read_timeout=60, write_timeout=60)
