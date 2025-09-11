# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot

from flask import Flask, request
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
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")
PORT = int(os.environ.get("PORT", 5000))

# ====== Debug: چک کردن متغیرها ======
print("==== Debug: Environment Variables ====")
print("SPOTIFY_CLIENT_ID:", "Set" if SPOTIFY_CLIENT_ID else "NOT SET")
print("SPOTIFY_CLIENT_SECRET:", "Set" if SPOTIFY_CLIENT_SECRET else "NOT SET")
print("TELEGRAM_BOT_TOKEN:", "Set" if TELEGRAM_BOT_TOKEN else "NOT SET")
print("TELEGRAM_CHAT_ID:", TELEGRAM_CHAT_ID if TELEGRAM_CHAT_ID else "NOT SET")
print("REFRESH_TOKEN:", "Set" if REFRESH_TOKEN else "NOT SET")
print("WEBHOOK_SECRET:", WEBHOOK_SECRET)
print("PORT:", PORT)
print("======================================")

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
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("Spotify client credentials not set!")
        return None
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    try:
        response = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
        res_json = response.json()
        return res_json.get("access_token")
    except Exception as e:
        print("Failed to refresh token:", e)
        return None

# ====== گرفتن هنرمندان دنبال‌شده ======
def get_followed_artists(token):
    url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers)
        return response.json().get("artists", {}).get("items", [])
    except Exception as e:
        print("Failed to get followed artists:", e)
        return []

# ====== گرفتن ریلیزهای جدید ======
def get_recent_albums(token, artist_id, months=6):
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"include_groups": "album,single", "limit": 50}
    try:
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
    except Exception as e:
        print(f"Failed to get albums for artist {artist_id}: {e}")
        return []

# ====== ارسال پیام به تلگرام ======
def send_telegram(message):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        except Exception as e:
            print("Failed to send Telegram message:", e)
    else:
        print("Cannot send Telegram message: TELEGRAM_BOT_TOKEN or CHAT_ID not set!")

# ====== پیام تستی ======
def send_test_message():
    print("Sending test message...")
    send_telegram("✅ Test message: Bot is running!")

# ====== Thread چک ریلیزها ======
def send_releases():
    while True:
        try:
            access_token = refresh_access_token(REFRESH_TOKEN)
            if not access_token:
                print("Access token not available, retry in 60s")
                time.sleep(60)
                continue
            artists = get_followed_artists(access_token)
            for artist in artists:
                name = artist['name']
                artist_id = artist['id']
                albums = get_recent_albums(access_token, artist_id)
                for album in albums:
                    msg = f"🎵 New release by {name}: {album['name']}\n{album['external_urls']['spotify']}"
                    send_telegram(msg)
            # برای Railway بهتره sleep کوتاه باشه، مثلا 5 دقیقه
            time.sleep(300)
        except Exception as e:
            print("Error in send_releases:", e)
            time.sleep(60)

def start_bot_thread():
    thread = threading.Thread(target=send_releases)
    thread.daemon = True
    thread.start()

# ====== Bot برای Webhook ======
bot = None
if TELEGRAM_BOT_TOKEN:
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if WEBHOOK_SECRET and header_secret != WEBHOOK_SECRET:
        return ("Forbidden", 403)

    data = request.get_json(force=True)
    print("Incoming update:", data)

    if bot:
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

# ====== اجرای برنامه ======
if __name__ == "__main__":
    send_test_message()
    start_bot_thread()
    app.run(host="0.0.0.0", port=PORT)
