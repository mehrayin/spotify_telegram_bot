import os
import asyncio
import datetime
import json
from aiohttp import ClientSession
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import nest_asyncio
nest_asyncio.apply()

# ====== تنظیمات =====
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

CACHE_FILE = "spotify_cache.json"
SENT_ALBUMS_FILE = "sent_albums.json"
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 ساعت
CHUNK_SIZE = 20  # تعداد پیام در هر بخش برای Telegram

# ====== Utility =====
def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===== Spotify Async =====
async def refresh_access_token(session):
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": REFRESH_TOKEN}
    async with session.post(url, data=data, auth=aiohttp.BasicAuth(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)) as resp:
        resp.raise_for_status()
        res = await resp.json()
        return res.get("access_token")

async def get_all_followed_artists(session, token):
    artists = []
    url = "https://api.spotify.com/v1/me/following"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"type": "artist", "limit": 50}
    after = None
    while True:
        if after:
            params["after"] = after
        async with session.get(url, headers=headers, params=params) as r:
            if r.status == 429:
                retry = int(r.headers.get("Retry-After", "1"))
                await asyncio.sleep(retry)
                continue
            r.raise_for_status()
            data = await r.json()
            chunk = data.get("artists", {}).get("items", [])
            artists.extend(chunk)
            after = data.get("artists", {}).get("cursors", {}).get("after")
            if not after:
                break
            await asyncio.sleep(0.2)
    return artists

async def get_albums_for_artist(session, token, artist_id):
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"include_groups": "album,single", "limit": 50}
    albums = []
    while True:
        async with session.get(url, headers=headers, params=params) as r:
            if r.status == 429:
                retry = int(r.headers.get("Retry-After", "1"))
                await asyncio.sleep(retry)
                continue
            r.raise_for_status()
            data = await r.json()
            albums.extend(data.get("items", []))
            next_url = data.get("next")
            if not next_url:
                break
            url = next_url
            params = None
            await asyncio.sleep(0.2)
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

async def cached_get_albums(session, token, artist_id, months=1):
    cache = load_json(CACHE_FILE)
    key = f"artist_{artist_id}"
    now = asyncio.get_event_loop().time()
    if key in cache and now - cache[key].get("ts", 0) < CACHE_TTL_SECONDS:
        return cache[key].get("recent_albums", [])
    albums = await get_albums_for_artist(session, token, artist_id)
    recent = filter_recent(albums, months=months)
    minimal = []
    for a in recent:
        minimal.append({
            "id": a.get("id"),
            "name": a.get("name"),
            "artist": a.get("artists", [{}])[0].get("name"),
            "release_date": a.get("release_date")
        })
    cache[key] = {"ts": now, "recent_albums": minimal}
    save_json(CACHE_FILE, cache)
    return minimal

# ===== Telegram Async =====
async def send_messages_in_chunks(bot, chat_id, messages, chunk_size=CHUNK_SIZE):
    for i in range(0, len(messages), chunk_size):
        chunk = messages[i:i+chunk_size]
        full_message = "\n".join(chunk)
        safe_text = escape_markdown(full_message, version=2)
        await bot.send_message(chat_id=chat_id, text=safe_text, parse_mode="MarkdownV2")
        await asyncio.sleep(0.2)

async def send_recent_releases(bot, chat_id, months=1):
    sent_albums = load_json(SENT_ALBUMS_FILE)
    messages = []

    async with ClientSession() as session:
        token = await refresh_access_token(session)
        artists = await get_all_followed_artists(session, token)
        for artist in artists:
            albums = await cached_get_albums(session, token, artist['id'], months=months)
            for album in albums:
                album_id = album['id']
                if album_id in sent_albums:
                    continue
                messages.append(f"{album['artist']} - {album['name']} ({album['release_date']})")
                sent_albums[album_id] = True

    save_json(SENT_ALBUMS_FILE, sent_albums)

    if messages:
        await send_messages_in_chunks(bot, chat_id, messages)
    else:
        await bot.send_message(chat_id, "هیچ ریلیز جدیدی در یک ماه گذشته وجود ندارد.")

# ===== Handlers =====
async def start(update, context):
    keyboard = [[InlineKeyboardButton("یک ماه گذشته", callback_data="1")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🤖 ربات آماده به کار است.\nبرای مشاهده ریلیزهای یک ماه گذشته روی دکمه زیر بزنید:",
        reply_markup=reply_markup
    )

async def button(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "1":
        asyncio.create_task(send_recent_releases(context.bot, query.message.chat.id, months=1))

# ====== Run Bot =====
app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))

if __name__ == "__main__":
    # Railway: Port environment variable
    import uvicorn
    uvicorn.run("this_file_name:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=True)
