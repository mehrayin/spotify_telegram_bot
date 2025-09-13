

# اضافه کنید به requirements.txt اگر لازم بود:
# pip install requests

import time
import requests
import datetime
import shelve
from typing import List, Dict

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")

# تنظیمات نرخ و کش
REQUEST_DELAY = 0.22  # ثانبه بین درخواست‌ها -> ~4.5 req/sec (ایمن)
CACHE_FILE = "spotify_cache.db"
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 ساعت، بسته به نیاز تغییر بده

def refresh_access_token(refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    resp = requests.post(url, data=data, auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET))
    resp.raise_for_status()
    return resp.json().get("access_token")

def get_all_followed_artists(token) -> List[Dict]:
    artists = []
    url = "https://api.spotify.com/v1/me/following"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"type": "artist", "limit": 50}
    # Spotify uses 'after' cursor param for following
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
        # cursor logic: Spotify returns cursors in 'artists' -> 'cursors' -> 'after'
        cursors = data.get("artists", {}).get("cursors", {})
        after = cursors.get("after")
        if not after:
            break
        # small delay to be polite
        time.sleep(REQUEST_DELAY)
    return artists

def get_albums_for_artist(token, artist_id) -> List[Dict]:
    """Returns all albums/singles for artist (no filtering by date)."""
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
        # check paging
        next_url = data.get("next")
        if not next_url:
            break
        # follow next link (Spotify gives full next URL)
        url = next_url
        params = None
        time.sleep(REQUEST_DELAY)
    return albums

def filter_recent(albums, months=6):
    cutoff = datetime.datetime.now() - datetime.timedelta(days=months*30)
    recent = []
    for a in albums:
        rd = a.get("release_date")
        # release_date may be YYYY or YYYY-MM or YYYY-MM-DD
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

def cached_get_albums(token, artist_id, months=6):
    """Use shelve cache to avoid re-fetching unchanged artists."""
    key = f"artist_{artist_id}"
    now = time.time()
    with shelve.open(CACHE_FILE) as db:
        entry = db.get(key)
        if entry:
            timestamp = entry.get("ts", 0)
            if now - timestamp < CACHE_TTL_SECONDS:
                # return filtered cached albums (already parsed stored)
                return [alb for alb in entry.get("recent_albums", []) if alb]  # shallow copy

        # otherwise fetch fresh
        albums = get_albums_for_artist(token, artist_id)
        recent = filter_recent(albums, months=months)
        # store minimal info to cache (avoid huge binary data)
        minimal = []
        for a in recent:
            minimal.append({
                "id": a.get("id"),
                "name": a.get("name"),
                "external_urls": a.get("external_urls"),
                "images": a.get("images", []),
                "release_date": a.get("release_date"),
                "parsed_date": a.get("parsed_date').isoformat() if isinstance(a.get('parsed_date'), datetime.datetime) else a.get('release_date')
            })
        db[key] = {"ts": now, "recent_albums": minimal}
        return recent

# Example orchestrator: gets all artists then iterates with pacing
def get_all_recent_releases_for_followed(months=6):
    token = refresh_access_token(REFRESH_TOKEN)
    artists = get_all_followed_artists(token)
    print(f"Found {len(artists)} followed artists")
    results = []  # list of tuples (artist_name, album)
    for i, artist in enumerate(artists, start=1):
        artist_id = artist['id']
        artist_name = artist.get('name')
        # throttle
        time.sleep(REQUEST_DELAY)
        try:
            albums = get_albums_for_artist(token, artist_id)
            recent = filter_recent(albums, months=months)
            for album in recent:
                results.append((artist_name, album))
        except requests.HTTPError as e:
            print(f"HTTP error for {artist_name}: {e}")
        except Exception as e:
            print(f"Other error for {artist_name}: {e}")
    return results
