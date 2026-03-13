import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
DB_PATH: str = os.getenv("DB_PATH", "reserve_table.db")
TZ: str = os.getenv("TZ", "UTC")

# Количество слотов вперёд для отображения при бронировании (16 = 4 часа)
SLOTS_AHEAD: int = int(os.getenv("SLOTS_AHEAD", "16"))
