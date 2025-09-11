# pip install flask requests python-telegram-bot

from flask import Flask, request
import requests
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler
import threading
import datetime
import os
import json

# ====== تنظیمات ======
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ====== تلگرام ======
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# ====== اسپاتیفای ======
def get_access_token():
    url = "https://accounts.spotify.com/api/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET
    }
    r = requests.post(url, data=payload)
    return r.json().get("access_token")

def get_new_releases(access_token, limit=30):
    url = f"https://api.spotify.com/v1/browse/new-releases?country=US&limit={limit}"
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json()["albums"]["items"]
    else:
        print("خطا:", r.text)
        return []

# ====== فیلتر کردن ریلیز بر اساس بازه زمانی ======
def filter_by_months(albums, months):
    cutoff_date = datetime.date.today() - datetime.timedelta(days=30*months)
    results = []
    for album in albums:
        release_date = album["release_date"]
        # تاریخ ممکنه فقط سال یا سال-ماه باشه → باید normalize بشه
        if len(release_date) == 4:
            release_date = f"{release_date}-01-01"
        elif len(release_date) == 7:
            release_date = f"{release_date}-01"

        try:
            date_obj = datetime.date.fromisoformat(release_date)
            if date_obj >= cutoff_date:
                results.append(album)
        except:
            pass
    return results

# ====== ارسال آلبوم به تلگرام ======
def send_album(album):
    name = album["name"]
    artist = album["artists"][0]["name"]
    url = album["external_urls"]["spotify"]
    release_date = album["release_date"]
    image_url = album["images"][0]["url"] if album["images"] else None

    caption = f"🎵 *{name}* by *{artist}*\n📅 Release date: {release_date}\n🔗 [Spotify Link]({url})"

    try:
        if image_url:
            bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=image_url,
                caption=caption,
                parse_mode="Markdown"
            )
        else:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=caption, parse_mode="Markdown")
    except Exception as e:
        print("خطا در ارسال:", e)

# ====== دکمه‌ها ======
def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("یک ماه گذشته", callback_data="1")],
        [InlineKeyboardButton("۳ ماه گذشته", callback_data="3")],
        [InlineKeyboardButton("۶ ماه گذشته", callback_data="6")],
        [InlineKeyboardButton("۱۲ ماه گذشته", callback_data="12")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("✅ ربات آماده به کار است!\nیکی از بازه‌های زمانی را انتخاب کن:", reply_markup=reply_markup)

def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    months = int(query.data)

    access_token = get_access_token()
    if not access_token:
        query.edit_message_text("❌ خطا در گرفتن توکن اسپاتیفای")
        return

    releases = get_new_releases(access_token, limit=50)
    filtered = filter_by_months(releases, months)

    if not filtered:
        query.edit_message_text(f"هیچ ریلیزی در {months} ماه گذشته پیدا نشد.")
    else:
        query.edit_message_text(f"🎶 ریلیزهای {months} ماه گذشته:")
        for album in filtered:
            send_album(album)

# ====== Flask برای وبهوک ======
app = Flask(__name__)
dispatcher = Dispatcher(bot, None, workers=0)

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CallbackQueryHandler(button_handler))

@app.route(f"/webhook", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/")
def home():
    return "Spotify Telegram Bot with Buttons is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
