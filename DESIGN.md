# Дизайн: Telegram-бот для бронирования теннисного стола

## Архитектура

```
reserve_table/
├── bot.py                  # Точка входа, регистрация всех хэндлеров
├── config.py               # Настройки из .env
├── database.py             # Всё взаимодействие с SQLite (aiosqlite)
├── keyboards.py            # Фабрики клавиатур InlineKeyboard / ReplyKeyboard
├── notifications.py        # Рассылка уведомлений всем подписчикам
├── utils.py                # Округление времени, форматирование слотов
├── handlers/
│   ├── __init__.py
│   ├── start.py            # /start — подписка, главное меню
│   ├── booking.py          # ConversationHandler для бронирования
│   ├── game.py             # "Начать игру" / "Закончить игру"
│   └── schedule.py         # /schedule — расписание на сегодня
├── .env.example
├── requirements.txt
├── README.md
└── DESIGN.md
```

## База данных

### Таблица `subscribers`
Все пользователи, написавшие `/start`. Используется для рассылки уведомлений.

```sql
CREATE TABLE IF NOT EXISTS subscribers (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    subscribed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Таблица `bookings`
Хранит брони. Частичный уникальный индекс на `slot_start` предотвращает двойное бронирование.

```sql
CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    slot_start  TEXT NOT NULL,   -- ISO-8601 UTC, напр. "2026-03-13 14:15:00"
    slot_end    TEXT NOT NULL,   -- slot_start + 15 мин
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    cancelled   INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES subscribers(user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_slot
    ON bookings(slot_start) WHERE cancelled = 0;
```

### Таблица `games`
Отслеживает активную игру. Только одна игра может быть активной одновременно (`ended_at IS NULL`).

```sql
CREATE TABLE IF NOT EXISTS games (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at    TEXT,           -- NULL пока игра идёт
    FOREIGN KEY (user_id) REFERENCES subscribers(user_id)
);
```

## Пользовательский поток

### /start
```
/start
  └─→ upsert_subscriber(user_id)
  └─→ Показать главное меню (ReplyKeyboard):
        [📅 Забронировать стол]
        [🎾 Начать игру]
        [📋 Расписание на сегодня]
```

### Бронирование стола

```
[📅 Забронировать стол]
    │
    ▼
[CHOOSING_SLOT]
  Показать InlineKeyboard с доступными слотами через 15 минут
  (от текущего времени, округлённого вверх)
    │
  Пользователь выбирает слот
    │
    ▼
[ENTERING_NAME]
  Бот: "Введите ваше имя:"
    │
  Пользователь вводит имя
    │
    ▼
[CONFIRMING]
  Бот: "Забронировать [слот] для [имя]? ✅ Подтвердить  ❌ Отмена"
    │
  [Подтвердить] ──→ database.create_booking()
                    notifications.broadcast_booking()
                    → END
  [Отмена]      ──→ "Бронирование отменено."  → END
```

Обработка коллизии: если между выбором слота и подтверждением он занят,
поймать `IntegrityError` и предложить выбрать снова.

### Начало игры

```
[🎾 Начать игру]
    │
    ▼
Проверить: есть ли активная игра?
  Да ──→ "Сейчас идёт игра: [имя]. Подождите окончания." → END
    │
    ▼
[GAME_ENTERING_NAME]
  Бот: "Введите ваше имя:"
    │
  Пользователь вводит имя
    │
    ▼
  database.start_game(user_id, name)
  notifications.broadcast_game_started(name)
  Отправить подтверждение игроку с кнопкой [🏁 Закончить игру]
  → END
```

### Окончание игры

```
[🏁 Закончить игру]  (InlineButton только в сообщении инициатора)
    │
    ▼
  callback_query: проверить game.user_id == update.effective_user.id
    Нет ──→ Alert: "Только начавший игру может её закончить"
    │
    ▼
  database.end_game(game.id)
  notifications.broadcast_game_ended(name)
  Редактировать сообщение: убрать кнопку, показать "Игра завершена"
  → END
```

## Технические решения

| Задача | Решение |
|---|---|
| Async I/O | `python-telegram-bot` v21 (asyncio) + `aiosqlite` |
| Двойное бронирование | UNIQUE INDEX + перехват `IntegrityError` |
| Кнопка "Закончить игру" | Проверка `user_id` в callback, кнопка только у инициатора |
| Потерявшие связь боты | `try/except Forbidden` в broadcast → удаление из subscribers |
| Гонка состояний в игре | Проверка `get_active_game()` до старта |
| Таймаут разговора | `conversation_timeout=120` в `ConversationHandler` |

## Формат уведомлений

- **Бронирование:** `📅 [Имя] забронировал стол на [время]`
- **Начало игры:** `🎾 [Имя] начал игру на теннисном столе!`
- **Конец игры:** `🏁 [Имя] завершил игру.`
