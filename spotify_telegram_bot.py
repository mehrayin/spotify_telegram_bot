# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot==20.6

from flask import Flask, request
import requests
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import datetime
import os
import threading
import time
from queue import Queue

# ====== تنظیمات ======
DEEZER_USER_ID = os.environ.get("4049345442")  # ID کاربر Deezer
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")

app = Flask(__name__)
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# ====== Queue و Worker ======
MAX_WORKERS = 1
REQUEST_DELAY = 1
album_queue = Queue()

def worker():
    while True:
        func, args = album_queue.get()
        try:
            func(*args)
        except Exception as e:
            print("Worker error:", e)
        album_queue.task_done()
        time.sleep(REQUEST_DELAY)

for _ in range(MAX_WORKERS):
    t = threading.Thread(target=worker, daemon=True)
    t.start()

# ====== گرفتن هنرمندان دنبال‌شده ======
def get_followed_artists():
    url = f"https://api.deezer.com/user/{DEEZER_USER_ID}/followings?limit=50"
    artists = []
    while url:
        resp = requests.get(url).json()
        items = resp.get("data", [])
        artists.extend(items)
        url = resp.get("next")
    return artists

# ====== گرفتن آلبوم‌های جدید ======
def get_recent_albums(artist_id, months=6, max_per_artist=5):
    url = f"https://api.deezer.com/artist/{artist_id}/albums"
    albums = []
    while url:
        resp = requests.get(url).json()
        items = resp.get("data", [])
        cutoff = datetime.datetime.now() - datetime.timedelta(days=months*30)
        for a in items:
            try:
                date_obj = datetime.datetime.strptime(a['release_date'], "%Y-%m-%d")
            except:
                continue
            if date_obj > cutoff:
                a['parsed_date'] = date_obj
                albums.append(a)
            if len(albums) >= max_per_artist:
                break
        url = resp.get("next")
        if len(albums) >= max_per_artist:
            break
    return albums

# ====== ارسال آلبوم‌ها به تلگرام ======
def enqueue_album(album, artist_name):
    album_queue.put((send_album_to_telegram, (album, artist_name)))

def send_album_to_telegram(album, artist_name):
    text = f"🎵 <b>{artist_name}</b> - {album['title']}<br>" \
           f"📅 {album['parsed_date'].strftime('%Y-%m-%d')}<br>" \
           f"<a href='{album['link']}'>لینک Deezer</a>"
    photo_url = album['cover_medium']
    try:
        bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=photo_url, caption=text, parse_mode="HTML")
    except Exception as e:
        print("Failed to send album:", e)

# ====== پردازش ریلیزها ======
def process_albums(months, query):
    try:
        artists = get_followed_artists()
        if not artists:
            try:
                query.edit_message_text("هیچ هنرمندی دنبال نشده است.")
            except telegram.error.BadRequest:
                pass
            return
        try:
            query.edit_message_text(f"⏳ در حال گرفتن ریلیزهای {months} ماه گذشته...")
        except telegram.error.BadRequest:
            pass
        for artist in artists:
            albums = get_recent_albums(artist['id'], months=months)
            for album in albums:
                enqueue_album(album, artist['name'])
        album_queue.join()
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ نمایش ریلیزها تمام شد.")
    except Exception as e:
        try:
            query.edit_message_text(f"❌ خطا: {e}")
        except telegram.error.BadRequest:
            pass

# ====== هندلر دکمه‌ها ======
def handle_button_click(update):
    query = update.callback_query
    data = query.data

    if data == "cancel":
        keyboard = [
            [InlineKeyboardButton("یک ماه گذشته", callback_data="1")],
            [InlineKeyboardButton("۳ ماه گذشته", callback_data="3")],
            [InlineKeyboardButton("۶ ماه گذشته", callback_data="6")],
            [InlineKeyboardButton("۱۲ ماه گذشته", callback_data="12")],
            [InlineKeyboardButton("❌ لغو", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            query.edit_message_text("✅ عملیات لغو شد.", reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" not in str(e):
                raise e
        return

    try:
        months = int(data)
        threading.Thread(target=process_albums, args=(months, query), daemon=True).start()
    except Exception as e:
        try:
            query.edit_message_text(f"❌ خطا: {e}")
        except telegram.error.BadRequest:
            pass

# ====== وبهوک تلگرام ======
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if WEBHOOK_SECRET and header_secret != WEBHOOK_SECRET:
        return ("Forbidden", 403)

    data = request.get_json(force=True)
    update = telegram.Update.de_json(data, bot)

    if update.message and update.message.text == "/start":
        keyboard = [
            [InlineKeyboardButton("یک ماه گذشته", callback_data="1")],
            [InlineKeyboardButton("۳ ماه گذشته", callback_data="3")],
            [InlineKeyboardButton("۶ ماه گذشته", callback_data="6")],
            [InlineKeyboardButton("۱۲ ماه گذشته", callback_data="12")],
            [InlineKeyboardButton("❌ لغو", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.send_message(
            chat_id=update.message.chat.id,
            text="🤖 ربات آماده به کار است.\nیکی از بازه‌های زمانی را انتخاب کنید:",
            reply_markup=reply_markup
        )

    elif update.callback_query:
        handle_button_click(update)

    return ("OK", 200)

# ====== اجرای برنامه ======
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)
