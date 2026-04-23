import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
DB_PATH: str = os.getenv("DB_PATH", "reserve_table.db")
TZ: str = os.getenv("TZ", "UTC")

# Количество слотов вперёд для отображения при бронировании (16 = 4 часа)
SLOTS_AHEAD: int = int(os.getenv("SLOTS_AHEAD", "16"))

# Антиспам: максимум броней от одного пользователя за календарный день
MAX_BOOKINGS_PER_DAY: int = int(os.getenv("MAX_BOOKINGS_PER_DAY", "2"))

# Администраторы (могут удалять чужие брони). Список user_id через запятую.
_admin_ids_raw: str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: frozenset[int] = frozenset(
    int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip()
)
