# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot>=20 uvicorn gunicorn

import os
import datetime
import requests
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# ====== Environment Variables ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change_this_to_a_random_value")

# ====== Flask App ======
app = Flask(__name__)

# ====== Telegram Bot Async ======
bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# ====== Spotify Helpers ======
def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    response = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    res_json = response.json()
    return res_json.get("access_token")

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
        except:
            continue
        if date_obj > cutoff:
            a['parsed_date'] = date_obj
            recent.append(a)
    return recent

# ====== Telegram Helpers ======
async def send_album_to_telegram(album, artist_name):
    text = f"🎵 *{artist_name}* - {album['name']}\n" \
           f"📅 {album['parsed_date'].strftime('%Y-%m-%d')}\n" \
           f"[لینک اسپاتیفای]({album['external_urls']['spotify']})"
    photo_url = album['images'][0]['url'] if album.get('images') else None
    try:
        if photo_url:
            await bot_app.bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=photo_url, caption=text, parse_mode="Markdown")
        else:
            await bot_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        print("Failed to send album:", e)

# ====== Handlers ======
async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await query.edit_message_text(
            "✅ عملیات لغو شد.\nدوباره یکی از بازه‌های زمانی رو انتخاب کن:",
            reply_markup=reply_markup
        )
        return

    try:
        months = int(data)
        token = refresh_access_token(REFRESH_TOKEN)
        artists = get_followed_artists(token)
        if not artists:
            await query.edit_message_text("هیچ هنرمندی دنبال نشده است.")
            return

        await query.edit_message_text(f"⏳ در حال گرفتن ریلیزهای {months} ماه گذشته...")

        for artist in artists:
            albums = get_recent_albums(token, artist['id'], months=months)
            for album in albums:
                await send_album_to_telegram(album, artist['name'])

        await bot_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ نمایش ریلیزها تمام شد.")
    except Exception as e:
        await query.edit_message_text(f"❌ خطا: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("یک ماه گذشته", callback_data="1")],
        [InlineKeyboardButton("۳ ماه گذشته", callback_data="3")],
        [InlineKeyboardButton("۶ ماه گذشته", callback_data="6")],
        [InlineKeyboardButton("۱۲ ماه گذشته", callback_data="12")],
        [InlineKeyboardButton("❌ لغو", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 ربات آماده به کار است.\nیکی از بازه‌های زمانی را انتخاب کنید:",
        reply_markup=reply_markup
    )

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(handle_button_click))

# ====== Flask Webhook ======
@app.route("/webhook", methods=["POST"])
async def telegram_webhook():
    if WEBHOOK_SECRET:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header_secret != WEBHOOK_SECRET:
            return "Forbidden", 403
    data = request.get_json(force=True)
    update = Update.de_json(data, bot_app.bot)
    await bot_app.update_queue.put(update)
    return "OK"

# ====== Main ======
if __name__ == "__main__":
    import asyncio
    print("🚀 Bot started successfully!")
    PORT = int(os.environ.get("PORT", 5000))
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    asyncio.run(serve(app, config))
