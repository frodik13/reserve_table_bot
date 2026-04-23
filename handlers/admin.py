"""Хэндлеры для администратора: удаление броней."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

import config
import database
import notifications
import utils

logger = logging.getLogger(__name__)


async def admin_cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    if query.from_user.id not in config.ADMIN_IDS:
        await query.answer("Недостаточно прав.", show_alert=True)
        return

    try:
        booking_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer("Некорректные данные.", show_alert=True)
        return

    booking = await database.cancel_booking_by_id(booking_id)
    if booking is None:
        await query.answer("Бронь уже отменена или не найдена.", show_alert=True)
        return

    slot_local = utils.db_to_local(booking["slot_start"])
    slot_display = utils.fmt_slot(slot_local)
    player_name = booking["player_name"]

    await query.answer("Бронь отменена.")
    logger.info(
        "Admin %s cancelled booking %s (%s, %s).",
        query.from_user.id, booking_id, player_name, slot_display,
    )

    try:
        await context.bot.send_message(
            booking["user_id"],
            f"❌ Ваша бронь на {slot_display} отменена администратором.",
        )
    except Exception as e:
        logger.warning("Failed to notify user %s: %s", booking["user_id"], e)

    await notifications.broadcast_booking_cancelled(
        bot=context.bot,
        player_name=player_name,
        slot_display=slot_display,
        owner_id=booking["user_id"],
    )

    mention = utils.mention_html(booking["user_id"], player_name)
    await query.edit_message_text(
        f"{query.message.text_html}\n\n✅ Отменена: {mention} на {slot_display}.",
        parse_mode="HTML",
    )
