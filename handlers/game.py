"""Хэндлеры для начала и окончания игры."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import database
import keyboards
import notifications
import utils

logger = logging.getLogger(__name__)


async def game_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    active = await database.get_active_game()
    if active:
        started = utils.db_to_local(active["started_at"])
        await update.effective_message.reply_text(
            f"🎾 Сейчас идёт игра: {active['player_name']}\n"
            f"Начало: {utils.fmt_slot(started)}\n\n"
            "Подождите окончания игры.",
            parse_mode=ParseMode.HTML,
        )
        return

    player_name = utils.display_name(update.effective_user)
    game_id = await database.start_game(user_id=update.effective_user.id, player_name=player_name)
    started = utils.local_now()

    await update.effective_message.reply_text(
        f"🎾 Игра начата!\n\n"
        f"👤 Игрок: {player_name}\n"
        f"🕐 Время: {utils.fmt_slot(started)}\n\n"
        "Нажмите кнопку ниже, когда закончите:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.end_game_keyboard(game_id),
    )

    await notifications.broadcast_game_started(
        bot=context.bot,
        player_name=player_name,
        starter_id=update.effective_user.id,
    )


async def end_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    game_id = int(query.data.split(":")[1])
    active = await database.get_active_game()

    if active is None:
        await query.answer("Активной игры нет.", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if active["user_id"] != query.from_user.id:
        await query.answer(
            "Только тот, кто начал игру, может её завершить.", show_alert=True
        )
        return

    if active["id"] != game_id:
        await query.answer("Эта игра уже завершена.", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
        return

    await database.end_game(game_id)

    player_name = active["player_name"]
    started = utils.db_to_local(active["started_at"])
    ended = utils.local_now()

    await query.answer("Игра завершена!")
    await query.edit_message_text(
        f"🏁 Игра завершена!\n\n"
        f"👤 Игрок: {player_name}\n"
        f"🕐 Начало: {utils.fmt_slot(started)}\n"
        f"🕐 Конец: {utils.fmt_time(ended)}",
        parse_mode=ParseMode.HTML,
    )

    await notifications.broadcast_game_ended(
        bot=context.bot,
        player_name=player_name,
        ender_id=query.from_user.id,
    )
