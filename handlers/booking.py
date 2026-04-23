"""ConversationHandler для бронирования стола."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiosqlite
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
import database
import keyboards
import notifications
import utils

logger = logging.getLogger(__name__)

CHOOSING_SLOT, CONFIRMING = range(2)

_KEY_SLOT = "booking_slot"


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

async def booking_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    now_local = utils.local_now()
    date_prefix = now_local.strftime("%Y-%m-%d")

    spam_msg = await _check_spam_limits(user_id, date_prefix)
    if spam_msg is not None:
        await update.effective_message.reply_text(spam_msg)
        return ConversationHandler.END

    booked = await database.get_booked_slots_today(date_prefix)

    kb = keyboards.slots_keyboard(booked)
    if kb is None:
        await update.effective_message.reply_text(
            "На сегодня все ближайшие слоты заняты. Попробуйте позже."
        )
        return ConversationHandler.END

    await update.effective_message.reply_text(
        "Выберите время для бронирования:",
        reply_markup=kb,
    )
    return CHOOSING_SLOT


async def _check_spam_limits(user_id: int, date_prefix: str) -> str | None:
    """Проверка антиспама. Возвращает текст ошибки или None если всё ок."""
    count = await database.count_user_bookings_for_date(user_id, date_prefix)
    if count >= config.MAX_BOOKINGS_PER_DAY:
        return (
            f"⚠️ Вы уже забронировали стол {count} раз(а) сегодня. "
            f"Лимит — {config.MAX_BOOKINGS_PER_DAY} брони в день."
        )

    last_user_id = await database.get_last_booking_user_id()
    if last_user_id == user_id:
        return (
            "⚠️ Вы уже забронировали стол последним. "
            "Дайте возможность другим игрокам, прежде чем бронировать снова."
        )

    return None


# ---------------------------------------------------------------------------
# Step 1: выбор слота → показать подтверждение
# ---------------------------------------------------------------------------

async def slot_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    slot_db = query.data.split(":", 1)[1]  # "slot:<slot_db>"
    context.user_data[_KEY_SLOT] = slot_db

    slot_local = utils.db_to_local(slot_db)
    slot_display = utils.fmt_slot(slot_local)
    player_name = utils.display_name(query.from_user)

    await query.edit_message_text(
        f"Подтвердите бронирование:\n\n"
        f"🕐 Время: {slot_display}\n"
        f"👤 Игрок: {player_name}",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.confirm_booking_keyboard(slot_db),
    )
    return CONFIRMING


# ---------------------------------------------------------------------------
# Step 2: подтверждение / отмена
# ---------------------------------------------------------------------------

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    # callback_data = "confirm|<slot_db>"
    slot_db = query.data.split("|", 1)[1]
    user_id = query.from_user.id
    player_name = utils.display_name(query.from_user)

    slot_local = utils.db_to_local(slot_db)
    date_prefix = slot_local.strftime("%Y-%m-%d")

    spam_msg = await _check_spam_limits(user_id, date_prefix)
    if spam_msg is not None:
        await query.edit_message_text(spam_msg)
        context.user_data.clear()
        return ConversationHandler.END

    slot_end_db = utils.slot_to_db(slot_local + timedelta(minutes=utils.SLOT_MINUTES))

    try:
        await database.create_booking(
            user_id=user_id,
            player_name=player_name,
            slot_start=slot_db,
            slot_end=slot_end_db,
        )
    except aiosqlite.IntegrityError:
        await query.edit_message_text(
            "⚠️ Этот слот только что заняли. Пожалуйста, выберите другое время."
        )
        return await _restart_slot_choice(update, context)

    slot_display = utils.fmt_slot(slot_local)
    await query.edit_message_text(
        f"✅ Стол забронирован на {slot_display}!",
        parse_mode=ParseMode.HTML,
    )

    await notifications.broadcast_booking(
        bot=context.bot,
        player_name=player_name,
        slot_display=slot_display,
        booker_id=user_id,
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Бронирование отменено.")
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено.")
    context.user_data.clear()
    return ConversationHandler.END


async def user_cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмена пользователем своей собственной брони из расписания."""
    query = update.callback_query

    try:
        booking_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer("Некорректные данные.", show_alert=True)
        return

    booking = await database.cancel_booking_by_id(booking_id, user_id=query.from_user.id)
    if booking is None:
        await query.answer(
            "Бронь не найдена, уже отменена или не ваша.", show_alert=True,
        )
        return

    slot_local = utils.db_to_local(booking["slot_start"])
    slot_display = utils.fmt_slot(slot_local)
    player_name = booking["player_name"]

    await query.answer("Бронь отменена.")
    logger.info(
        "User %s cancelled own booking %s (%s).",
        query.from_user.id, booking_id, slot_display,
    )

    await notifications.broadcast_booking_self_cancelled(
        bot=context.bot,
        player_name=player_name,
        slot_display=slot_display,
        user_id=query.from_user.id,
    )

    await query.edit_message_text(
        f"{query.message.text}\n\n✅ Ваша бронь на {slot_display} отменена."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _restart_slot_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    now_local = utils.local_now()
    date_prefix = now_local.strftime("%Y-%m-%d")
    booked = await database.get_booked_slots_today(date_prefix)
    kb = keyboards.slots_keyboard(booked)
    if kb is None:
        await update.effective_message.reply_text(
            "На сегодня все ближайшие слоты заняты. Попробуйте позже."
        )
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "Выберите другое время:",
        reply_markup=kb,
    )
    return CHOOSING_SLOT


# ---------------------------------------------------------------------------
# ConversationHandler
# ---------------------------------------------------------------------------

def build_booking_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("book", booking_start),
            MessageHandler(filters.Regex(r"^📅 Забронировать стол$"), booking_start),
        ],
        states={
            CHOOSING_SLOT: [
                CallbackQueryHandler(slot_chosen, pattern=r"^slot:"),
            ],
            CONFIRMING: [
                CallbackQueryHandler(confirm_booking, pattern=r"^confirm\|"),
                CallbackQueryHandler(cancel_booking, pattern=r"^cancel_booking$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        conversation_timeout=180,
    )
