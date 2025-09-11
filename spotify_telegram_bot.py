import os
import requests
import datetime
from flask import Flask, request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ====== متغیرهای محیطی ======
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")

# ====== Flask ======
app = Flask(__name__)

# ====== کیبورد ======
keyboard = [
    [KeyboardButton("یک ماه گذشته"), KeyboardButton("۳ ماه گذشته")],
    [KeyboardButton("۶ ماه گذشته"), KeyboardButton("۱۲ ماه گذشته")],
    [KeyboardButton("لغو")]
]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ====== توابع اسپاتیفای ======
def get_access_token():
    url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }
    r = requests.post(url, data=data)
    return r.json().get("access_token")

def get_new_releases(limit=10, date_filter=None):
    token = get_access_token()
    if not token:
        return []

    url = f"https://api.spotify.com/v1/browse/new-releases?limit={limit}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    releases = r.json().get("albums", {}).get("items", [])

    if date_filter:
        cutoff_date = datetime.datetime.now() - date_filter
        releases = [
            album for album in releases
            if datetime.datetime.fromisoformat(album["release_date"])
            >= cutoff_date
        ]
    return releases

# ====== دستورات تلگرام ======
async def set_commands(application: Application):
    commands = [
        BotCommand("start", "شروع ربات"),
        BotCommand("cancel", "لغو دستور فعلی"),
        BotCommand("help", "راهنما"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 ربات آماده به کار است!\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 راهنما:\n"
        "/start → شروع ربات\n"
        "/cancel → لغو دستور\n"
        "/help → نمایش راهنما"
    )

# ====== هندلر دکمه‌های کیبورد ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    delta = None

    if text == "یک ماه گذشته":
        delta = datetime.timedelta(days=30)
    elif text == "۳ ماه گذشته":
        delta = datetime.timedelta(days=90)
    elif text == "۶ ماه گذشته":
        delta = datetime.timedelta(days=180)
    elif text == "۱۲ ماه گذشته":
        delta = datetime.timedelta(days=365)
    elif text == "لغو":
        await cancel(update, context)
        return

    if delta:
        releases = get_new_releases(limit=20, date_filter=delta)
        if not releases:
            await update.message.reply_text("هیچ ریلیزی در این بازه پیدا نشد.")
            return

        for album in releases:
            name = album["name"]
            artist = ", ".join(a["name"] for a in album["artists"])
            release_date = album.get("release_date", "نامشخص")
            url = album["external_urls"]["spotify"]
            image = album["images"][0]["url"] if album["images"] else None

            caption = f"🎵 {name}\n👤 {artist}\n📅 {release_date}"
            if image:
                await update.message.reply_photo(
                    photo=image,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("باز کردن در Spotify", url=url)]
                    ])
                )
            else:
                await update.message.reply_text(
                    f"{caption}\n🔗 {url}"
                )

# ====== اجرای Flask و ربات ======
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    application.update_queue.put_nowait(update)
    return "OK"

if __name__ == "__main__":
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.post_init = lambda _: set_commands(application)

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path="webhook",
        webhook_url=f"https://{os.getenv('RAILWAY_URL')}/webhook"
    )
