import html
import math
from datetime import datetime, timedelta

import pytz

import config

SLOT_MINUTES = 15


def local_now() -> datetime:
    """Текущее время в локальном часовом поясе."""
    tz = pytz.timezone(config.TZ)
    return datetime.now(tz)


def round_up_to_slot(dt: datetime) -> datetime:
    """Округлить время вверх до ближайшего 15-минутного слота."""
    total_minutes = dt.hour * 60 + dt.minute
    if dt.second > 0 or dt.microsecond > 0:
        total_minutes += 1  # любая неполная минута → следующий слот
    rounded = math.ceil(total_minutes / SLOT_MINUTES) * SLOT_MINUTES
    result = dt.replace(
        hour=rounded // 60 % 24,
        minute=rounded % 60,
        second=0,
        microsecond=0,
    )
    # Если округление перешло на следующий день
    if rounded >= 24 * 60:
        result = (dt + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return result


def next_slots(n: int = None) -> list[datetime]:
    """Список ближайших N доступных временных слотов."""
    if n is None:
        n = config.SLOTS_AHEAD
    start = round_up_to_slot(local_now())
    return [start + timedelta(minutes=SLOT_MINUTES * i) for i in range(n)]


def fmt_slot(dt: datetime) -> str:
    """Форматировать слот для отображения: 'Пн 13 мар · 15:30'."""
    return dt.strftime("%a %d %b · %H:%M")


def fmt_time(dt: datetime) -> str:
    """Только время: '15:30'."""
    return dt.strftime("%H:%M")


def slot_to_db(dt: datetime) -> str:
    """Конвертировать datetime в строку для хранения в БД (UTC ISO-8601)."""
    if dt.tzinfo is not None:
        utc_dt = dt.astimezone(pytz.utc)
    else:
        utc_dt = dt
    return utc_dt.strftime("%Y-%m-%d %H:%M:%S")


def display_name(user) -> str:
    """Отображаемое имя пользователя Telegram: first_name → @username → id."""
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return str(user.id)


def mention_html(user_id: int, name: str) -> str:
    """HTML-меншн: кликабельное имя, открывающее профиль пользователя в Telegram."""
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


def db_to_local(s: str) -> datetime:
    """Конвертировать строку из БД в локальный datetime."""
    tz = pytz.timezone(config.TZ)
    utc_dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.utc)
    return utc_dt.astimezone(tz)
