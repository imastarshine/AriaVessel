import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
ARIA2_SECRET = os.getenv("ARIA2_SECRET")
YADISK_TOKEN = os.getenv("YADISK_TOKEN")
YADISK_URL_PROXY = os.getenv("YADISK_URL_PROXY")
TELEGRAM_BOT_SOCKS5_PROXY = os.getenv("TELEGRAM_BOT_SOCKS5_PROXY")
