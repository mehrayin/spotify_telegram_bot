# نصب کتابخانه‌ها:
# pip install flask requests python-telegram-bot

from flask import Flask, request
import telegram
import requests
import shelve
from telegram.helpers import escape_markdown

app = Flask(__name__)

TELEGRAM_TOKEN = "توکن_ربات_تو"
bot = telegram.Bot(token=TELEGRAM_TOKEN)

DB_FILE = "sent_albums.db"

# ==== مدیریت آلبوم‌های فرستاده شده برای چند کاربر ====
def already_sent(user_id, album_id):
    with shelve.open(DB_FILE) as db:
        sent = db.get(str(user_id), set())
        return album_id in sent

def mark_sent(user_id, album_id):
    with shelve.open(DB_FILE, writeback=True) as db:
        sent = db.get(str(user_id), set())
        sent.add(album_id)
        db[str(user_id)] = sent

# ==== ارسال آلبوم به تلگرام ====
def send_album_to_telegram(chat_id, album):
    album_id = album['id']
    artist_name = album['artist_name']
    album_name = album.get('name', 'بدون نام')
    photo_url = album.get('cover', None)

    if already_sent(chat_id, album_id):
        return  # قبلاً فرستاده شده

    text = f"*{escape_markdown(album_name, version=2)}* - {escape_markdown(artist_name, version=2)}"

    try:
        bot.send_photo(chat_id=chat_id, photo=photo_url, caption=text, parse_mode="MarkdownV2")
        mark_sent(chat_id, album_id)
    except Exception as e:
        print(f"Failed to send album: {e}")

# ==== هندل دکمه‌ها و دریافت ریلیزها ====
def get_releases(period):
    """
    این تابع باید بر اساس API اسپاتیفای یا دیزر ریلیزها را برگرداند.
    هر آلبوم باید dict با کلیدهای:
        'id' (شناسه یکتا)
        'name' (نام آلبوم)
        'artist_name' (نام هنرمند)
        'cover' (لینک عکس)
    """
    # نمونه ساختگی برای تست
    return [
        {'id': f'{period}_1', 'name': 'Test Album 1', 'artist_name': 'Artist A', 'cover': 'https://via.placeholder.com/300'},
        {'id': f'{period}_2', 'name': 'Test Album 2', 'artist_name': 'Artist B', 'cover': 'https://via.placeholder.com/300'}
    ]

def handle_button_click(update):
    query = update.get('callback_query')
    if not query:
        return
    chat_id = query['from']['id']
    data = query['data']
    releases = get_releases(period=data)
    for album in releases:
        send_album_to_telegram(chat_id, album)

# ==== وبهوک ====
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    print("==== WEBHOOK HIT ====")
    print("Payload received:", update)
    handle_button_click(update)
    return "OK"

# ==== اجرای لوکال برای تست ====
if __name__ == '__main__':
    app.run(port=5000)
