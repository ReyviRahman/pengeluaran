import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN harus diatur di file .env")

if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL harus diatur di file .env")
