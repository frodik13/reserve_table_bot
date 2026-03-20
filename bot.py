"""Точка входа: сборка и запуск Telegram-бота."""
import logging

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import config
import database
from handlers.booking import build_booking_handler
from handlers.game import end_game_callback, game_start
from handlers.opponent import accept_challenge, cancel_search, decline_challenge, search_opponent
from handlers.schedule import schedule
from handlers.start import start

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Инициализация БД при старте."""
    await database.init_db()
    logger.info("Database initialised.")


def main() -> None:
    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # /start
    app.add_handler(CommandHandler("start", start))

    # Расписание
    app.add_handler(CommandHandler("schedule", schedule))
    app.add_handler(MessageHandler(filters.Regex(r"^📋 Расписание на сегодня$"), schedule))

    # ConversationHandler для бронирования (должен идти до общих хэндлеров)
    app.add_handler(build_booking_handler())

    # Начало игры — обычный хэндлер
    app.add_handler(CommandHandler("gamestart", game_start))
    app.add_handler(MessageHandler(filters.Regex(r"^🎾 Начать игру$"), game_start))

    # Кнопка "Закончить игру" — обычный CallbackQueryHandler вне ConversationHandler
    app.add_handler(CallbackQueryHandler(end_game_callback, pattern=r"^end_game:"))

    # Поиск соперника
    app.add_handler(MessageHandler(filters.Regex(r"^🔍 Поиск соперника$"), search_opponent))
    app.add_handler(CallbackQueryHandler(accept_challenge, pattern=r"^accept_challenge:"))
    app.add_handler(CallbackQueryHandler(decline_challenge, pattern=r"^decline_challenge:"))
    app.add_handler(CallbackQueryHandler(cancel_search, pattern=r"^cancel_opponent_search$"))

    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
