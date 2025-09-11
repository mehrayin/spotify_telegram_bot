def send_releases_job():
    global sent_albums
    try:
        access_token = refresh_access_token(REFRESH_TOKEN)
        if not access_token:
            print("Access token not available")
            return
        artists = get_followed_artists(access_token)
        for artist in artists:
            name = artist['name']
            artist_id = artist['id']
            albums = get_recent_albums(access_token, artist_id)
            for album in albums:
                album_id = album['id']
                if album_id in sent_albums:
                    continue  # قبلاً ارسال شده
                album_name = album['name']
                release_date = album.get('release_date', 'Unknown')
                album_url = album['external_urls']['spotify']
                # گرفتن عکس آلبوم (اولین تصویر)
                album_images = album.get('images', [])
                album_image_url = album_images[0]['url'] if album_images else None

                # ساخت پیام
                msg = f"🎵 New release by {name}:\n"
                msg += f"Album: {album_name}\n"
                msg += f"Release Date: {release_date}\n"
                msg += f"Link: {album_url}"

                # ارسال پیام با عکس اگر موجود بود
                if album_image_url:
                    try:
                        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
                        bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=album_image_url, caption=msg)
                    except Exception as e:
                        print("Failed to send album photo/message:", e)
                        send_telegram(msg)  # fallback بدون عکس
                else:
                    send_telegram(msg)

                sent_albums.add(album_id)
    except Exception as e:
        print("Error in send_releases_job:", e)
