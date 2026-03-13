"""Рассылка уведомлений всем подписчикам."""
from __future__ import annotations

import logging

from telegram import Bot
from telegram.error import Forbidden, TelegramError

import database

logger = logging.getLogger(__name__)


async def broadcast(bot: Bot, text: str, exclude_user_id: int | None = None) -> None:
    """Отправить text всем подписчикам, кроме exclude_user_id."""
    subscribers = await database.get_all_subscribers()
    for sub in subscribers:
        uid = sub["user_id"]
        if uid == exclude_user_id:
            continue
        try:
            await bot.send_message(uid, text)
        except Forbidden:
            # Пользователь заблокировал бота — удаляем из подписчиков
            logger.info("User %s blocked the bot, removing from subscribers.", uid)
            await database.remove_subscriber(uid)
        except TelegramError as e:
            logger.warning("Failed to send to %s: %s", uid, e)


async def broadcast_booking(bot: Bot, player_name: str, slot_display: str, booker_id: int) -> None:
    text = f"📅 {player_name} забронировал стол на {slot_display}"
    await broadcast(bot, text, exclude_user_id=booker_id)


async def broadcast_game_started(bot: Bot, player_name: str, starter_id: int) -> None:
    text = f"🎾 {player_name} начал игру за теннисным столом!"
    await broadcast(bot, text, exclude_user_id=starter_id)


async def broadcast_game_ended(bot: Bot, player_name: str, ender_id: int) -> None:
    text = f"🏁 {player_name} завершил игру."
    await broadcast(bot, text, exclude_user_id=ender_id)
