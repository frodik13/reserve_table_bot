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
        "Выберите время для бронирования:",
        reply_markup=kb,
    )
    return CHOOSING_SLOT


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
    player_name = utils.display_name(query.from_user)

    slot_local = utils.db_to_local(slot_db)
    slot_end_db = utils.slot_to_db(slot_local + timedelta(minutes=utils.SLOT_MINUTES))

    try:
        await database.create_booking(
            user_id=query.from_user.id,
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
        booker_id=query.from_user.id,
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
