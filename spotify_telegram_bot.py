import os
import time
import datetime
import shelve
import threading
import requests
from telegram import Bot, Update
from telegram.utils.helpers import escape_markdown
from flask import Flask, request

# ====== تنظیمات =====
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

REQUEST_DELAY = 0.22
CACHE_FILE = "spotify_cache.db"
SENT_ALBUMS_FILE = "sent_albums.db"
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 ساعت

bot = Bot(token=TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== Spotify helper functions =====
def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    resp = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    resp.raise_for_status()
    return resp.json().get("access_token")

def get_all_followed_artists(token):
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
        after = data.get("artists", {}).get("cursors", {}).get("after")
        if not after:
            break
        time.sleep(REQUEST_DELAY)
    return artists

def get_albums_for_artist(token, artist_id):
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
        next_url = data.get("next")
        if not next_url:
            break
        url = next_url
        params = None
        time.sleep(REQUEST_DELAY)
    return albums

def filter_recent(albums, months=1):
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
            a['parsed_date'] = date_obj
            recent.append(a)
    return recent

def cached_get_albums(token, artist_id, months=1):
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
                "external_urls": a.get("external_urls"),
                "images": a.get("images", []),
                "release_date": a.get("release_date"),
                "parsed_date": a.get("parsed_date").isoformat() if isinstance(a.get("parsed_date"), datetime.datetime) else a.get("release_date")
            })
        db[key] = {"ts": now, "recent_albums": minimal}
        return minimal

# ===== Telegram helper =====
def send_album_safe(chat_id, album_id, text, photo_url=None):
    with shelve.open(SENT_ALBUMS_FILE, writeback=True) as sent_db:
        if album_id in sent_db:
            return
        sent_db[album_id] = True
        sent_db.sync()

    safe_text = escape_markdown(text, version=2)
    try:
        if photo_url:
            bot.send_photo(chat_id, photo_url, caption=safe_text, parse_mode="MarkdownV2")
        else:
            bot.send_message(chat_id, safe_text, parse_mode="MarkdownV2")
    except Exception as e:
        print("Failed to send album:", e)

def send_recent_releases(chat_id, months=1):
    token = refresh_access_token(REFRESH_TOKEN)
    artists = get_all_followed_artists(token)
    for artist in artists:
        albums = cached_get_albums(token, artist['id'], months=months)
        for album in albums:
            text = f"*{artist['name']}*\n{album['name']}\n{album['release_date']}"
            photo_url = album.get("images", [{}])[0].get("url")
            send_album_safe(chat_id, album['id'], text, photo_url)
            time.sleep(REQUEST_DELAY)

# ===== Flask webhook =====
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    threading.Thread(target=handle_update, args=(data,)).start()
    return "ok"

def handle_update(update_json):
    # بررسی نوع update
    if "message" in update_json:
        text = update_json["message"]["text"]
        chat_id = update_json["message"]["chat"]["id"]
        if text == "/start":
            bot.send_message(chat_id, "🤖 ربات آماده به کار است.\nیکی از بازه‌های زمانی را انتخاب کنید:")
    elif "callback_query" in update_json:
        chat_id = update_json["callback_query"]["message"]["chat"]["id"]
        data = update_json["callback_query"]["data"]
        if data in ["1","3","6","12"]:
            months = int(data)
            send_recent_releases(chat_id, months=months)

# ===== Run Flask =====
if __name__ == "__main__":
    app.run(port=8080)
