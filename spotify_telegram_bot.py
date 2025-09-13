# نصب کتابخانه‌ها:
# pip install requests python-telegram-bot flask

import os
import time
import requests
import datetime
import shelve
import re
from threading import Thread
from typing import List, Dict
from flask import Flask, request
from telegram import Bot

# ====== تنظیمات ======
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

REQUEST_DELAY = 0.3
CACHE_FILE = "spotify_cache.db"
CACHE_TTL_SECONDS = 60 * 60 * 6
SENT_ALBUMS_FILE = "sent_albums.db"

bot = Bot(token=TELEGRAM_TOKEN)
app = Flask(__name__)

# ====== فانکشن‌های کمکی ======
def escape_markdown(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

# ====== فانکشن‌های اسپاتیفای ======
def refresh_access_token(refresh_token: str) -> str:
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    resp = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    resp.raise_for_status()
    return resp.json().get("access_token")

def get_all_followed_artists(token: str) -> List[Dict]:
    artists = []
    url = "https://api.spotify.com/v1/me/following"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"type": "artist", "limit": 50}
    after = None
    while True:
        if after:
            params["after"] = after
        r = requests.get(url, headers=headers, params=params)
        if r.status_code == 429:
            retry = int(r.headers.get("Retry-After", "1"))
            time.sleep(retry)
            continue
        r.raise_for_status()
        data = r.json()
        chunk = data.get("artists", {}).get("items", [])
        artists.extend(chunk)
        cursors = data.get("artists", {}).get("cursors", {})
        after = cursors.get("after")
        if not after:
            break
        time.sleep(REQUEST_DELAY)
    return artists

def get_albums_for_artist(token: str, artist_id: str) -> List[Dict]:
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"include_groups": "album,single", "limit": 50}
    albums = []
    while True:
        r = requests.get(url, headers=headers, params=params)
        if r.status_code == 429:
            retry = int(r.headers.get("Retry-After", "1"))
            time.sleep(retry)
            continue
        r.raise_for_status()
        data = r.json()
        albums.extend(data.get("items", []))
        if not data.get("next"):
            break
        url = data.get("next")
        params = None
        time.sleep(REQUEST_DELAY)
    return albums

def filter_recent(albums: List[Dict], months=1) -> List[Dict]:
    cutoff = datetime.datetime.now() - datetime.timedelta(days=months*30)
    recent = []
    for a in albums:
        rd = a.get("release_date")
        try:
            if len(rd) == 4:
                date_obj = datetime.datetime.strptime(rd, "%Y")
            elif len(rd) == 7:
                date_obj = datetime.datetime.strptime(rd, "%Y-%m")
            else:
                date_obj = datetime.datetime.strptime(rd, "%Y-%m-%d")
        except Exception:
            continue
        if date_obj > cutoff:
            a["parsed_date"] = date_obj
            recent.append(a)
    return recent

def cached_get_albums(token: str, artist_id: str, months=1) -> List[Dict]:
    key = f"artist_{artist_id}"
    now = time.time()
    with shelve.open(CACHE_FILE) as db:
        entry = db.get(key)
        if entry and now - entry.get("ts", 0) < CACHE_TTL_SECONDS:
            return entry.get("recent_albums", [])
        albums = get_albums_for_artist(token, artist_id)
        recent = filter_recent(albums, months=months)
        minimal = []
        for a in recent:
            minimal.append({
                "id": a.get("id"),
                "name": a.get("name"),
                "external_url": a.get("external_urls", {}).get("spotify"),
                "image": a.get("images", [{}])[0].get("url") if a.get("images") else None,
                "release_date": a.get("release_date"),
                "parsed_date": a.get("parsed_date").isoformat() if isinstance(a.get("parsed_date"), datetime.datetime) else a.get("release_date")
            })
        db[key] = {"ts": now, "recent_albums": minimal}
        return minimal

# ====== ارسال ریلیزهای جدید بدون تکرار ======
def send_recent_releases_to_telegram(chat_id, months=1):
    try:
        bot.send_message(chat_id, "⏳ در حال بررسی ریلیزهای جدید...")
        token = refresh_access_token(REFRESH_TOKEN)
        artists = get_all_followed_artists(token)

        results = []
        with shelve.open(SENT_ALBUMS_FILE) as sent_db:
            for artist in artists:
                artist_id = artist["id"]
                artist_name = artist.get("name")
                time.sleep(REQUEST_DELAY)
                try:
                    recent_albums = cached_get_albums(token, artist_id, months=months)
                    for album in recent_albums:
                        album_id = album.get("id")
                        if not album_id or album_id in sent_db:
                            continue
                        sent_db[album_id] = True  # علامت گذاری

                        text = escape_markdown(f"🎵 {artist_name} - {album['name']}\n📅 {album['release_date']}\n🔗 {album.get('external_url')}")
                        try:
                            if album.get("image"):
                                bot.send_photo(chat_id, album["image"], caption=text)
                            else:
                                bot.send_message(chat_id, text)
                        except Exception as e:
                            print("Failed to send album:", e)
                except Exception as e:
                    print(f"Failed for {artist_name}: {e}")

    except Exception as e:
        print("Error in send_recent_releases_to_telegram:", e)

# ====== وب‌هوک ======
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if "callback_query" in update:
        data = update["callback_query"]["data"]
        chat_id = update["callback_query"]["message"]["chat"]["id"]
        bot.answer_callback_query(update["callback_query"]["id"], text="⏳ در حال جمع‌آوری ریلیزها...")
        Thread(target=send_recent_releases_to_telegram, args=(chat_id, int(data))).start()
    return "ok"

# ====== اجرای اپ ======
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
