"""Все операции с базой данных (aiosqlite)."""
from __future__ import annotations

import aiosqlite

import config

DB = config.DB_PATH


async def init_db() -> None:
    """Создать таблицы при первом запуске."""
    async with aiosqlite.connect(DB) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS subscribers (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT,
                first_name    TEXT,
                subscribed_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                player_name TEXT NOT NULL,
                slot_start  TEXT NOT NULL,
                slot_end    TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                cancelled   INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES subscribers(user_id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_slot
                ON bookings(slot_start) WHERE cancelled = 0;

            CREATE TABLE IF NOT EXISTS games (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                player_name TEXT NOT NULL,
                started_at  TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at    TEXT,
                FOREIGN KEY (user_id) REFERENCES subscribers(user_id)
            );
        """)
        await db.commit()


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------

async def upsert_subscriber(user_id: int, username: str | None, first_name: str | None) -> None:
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            """
            INSERT INTO subscribers(user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name
            """,
            (user_id, username, first_name),
        )
        await db.commit()


async def get_all_subscribers() -> list[dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, username, first_name FROM subscribers") as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def remove_subscriber(user_id: int) -> None:
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM subscribers WHERE user_id = ?", (user_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------

async def get_booked_slots_today(date_prefix: str) -> list[str]:
    """Вернуть список slot_start для активных броней на указанную дату."""
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT slot_start FROM bookings WHERE cancelled = 0 AND slot_start LIKE ?",
            (f"{date_prefix}%",),
        ) as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows]


async def create_booking(user_id: int, player_name: str, slot_start: str, slot_end: str) -> int:
    """
    Создать бронирование. Поднимает aiosqlite.IntegrityError если слот уже занят.
    Возвращает id новой строки.
    """
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "INSERT INTO bookings(user_id, player_name, slot_start, slot_end) VALUES (?,?,?,?)",
            (user_id, player_name, slot_start, slot_end),
        )
        await db.commit()
        return cur.lastrowid


async def get_bookings_for_date(date_prefix: str) -> list[dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, user_id, player_name, slot_start, slot_end
            FROM bookings
            WHERE cancelled = 0 AND slot_start LIKE ?
            ORDER BY slot_start
            """,
            (f"{date_prefix}%",),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def count_user_bookings_for_date(user_id: int, date_prefix: str) -> int:
    """Сколько активных броней у пользователя на указанную дату."""
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            """
            SELECT COUNT(*) FROM bookings
            WHERE cancelled = 0 AND user_id = ? AND slot_start LIKE ?
            """,
            (user_id, f"{date_prefix}%"),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def get_last_booking_user_id() -> int | None:
    """user_id самой недавней активной брони (по created_at)."""
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            """
            SELECT user_id FROM bookings
            WHERE cancelled = 0
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else None


async def cancel_booking_by_id(booking_id: int, user_id: int | None = None) -> dict | None:
    """
    Пометить бронь cancelled=1. Возвращает данные брони (для уведомления),
    либо None если бронь не найдена / уже отменена / не принадлежит user_id.
    Если user_id указан, отмена допускается только для собственной брони.
    """
    if user_id is None:
        where = "id = ? AND cancelled = 0"
        params: tuple = (booking_id,)
    else:
        where = "id = ? AND cancelled = 0 AND user_id = ?"
        params = (booking_id, user_id)

    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT id, user_id, player_name, slot_start FROM bookings WHERE {where}",
            params,
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        await db.execute("UPDATE bookings SET cancelled = 1 WHERE id = ?", (booking_id,))
        await db.commit()
    return dict(row)


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------

async def get_active_game() -> dict | None:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, user_id, player_name, started_at FROM games WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def start_game(user_id: int, player_name: str) -> int:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "INSERT INTO games(user_id, player_name) VALUES (?, ?)",
            (user_id, player_name),
        )
        await db.commit()
        return cur.lastrowid


async def end_game(game_id: int) -> None:
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE games SET ended_at = datetime('now') WHERE id = ?",
            (game_id,),
        )
        await db.commit()
