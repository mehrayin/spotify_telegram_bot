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
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")

app = Flask(__name__)
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# ====== تنظیمات Rate Limit ======
MAX_WORKERS = 2       # کاهش تعداد Worker برای جلوگیری از 429
REQUEST_DELAY = 1     # افزایش فاصله بین هر درخواست (ثانیه)
album_queue = Queue() # صف ارسال آلبوم‌ها

# ====== Worker Queue ======
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

# ====== Access Token ======
def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    try:
        response = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
        if response.status_code != 200:
            print(f"Spotify token error {response.status_code}: {response.text}")
            return None
        res_json = response.json()
        return res_json.get("access_token")
    except Exception as e:
        print("Spotify token request failed:", e)
        return None

# ====== تابع GET امن با retry و مدیریت 429 ======
def safe_get(url, headers, retries=5, delay=5):
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", delay))
                print(f"Rate limit hit. Sleeping {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                print(f"Spotify GET error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Spotify GET exception: {e}")
        time.sleep(delay)
    return None

# ====== گرفتن همه هنرمندان با paging ======
def get_all_followed_artists(token):
    artists = []
    url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
    headers = {"Authorization": f"Bearer {token}"}

    while url:
        data = safe_get(url, headers)
        if not data:
            break
        items = data.get("artists", {}).get("items", [])
        artists.extend(items)
        url = data.get("artists", {}).get("next")
    return artists

# ====== گرفتن همه آلبوم‌ها با paging ======
def get_all_albums(token, artist_id):
    albums = []
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums?include_groups=album,single&limit=50"
    headers = {"Authorization": f"Bearer {token}"}

    while url:
        data = safe_get(url, headers)
        if not data:
            break
        items = data.get("items", [])
        albums.extend(items)
        url = data.get("next")
    return albums

# ====== گرفتن ریلیزهای اخیر ======
def get_recent_albums(token, artist_id, months=6):
    all_albums = get_all_albums(token, artist_id)
    cutoff = datetime.datetime.now() - datetime.timedelta(days=months*30)
    recent = []
    for a in all_albums:
        try:
            date_obj = datetime.datetime.strptime(a['release_date'], "%Y-%m-%d")
        except:
            continue
        if date_obj > cutoff:
            a['parsed_date'] = date_obj
            recent.append(a)
    return recent

# ====== ارسال آلبوم‌ها با Queue ======
def enqueue_album(album, artist_name):
    album_queue.put((send_album_to_telegram, (album, artist_name)))

# ====== ارسال آلبوم به تلگرام با HTML Mode ======
def send_album_to_telegram(album, artist_name):
    text = f"🎵 <b>{artist_name}</b> - {album['name']}<br>" \
           f"📅 {album['parsed_date'].strftime('%Y-%m-%d')}<br>" \
           f"<a href='{album['external_urls']['spotify']}'>لینک اسپاتیفای</a>"

    photo_url = album['images'][0]['url'] if album.get('images') else None
    try:
        if photo_url:
            bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=photo_url, caption=text, parse_mode="HTML")
        else:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="HTML")
    except Exception as e:
        print("Failed to send album:", e)

# ====== پردازش ریلیزها در Thread ======
def process_albums(months, query):
    try:
        token = refresh_access_token(REFRESH_TOKEN)
        if not token:
            try:
                query.edit_message_text("❌ خطا: دریافت Access Token ناموفق بود.")
            except telegram.error.BadRequest:
                pass
            return

        artists = get_all_followed_artists(token)
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
            albums = get_recent_albums(token, artist['id'], months=months)
            for album in albums:
                enqueue_album(album, artist['name'])

        album_queue.join()  # منتظر می‌ماند تا همه آلبوم‌ها ارسال شوند
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
