# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot
from flask import Flask
from flask import request, abort
import requests
import telegram
import threading
import datetime
import os
import time

# ====== تنظیمات از Environment Variables ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

app = Flask(__name__)

# ====== دریافت Access Token با Refresh Token ======
def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    response = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    res_json = response.json()
    return res_json.get("access_token")

# ====== گرفتن هنرمندان دنبال‌شده ======
def get_followed_artists(token):
    url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    artists = response.json().get("artists", {}).get("items", [])
    return artists

# ====== گرفتن ریلیزهای جدید ======
def get_recent_albums(token, artist_id, months=6):
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"include_groups": "album,single", "limit": 50}
    response = requests.get(url, headers=headers, params=params)
    albums = response.json().get("items", [])
    cutoff = datetime.datetime.now() - datetime.timedelta(days=months*30)
    recent = []
    for a in albums:
        try:
            date_obj = datetime.datetime.strptime(a['release_date'], "%Y-%m-%d")
        except:
            continue
        if date_obj > cutoff:
            recent.append(a)
    return recent

# ====== ارسال پیام به تلگرام ======
def send_telegram(message):
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# ====== چک و ارسال ریلیزها ======
def send_releases():
    while True:
        try:
            access_token = refresh_access_token(REFRESH_TOKEN)
            artists = get_followed_artists(access_token)
            for artist in artists:
                name = artist['name']
                artist_id = artist['id']
                albums = get_recent_albums(access_token, artist_id)
                for album in albums:
                    msg = f"🎵 New release by {name}: {album['name']}\n{album['external_urls']['spotify']}"
                    send_telegram(msg)
            # یک ساعت صبر کن تا دوباره چک کنه
            time.sleep(3600)
        except Exception as e:
            print("Error:", e)
            time.sleep(60)

# ====== اجرای Thread برای ارسال ریلیزها ======
def start_bot_thread():
    thread = threading.Thread(target=send_releases)
    thread.daemon = True
    thread.start()

# ====== مسیر اصلی Flask ======
@app.route("/")
def index():
    return "Spotify Telegram Bot is running!"

# ====== اجرای برنامه ======
if __name__ == "__main__":
    start_bot_thread()
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)

# ساختن یک شی Bot سراسری (از ENV خوانده می‌شود)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telegram.Bot(token=BOT_TOKEN)

# یک SECRET ساده برای تایید اینکه درخواست‌ها از تلگرام میان
# (در Railway متغیر محیطی WEBHOOK_SECRET را با یک رشته امن قرار بده)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    # بررسی header امنیتی (تلگرام آن را می‌فرستد اگر هنگام setWebhook secret_token تنظیم کرده باشی)
    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if WEBHOOK_SECRET and header_secret != WEBHOOK_SECRET:
        return ("Forbidden", 403)

    data = request.get_json(force=True)
    # لاگ کردن خام برای عیب‌یابی (در لاگ‌های Railway ظاهر می‌شود)
    print("Incoming update:", data)

    try:
        update = telegram.Update.de_json(data, bot)
    except Exception as e:
        print("Failed to parse update:", e)
        return ("Bad Request", 400)

    # نمونه ساده: اگر پیام متنی اومد جواب بده
    if update.message and update.message.text:
        chat_id = update.message.chat.id
        text = update.message.text
        bot.send_message(chat_id=chat_id, text=f"پیام دریافت شد. متن: {text}")

    return ("OK", 200)
