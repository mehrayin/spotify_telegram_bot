# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot

from flask import Flask, request
import requests
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import datetime
import os

# ====== تنظیمات از Environment Variables ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")

# بررسی متغیرهای محیطی
required_envs = [
    ("SPOTIFY_CLIENT_ID", SPOTIFY_CLIENT_ID),
    ("SPOTIFY_CLIENT_SECRET", SPOTIFY_CLIENT_SECRET),
    ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
    ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
    ("REFRESH_TOKEN", REFRESH_TOKEN)
]

for name, val in required_envs:
    if not val:
        raise ValueError(f"Environment variable {name} is not set!")

app = Flask(__name__)
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# ====== دریافت Access Token با Refresh Token ======
def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    response = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    
    if response.status_code != 200:
        print("❌ Spotify token refresh failed:", response.status_code, response.text)
        return None
    
    try:
        res_json = response.json()
    except Exception as e:
        print("❌ Failed to parse JSON from Spotify:", e, response.text)
        return None

    return res_json.get("access_token")

# ====== گرفتن هنرمندان دنبال‌شده ======
def get_followed_artists(token):
    url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print("❌ Failed to get followed artists:", response.status_code, response.text)
        return []
    
    try:
        data = response.json()
    except Exception as e:
        print("❌ Failed to parse JSON for followed artists:", e, response.text)
        return []

    return data.get("artists", {}).get("items", [])

# ====== گرفتن ریلیزهای جدید ======
def get_recent_albums(token, artist_id, months=6):
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"include_groups": "album,single", "limit": 50}
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"❌ Failed to get albums for artist {artist_id}:", response.status_code, response.text)
        return []

    try:
        albums = response.json().get("items", [])
    except Exception as e:
        print(f"❌ Failed to parse JSON albums for artist {artist_id}:", e, response.text)
        return []

    cutoff = datetime.datetime.now() - datetime.timedelta(days=months*30)
    recent = []
    for a in albums:
        try:
            date_obj = datetime.datetime.strptime(a['release_date'], "%Y-%m-%d")
        except:
            continue
        if date_obj > cutoff:
            a['parsed_date'] = date_obj
            recent.append(a)
    return recent

# ====== ارسال پیام به تلگرام ======
def send_album_to_telegram(album, artist_name):
    text = f"🎵 *{artist_name}* - {album['name']}\n" \
           f"📅 {album['parsed_date'].strftime('%Y-%m-%d')}\n" \
           f"[لینک اسپاتیفای]({album['external_urls']['spotify']})"

    photo_url = album['images'][0]['url'] if album.get('images') else None
    try:
        if photo_url:
            bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=photo_url, caption=text, parse_mode="Markdown")
        else:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        print("❌ Failed to send album:", e)

# ====== هندلر برای دکمه‌ها ======
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
        query.edit_message_text(
            "✅ عملیات لغو شد.\nدوباره یکی از بازه‌های زمانی رو انتخاب کن:",
            reply_markup=reply_markup
        )
        return

    try:
        months = int(data)
        token = refresh_access_token(REFRESH_TOKEN)
        if not token:
            query.edit_message_text("❌ دریافت توکن اسپاتیفای موفقیت‌آمیز نبود.")
            return

        artists = get_followed_artists(token)
        if not artists:
            query.edit_message_text("هیچ هنرمندی دنبال نشده است.")
            return

        query.edit_message_text(f"⏳ در حال گرفتن ریلیزهای {months} ماه گذشته...")

        for artist in artists:
            albums = get_recent_albums(token, artist['id'], months=months)
            for album in albums:
                send_album_to_telegram(album, artist['name'])

        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ نمایش ریلیزها تمام شد.")
    except Exception as e:
        query.edit_message_text(f"❌ خطا: {e}")

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
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ Bot started successfully!")
    except Exception as e:
        print("❌ Failed to send start message:", e)
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)
