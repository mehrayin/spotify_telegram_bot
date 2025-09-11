# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot==20.3 pytz

from flask import Flask, request
import os, datetime, requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import threading, time

# ====== تنظیمات Environment Variables ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
RAILWAY_URL = "web-production-1ea15.up.railway.app"

# ====== چک Environment Variables ======
for var in ["SPOTIFY_CLIENT_ID","SPOTIFY_CLIENT_SECRET","TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID","REFRESH_TOKEN"]:
    if not os.environ.get(var):
        print(f"ERROR: {var} not set!")

# ====== Flask app ======
app = Flask(__name__)

# ====== ذخیره ریلیزهای فرستاده شده ======
sent_albums = set()
current_interval_days = 30  # پیش فرض یک ماهه
send_releases_flag = False   # برای دکمه لغو

# ====== Spotify API ======
def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    response = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    return response.json().get("access_token")

def get_followed_artists(token):
    url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers)
    return res.json().get("artists", {}).get("items", [])

def get_recent_albums(token, artist_id, months=6):
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"include_groups":"album,single","limit":50}
    res = requests.get(url, headers=headers, params=params)
    albums = res.json().get("items", [])
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

# ====== ارسال پیام تلگرام ======
async def send_album_message(bot, album, artist_name):
    msg = f"🎵 New release by {artist_name}: {album['name']}\nRelease date: {album['release_date']}\n{album['external_urls']['spotify']}"
    image_url = album['images'][0]['url'] if album['images'] else None
    if image_url:
        await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=image_url, caption=msg)
    else:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

# ====== Thread چک ریلیز ======
def release_checker():
    global sent_albums, current_interval_days, send_releases_flag
    while True:
        if send_releases_flag:
            try:
                token = refresh_access_token(REFRESH_TOKEN)
                artists = get_followed_artists(token)
                for artist in artists:
                    albums = get_recent_albums(token, artist['id'], months=current_interval_days//30)
                    for album in albums:
                        key = f"{artist['id']}_{album['id']}"
                        if key not in sent_albums:
                            sent_albums.add(key)
                            import asyncio
                            asyncio.run(send_album_message(bot.application.bot, album, artist['name']))
                time.sleep(300)  # هر ۵ دقیقه
            except Exception as e:
                print("Error in release_checker:", e)
                time.sleep(60)
        else:
            time.sleep(2)

# ====== Telegram Bot setup ======
bot = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# ====== دکمه‌ها ======
def get_keyboard():
    keyboard = [
        [InlineKeyboardButton("یک ماه گذشته", callback_data="30"),
         InlineKeyboardButton("3 ماه گذشته", callback_data="90")],
        [InlineKeyboardButton("6 ماه گذشته", callback_data="180"),
         InlineKeyboardButton("12 ماه گذشته", callback_data="360")],
        [InlineKeyboardButton("لغو", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ====== هندلرها ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global send_releases_flag
    send_releases_flag = True
    await update.message.reply_text("✅ Bot started successfully! Choose interval:", reply_markup=get_keyboard())

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_interval_days, send_releases_flag
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        send_releases_flag = False
        await query.edit_message_text("❌ Sending cancelled.")
    else:
        current_interval_days = int(query.data)
        send_releases_flag = True
        await query.edit_message_text(f"⏱ Interval set to last {current_interval_days} days. Checking releases...")

async def help_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start to begin and select interval.")

bot.add_handler(CommandHandler("start", start))
bot.add_handler(CallbackQueryHandler(button))
bot.add_handler(CommandHandler("help", help_msg))

# ====== Flask webhook ======
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot.application.bot)
    bot.application.update_queue.put_nowait(update)
    return "OK"

# ====== اجرای Thread ======
threading.Thread(target=release_checker, daemon=True).start()

# ====== اجرای Flask ======
if __name__ == "__main__":
    import asyncio
    # ست کردن Webhook خودکار
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url=https://{RAILWAY_URL}/webhook"
    try:
        requests.get(url)
    except:
        pass
    print("Webhook set:", url)
    # اجرای bot
    asyncio.run(bot.run_webhook(listen="0.0.0.0", port=int(os.environ.get("PORT", 8080)), url_path="webhook", webhook_url=f"https://{RAILWAY_URL}/webhook"))
