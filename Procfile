# web: gunicorn spotify_telegram_bot:app --bind 0.0.0.0:$PORT
# web: gunicorn -w 4 -b 0.0.0.0:$PORT spotify_telegram_bot:app
web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT spotify_telegram_bot:app




