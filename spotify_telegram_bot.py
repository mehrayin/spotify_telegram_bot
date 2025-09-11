# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot gunicorn

from flask import Flask, request
import requests
import telegram
import threading
import datetime
import os
import time
import asyncio

# ====== تنظیمات از Environment Variables ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")

# ====== چک کامل Environment Variables ======
required_envs = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "REFRESH_TOKEN"]
missing_envs = [var for var in required_envs if not os.environ.get(var)]
if missing_envs:
    raise EnvironmentError(f"The following environment variables are NOT set: {', '.join(missing_envs)}")

# ====== ساخت اپ Flask ======
app = Flask(__name__)

# ====== مسیر اصلی ======
@app.route("/")
def index():
    return "Spotify Telegram Bot is running!"

# ====== مسیر Callback اسپاتیفای ======
@app.route("/callback")
def callback():
    code = request.args.get("code")
    if code:
        return f"Spotify Authorization Code: {code}"
    else:
        return "Spotify Authorization - No code found."

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
async def send_telegram_async(message):
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

def send_telegram(message):
    asyncio.run(send_telegram_async(message))

# ====== ارسال پیام تست ======
def send_test_message():
    try:
        send_telegram("✅ Test message: Bot is running!")
        print("Test message sent successfully!")
    except Exception as e:
        print("Failed to send test message:", e)

# ====== چک و ارسال ریلیزها در Thread جدا ======
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
            time.sleep(3600)  # یک ساعت صبر کن
        except Exception as e:
            print("Error:", e)
            time.sleep(60)

def start_bot_thread():
    thread = threading.Thread(target=send_releases)
    thread.daemon = True
    thread.start()

# ====== ساخت شی Bot برای Webhook تلگرام ======
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if WEBHOOK_SECRET and header_secret != WEBHOOK_SECRET:
        return ("Forbidden", 403)

    data = request.get_json(force=True)
    print("Incoming update:", data)

    try:
        update = telegram.Update.de_json(data, bot)
    except Exception as e:
        print("Failed to parse update:", e)
        return ("Bad Request", 400)

    if update.message and update.message.text:
        chat_id = update.message.chat.id
        text = update.message.text
        bot.send_message(chat_id=chat_id, text=f"پیام دریافت شد. متن: {text}")

    return ("OK", 200)

# ====== اجرای برنامه ======
if __name__ == "__main__":
    send_test_message()
    start_bot_thread()
    PORT = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=PORT)
