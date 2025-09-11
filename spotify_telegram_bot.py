# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot==20.5 pytz

from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
import requests
import threading
import datetime
import os
import pytz
import time

# ====== Environment Variables ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")
PORT = int(os.environ.get("PORT", 5000))

# ====== Flask App ======
app = Flask(__name__)

# ====== Global ======
current_job = None
job_lock = threading.Lock()
selected_months = 1  # پیشفرض 1 ماه

# ====== Spotify Functions ======
def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    response = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    return response.json().get("access_token")

def get_followed_artists(token):
    url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    return resp.json().get("artists", {}).get("items", [])

def get_recent_albums(token, artist_id, months=6):
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"include_groups": "album,single", "limit": 50}
    resp = requests.get(url, headers=headers, params=params)
    albums = resp.json().get("items", [])
    cutoff = datetime.datetime.now(pytz.UTC) - datetime.timedelta(days=months*30)
    recent = []
    for a in albums:
        try:
            date_obj = datetime.datetime.strptime(a['release_date'], "%Y-%m-%d").replace(tzinfo=pytz.UTC)
        except:
            continue
        if date_obj > cutoff:
            recent.append(a)
    return recent

# ====== Telegram Functions ======
async def send_album_message(context: ContextTypes.DEFAULT_TYPE, artist_name, album):
    keyboard = [
        [InlineKeyboardButton("Spotify Link", url=album['external_urls']['spotify'])]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"🎵 {artist_name} - {album['name']}\n📅 Release: {album['release_date']}"
    if album['images']:
        await context.bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=album['images'][0]['url'], caption=msg, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("1 ماه گذشته", callback_data="1"),
         InlineKeyboardButton("3 ماه گذشته", callback_data="3")],
        [InlineKeyboardButton("6 ماه گذشته", callback_data="6"),
         InlineKeyboardButton("12 ماه گذشته", callback_data="12")],
        [InlineKeyboardButton("لغو", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("✅ ربات آماده است! بازه زمانی را انتخاب کنید:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global selected_months, current_job
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        with job_lock:
            current_job = None
        await query.edit_message_text("🛑 ارسال ریلیزها لغو شد!")
    else:
        selected_months = int(query.data)
        await query.edit_message_text(f"⏱ بازه انتخاب شد: {selected_months} ماه\nشروع ارسال ریلیزها...")
        threading.Thread(target=send_releases_job, args=(context.application,), daemon=True).start()

# ====== Job Function ======
def send_releases_job(application):
    global current_job
    with job_lock:
        if current_job is not None:
            return  # job قبلی هنوز فعال است
        current_job = True
    access_token = refresh_access_token(REFRESH_TOKEN)
    artists = get_followed_artists(access_token)
    for artist in artists:
        name = artist['name']
        albums = get_recent_albums(access_token, artist['id'], months=selected_months)
        for album in albums:
            # ارسال هر آلبوم
            application.create_task(send_album_message(application, name, album))
            time.sleep(0.3)  # فاصله کوتاه بین پیام‌ها
    with job_lock:
        current_job = None

# ====== Flask Routes ======
@app.route("/")
def index():
    return "Spotify Telegram Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return "Forbidden", 403
    data = request.get_json(force=True)
    app.bot.update_queue.put(data)
    return "OK", 200

# ====== Main ======
if __name__ == "__main__":
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    # ذخیره reference bot برای Flask
    app.bot = application.bot
    # راه‌اندازی webhook (در Railway این مسیر باید روی /webhook تنظیم شود)
    application.run_polling()
    # برای deployment روی Railway می‌توانید از run_polling() به run_webhook() با URL مناسب استفاده کنید
