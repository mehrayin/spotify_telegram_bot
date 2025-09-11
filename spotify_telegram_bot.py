# pip install flask requests python-telegram-bot apscheduler pytz

from flask import Flask, request
import requests
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import datetime
import os

# ====== تنظیمات ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")
PORT = int(os.environ.get("PORT", 5000))

# ====== ساخت اپ Flask ======
app = Flask(__name__)
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# ====== جلوگیری از ارسال تکراری ======
sent_albums = set()

# ====== بازه پیش‌فرض ======
selected_months = 6  # اگر کاربر انتخاب نکرد، 6 ماه پیش نمایش بده

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

def send_album_messages(months):
    global sent_albums
    access_token = refresh_access_token(REFRESH_TOKEN)
    if not access_token:
        print("Access token not available")
        return
    artists = get_followed_artists(access_token)
    for artist in artists:
        name = artist['name']
        artist_id = artist['id']
        albums = get_recent_albums(access_token, artist_id, months=months)
        for album in albums:
            album_id = album['id']
            if album_id in sent_albums:
                continue
            album_name = album['name']
            release_date = album.get('release_date', 'Unknown')
            album_url = album['external_urls']['spotify']
            album_images = album.get('images', [])
            album_image_url = album_images[0]['url'] if album_images else None

            msg = f"🎵 New release by {name}:\n"
            msg += f"Album: {album_name}\n"
            msg += f"Release Date: {release_date}\n"
            msg += f"Link: {album_url}"

            try:
                if album_image_url:
                    bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=album_image_url, caption=msg)
                else:
                    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
            except Exception as e:
                print("Failed to send message/photo:", e)
            sent_albums.add(album_id)

# ====== ارسال پیام شروع با دکمه‌ها ======
def send_start_message():
    keyboard = [
        [
            InlineKeyboardButton("یک ماه گذشته", callback_data="1"),
            InlineKeyboardButton("3 ماه گذشته", callback_data="3")
        ],
        [
            InlineKeyboardButton("6 ماه گذشته", callback_data="6"),
            InlineKeyboardButton("12 ماه گذشته", callback_data="12")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                     text="✅ Bot is ready! Select the release timeframe:",
                     reply_markup=reply_markup)

# ====== Flask routes ======
@app.route("/")
def index():
    return "Spotify Telegram Bot is running!"

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    global selected_months
    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if WEBHOOK_SECRET and header_secret != WEBHOOK_SECRET:
        return ("Forbidden", 403)

    data = request.get_json(force=True)
    try:
        update = telegram.Update.de_json(data, bot)
        # متن پیام ساده
        if update.message and update.message.text:
            chat_id = update.message.chat.id
            bot.send_message(chat_id=chat_id, text=f"پیام دریافت شد. متن: {update.message.text}")

        # دکمه‌ها
        elif update.callback_query:
            query = update.callback_query
            selected_months = int(query.data)
            bot.answer_callback_query(callback_query_id=query.id, text=f"Selected {selected_months} month(s)")
            send_album_messages(selected_months)
    except Exception as e:
        print("Failed to parse/update message:", e)
        return ("Bad Request", 400)

    return ("OK", 200)

# ====== اجرای برنامه ======
if __name__ == "__main__":
    send_start_message()
    app.run(host="0.0.0.0", port=PORT)
