# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot apscheduler

from flask import Flask, request
import requests
import telegram
import datetime
import os
from apscheduler.schedulers.background import BackgroundScheduler

# ====== تنظیمات از Environment Variables ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")
PORT = int(os.environ.get("PORT", 5000))

# ====== ساخت اپ Flask ======
app = Flask(__name__)

# ====== بررسی تنظیمات محیطی ======
for var_name in ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "REFRESH_TOKEN"]:
    if not os.environ.get(var_name):
        print(f"ERROR: Environment variable {var_name} is NOT set!")

# ====== توابع کمکی ======
def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    response = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    return response.json().get("access_token")

def get_followed_artists(token):
    url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json().get("artists", {}).get("items", [])

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
            if date_obj > cutoff:
                recent.append(a)
        except:
            continue
    return recent

def send_telegram(message):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        except Exception as e:
            print("Failed to send Telegram message:", e)

def send_releases_job():
    try:
        access_token = refresh_access_token(REFRESH_TOKEN)
        if not access_token:
            print("Access token not available")
            return
        artists = get_followed_artists(access_token)
        for artist in artists:
            name = artist['name']
            artist_id = artist['id']
            albums = get_recent_albums(access_token, artist_id)
            for album in albums:
                msg = f"🎵 New release by {name}: {album['name']}\n{album['external_urls']['spotify']}"
                send_telegram(msg)
    except Exception as e:
        print("Error in send_releases_job:", e)

# ====== Flask routes ======
@app.route("/")
def index():
    return "Spotify Telegram Bot is running!"

@app.route("/callback")
def callback():
    code = request.args.get("code")
    return f"Spotify Authorization Code: {code}" if code else "Spotify Authorization - No code found."

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if WEBHOOK_SECRET and header_secret != WEBHOOK_SECRET:
        return ("Forbidden", 403)

    data = request.get_json(force=True)
    try:
        update = telegram.Update.de_json(data, bot)
        if update.message and update.message.text:
            chat_id = update.message.chat.id
            text = update.message.text
            bot.send_message(chat_id=chat_id, text=f"پیام دریافت شد. متن: {text}")
    except Exception as e:
        print("Failed to parse/update message:", e)
        return ("Bad Request", 400)

    return ("OK", 200)

# ====== APScheduler setup ======
scheduler = BackgroundScheduler()
scheduler.add_job(func=send_releases_job, trigger="interval", minutes=5)
scheduler.start()

# ====== پیام تستی ======
send_telegram("✅ Bot started successfully!")

# ====== اجرای برنامه ======
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
