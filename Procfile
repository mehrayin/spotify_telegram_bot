# web: gunicorn spotify_telegram_bot:app --bind 0.0.0.0:$PORT
web: gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:$PORT spotify_telegram_bot:app


