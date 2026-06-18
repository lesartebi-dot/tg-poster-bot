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

STYLE_PROMPT = """Ты пишешь посты для Telegram-канала АПЭТ (ассоциация продавцов электронной торговли) — про e-commerce, маркетплейсы, продавцов, регулирование рынка и инвестиции.

СТРУКТУРА:
1. Заголовок — короткий, по существу, без эмодзи и кликбейта (например: "Цифровые платформы как инфраструктура для роста продавцов")
2. Вводный абзац — что произошло (конференция, сессия, исследование) и о чём в целом речь
3. Раскрытие темы — 2-4 абзаца аналитики: почему это важно, что изменилось для рынка, какой контекст
4. Список через 🔹 — конкретные пункты, направления или инструменты (3-9 пунктов)
5. Абзац "Для селлеров это..." — практический вывод, что это значит для продавцов
6. Абзац от лица АПЭТ — "Мы в АПЭТ считаем..." / "Для АПЭТ это важное направление..." — позиция организации
7. Финал — короткий итоговый тезис, без эмодзи-восклицаний

СТИЛЬ:
- Деловой, экспертный, спокойный тон — НЕ разговорный, без "ты", обращение нейтральное
- Никакого кликбейта, провокаций, восклицательных знаков в заголовке
- Эмодзи используются ТОЛЬКО как маркеры списка (🔹) и в самом конце для ссылок (🛒💙📷🌟) — больше нигде
- Термины: маркетплейсы, селлеры, МСП, ПВЗ, e-commerce, платформенная экономика
- Длина: 300-450 слов
- Структура с короткими абзацами (1-3 предложения), много пустых строк между ними

ЗАПРЕЩЕНО:
- Эмодзи в заголовке или тексте абзацев
- Восклицательные знаки
- Разговорный тон, обращение на "ты"
- Слова "хайп", "вау", "крутой", "топ" """

def generate_post(topic):
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": [
            {"role": "system", "content": STYLE_PROMPT},
            {"role": "user", "content": f"Напиши пост на тему: {topic}"}
        ], "max_tokens": 900},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

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
        "После генерации текста можешь прислать фото или видео — прикреплю к посту.\n"
        "Когда всё готово — жми ✅ Опубликовать.",
        reply_markup=idle_keyboard(),
    )

async def help_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Как пользоваться:\n\n"
        "✍️ Новый пост — начать с темы\n"
        "Пришли фото или видео — прикрепится к текущему посту\n"
        "✅ Опубликовать — отправить в канал\n"
        "🔄 Сгенерировать снова — другой вариант текста\n"
        "🗑 Убрать медиа — снять прикреплённое фото/видео\n"
        "❌ Отмена — сбросить текущий пост",
        reply_markup=current_keyboard(context),
    )

async def send_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = context.user_data.get("pending_text")
    media = context.user_data.get("pending_media")  # (type, file_id) или None
    kb = preview_keyboard(bool(media))
    if media:
        kind, file_id = media
        if kind == "photo":
            await update.message.reply_photo(photo=file_id, caption=content, reply_markup=kb)
        else:
            await update.message.reply_video(video=file_id, caption=content, reply_markup=kb)
    else:
        await update.message.reply_text(content, reply_markup=kb)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    text = update.message.text.strip()

    if text == KB_HELP:
        await help_text(update, context); return
    if text == KB_NEW:
        context.user_data["awaiting_topic"] = True
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

    # обычный текст = тема нового поста (всегда, для удобства)
    await do_generate(update, context, text)

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        kind = "photo"
        caption = (update.message.caption or "").strip()
    elif update.message.video:
        file_id = update.message.video.file_id
        kind = "video"
        caption = (update.message.caption or "").strip()
    else:
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
    content = generate_post(topic)
    context.user_data["pending_text"] = content
    await send_preview(update, context)

async def do_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = context.user_data.get("pending_text")
    media = context.user_data.get("pending_media")
    if not content:
        await update.message.reply_text("Нет поста для публикации. Нажми ✍️ Новый пост.", reply_markup=idle_keyboard())
        return
    if media:
        kind, file_id = media
        if kind == "photo":
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=file_id, caption=content)
        else:
            await context.bot.send_video(chat_id=CHANNEL_ID, video=file_id, caption=content)
    else:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=content)
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
app.run_polling()
