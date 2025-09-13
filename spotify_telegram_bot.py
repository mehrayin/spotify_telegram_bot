# نصب کتابخانه‌ها:
# pip install requests

import os
import time
import requests
import datetime
import shelve
from typing import List, Dict

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

# تنظیمات نرخ و کش
REQUEST_DELAY = 0.3  # فاصله بین درخواست‌ها -> ~3 req/sec (ایمن‌تر)
CACHE_FILE = "spotify_cache.db"
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 ساعت

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
            print(f"Rate limited on follow -> sleep {retry}s")
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
            print(f"Rate limited on albums for {artist_id} -> sleep {retry}s")
            time.sleep(retry)
            continue
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        albums.extend(items)
        next_url = data.get("next")
        if not next_url:
            break
        url = next_url
        params = None
        time.sleep(REQUEST_DELAY)
    return albums

def filter_recent(albums: List[Dict], months=6) -> List[Dict]:
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

def cached_get_albums(token: str, artist_id: str, months=6) -> List[Dict]:
    key = f"artist_{artist_id}"
    now = time.time()
    with shelve.open(CACHE_FILE) as db:
        entry = db.get(key)
        if entry:
            timestamp = entry.get("ts", 0)
            if now - timestamp < CACHE_TTL_SECONDS:
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
                "parsed_date": a.get("parsed_date").isoformat() if isinstance(a.get("parsed_date"), datetime.datetime) else a.get("release_date"),
            })
        db[key] = {"ts": now, "recent_albums": minimal}
        return minimal

def get_all_recent_releases_for_followed(months=6) -> List[Dict]:
    token = refresh_access_token(REFRESH_TOKEN)
    artists = get_all_followed_artists(token)
    print(f"Found {len(artists)} followed artists")

    results = []
    for i, artist in enumerate(artists, start=1):
        artist_id = artist["id"]
        artist_name = artist.get("name")
        time.sleep(REQUEST_DELAY)
        try:
            recent_albums = cached_get_albums(token, artist_id, months=months)
            for album in recent_albums:
                results.append({
                    "artist": artist_name,
                    "album": album["name"],
                    "date": album["release_date"],
                    "url": album["external_url"],
                    "image": album["image"]
                })
        except requests.HTTPError as e:
            print(f"HTTP error for {artist_name}: {e}")
        except Exception as e:
            print(f"Other error for {artist_name}: {e}")
    return results

# تست سریع
if __name__ == "__main__":
    releases = get_all_recent_releases_for_followed(months=1)
    for r in releases[:10]:
        print(r)
