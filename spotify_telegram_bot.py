# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot==20.3

from flask import Flask, request
import os
import threading
import datetime
import requests
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

# ====== تنظیمات Environment Variables ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")
PORT = int(os.environ.get("PORT", 5000))

# ====== ساخت اپ Flask ======
app = Flask(__name__)

# ====== متغیر کنترلی برای توقف ارسال ریلیزها ======
stop_flag = False

# ====== Refresh Spotify Token ======
def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    response = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    return response.json().get("access_token")

# ====== گرفتن هنرمندان دنبال‌شده ======
def get_followed_artists(token):
    url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json().get("artists", {}).get("items", [])

# ====== گرفتن ریلیزهای اخیر ======
def get_recent_albums(token, artist_id, months):
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

# ====== ارسال پیام تلگرام ======
def send_telegram(bot, msg, image_url=None, buttons=None):
    if image_url:
        bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=image_url, caption=msg, reply_markup=buttons)
    else:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, reply_markup=buttons)

# ====== ارسال ریلیزها در Thread ======
def send_releases_job(bot, months):
    global stop_flag
    stop_flag = False
    access_token = refresh_access_token(REFRESH_TOKEN)
    artists = get_followed_artists(access_token)
    for artist in artists:
        if stop_flag:
            break
        name = artist['name']
        artist_id = artist['id']
        albums = get_recent_albums(access_token, artist_id, months)
        for album in albums:
            if stop_flag:
                break
            msg = f"🎵 New release by {name}: {album['name']}\nRelease Date: {album['release_date']}\n{album['external_urls']['spotify']}"
            image_url = album['images'][0]['url'] if album.get('images') else None
            send_telegram(bot, msg, image_url=image_url)

# ====== دکمه‌ها ======
def get_month_buttons():
    buttons = [
        [InlineKeyboardButton("1 Month", callback_data="1")],
        [InlineKeyboardButton("3 Months", callback_data="3")],
        [InlineKeyboardButton("6 Months", callback_data="6")],
        [InlineKeyboardButton("12 Months", callback_data="12")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(buttons)

# ====== هندلر CallbackQuery ======
async def button_handler(update: Update, context):
    global stop_flag
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel":
        stop_flag = True
        await query.edit_message_text("⛔ Job cancelled.")
        return

    months = int(data)
    await query.edit_message_text(f"⏳ Fetching releases for the past {months} month(s)...")
    threading.Thread(target=send_releases_job, args=(context.bot, months)).start()

# ====== هندلر استارت ======
async def start(update: Update, context):
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="✅ Bot is ready!",
                                   reply_markup=get_month_buttons())

# ====== Flask Webhook ======
@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header_secret != WEBHOOK_SECRET:
            return "Forbidden", 403

    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    context.application.update_queue.put(update)
    return "OK", 200

@app.route("/")
def index():
    return "Spotify Telegram Bot is running!"

# ====== اجرای ربات ======
if __name__ == "__main__":
    bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    bot_app.add_handler(CommandHandler("start", start))

    bot = bot_app.bot

    # استارت Thread وب سرور Flask
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT)).start()

    print("Bot is running...")
    bot_app.run_polling()
