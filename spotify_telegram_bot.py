import os
import json
import datetime
import requests
from flask import Flask, request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ====== تنظیمات ======
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
RAILWAY_URL = os.getenv("RAILWAY_URL")

# ====== Flask ======
app = Flask(__name__)

# ====== کیبورد ======
keyboard = [
    [KeyboardButton("یک ماه گذشته"), KeyboardButton("۳ ماه گذشته")],
    [KeyboardButton("۶ ماه گذشته"), KeyboardButton("۱۲ ماه گذشته")],
    [KeyboardButton("لغو")]
]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ====== فایل ذخیره پیام‌های فرستاده شده ======
SENT_FILE = "sent_albums.json"
if os.path.exists(SENT_FILE):
    with open(SENT_FILE, "r", encoding="utf-8") as f:
        sent_albums = set(json.load(f))
else:
    sent_albums = set()

def save_sent_albums():
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_albums), f, ensure_ascii=False, indent=2)

# ====== دستورات اسپاتیفای ======
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

def get_followed_artists(token):
    artists = []
    url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    while url:
        r = requests.get(url, headers=headers).json()
        items = r.get("artists", {}).get("items", [])
        artists.extend(items)
        after = r.get("artists", {}).get("cursors", {}).get("after")
        url = f"https://api.spotify.com/v1/me/following?type=artist&limit=50&after={after}" if after else None
    return artists

def get_albums_for_artist(token, artist_id, months_delta=None):
    albums = []
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums?include_groups=album,single&limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    while url:
        r = requests.get(url, headers=headers).json()
        items = r.get("items", [])
        for a in items:
            if months_delta:
                try:
                    release_date = a.get("release_date", "1900-01-01")
                    release_dt = datetime.datetime.fromisoformat(release_date)
                    cutoff = datetime.datetime.now() - months_delta
                    if release_dt < cutoff:
                        continue
                except:
                    continue
            albums.append(a)
        url = r.get("next")
    return albums

# ====== تلگرام ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 ربات آماده به کار است!\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=reply_markup)

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
        token = get_access_token()
        artists = get_followed_artists(token)
        for artist in artists:
            artist_name = artist["name"]
            artist_id = artist["id"]
            albums = get_albums_for_artist(token, artist_id, months_delta=delta)
            for album in albums:
                album_id = album["id"]
                if album_id in sent_albums:
                    continue
                sent_albums.add(album_id)
                save_sent_albums()  # ذخیره تغییرات

                name = album["name"]
                release_date = album.get("release_date", "نامشخص")
                url = album["external_urls"]["spotify"]
                image = album["images"][0]["url"] if album["images"] else None

                caption = f"🎵 {name}\n👤 {artist_name}\n📅 {release_date}"
                if image:
                    await update.message.reply_photo(
                        photo=image,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("باز کردن در Spotify", url=url)]
                        ])
                    )
                else:
                    await update.message.reply_text(f"{caption}\n🔗 {url}")

# ====== Flask webhook ======
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    application.update_queue.put_nowait(update)
    return "OK"

# ====== اجرای ربات ======
if __name__ == "__main__":
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path="webhook",
        webhook_url=f"https://{RAILWAY_URL}/webhook"
    )

