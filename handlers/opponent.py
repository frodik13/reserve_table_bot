"""Хэндлеры для поиска соперника."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

import database
import keyboards
import notifications
import utils

logger = logging.getLogger(__name__)

_SEARCH_KEY = "opponent_search"


def _get_search(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return context.bot_data.get(_SEARCH_KEY)


async def _clear_search_notifications(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удалить/отредактировать все разосланные уведомления о поиске соперника."""
    search = _get_search(context)
    if not search:
        return

    bot = context.bot
    for uid, mid in search.get("notifications", {}).items():
        try:
            await bot.edit_message_text(
                chat_id=uid,
                message_id=mid,
                text="🔍 Поиск соперника завершён.",
            )
        except TelegramError:
            pass

    # Убрать кнопку «Отменить поиск» у инициатора
    searcher_msg = search.get("searcher_message_id")
    searcher_chat = search.get("searcher_chat_id")
    if searcher_msg and searcher_chat:
        try:
            await bot.edit_message_text(
                chat_id=searcher_chat,
                message_id=searcher_msg,
                text="🔍 Поиск соперника завершён.",
            )
        except TelegramError:
            pass

    context.bot_data.pop(_SEARCH_KEY, None)


# ---------------------------------------------------------------------------
# Начать поиск соперника
# ---------------------------------------------------------------------------

async def search_opponent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Пользователь нажал «Поиск соперника»."""
    existing = _get_search(context)
    if existing:
        if existing["searcher_id"] == update.effective_user.id:
            await update.effective_message.reply_text(
                "Вы уже ищете соперника. Дождитесь ответа или отмените поиск."
            )
            return
        searcher_name = existing["searcher_name"]
        await update.effective_message.reply_text(
            f"Сейчас {searcher_name} уже ищет соперника. Попробуйте позже."
        )
        return

    player_name = utils.display_name(update.effective_user)
    searcher_id = update.effective_user.id

    # Отправить инициатору сообщение с кнопкой отмены
    msg = await update.effective_message.reply_text(
        "🔍 Ищем соперника... Ожидайте ответа.",
        reply_markup=keyboards.cancel_search_keyboard(),
    )

    # Сохранить данные поиска
    search_data = {
        "searcher_id": searcher_id,
        "searcher_name": player_name,
        "searcher_chat_id": update.effective_chat.id,
        "searcher_message_id": msg.message_id,
        "notifications": {},
    }
    context.bot_data[_SEARCH_KEY] = search_data

    # Разослать уведомления всем подписчикам кроме инициатора
    subscribers = await database.get_all_subscribers()
    challenge_kb = keyboards.opponent_challenge_keyboard(searcher_id)

    for sub in subscribers:
        uid = sub["user_id"]
        if uid == searcher_id:
            continue
        try:
            sent = await context.bot.send_message(
                uid,
                f"🔍 {player_name} ищет соперника для игры!\n"
                "Хотите сыграть?",
                reply_markup=challenge_kb,
            )
            search_data["notifications"][uid] = sent.message_id
        except TelegramError as e:
            logger.warning("Failed to send challenge to %s: %s", uid, e)


# ---------------------------------------------------------------------------
# Принять вызов
# ---------------------------------------------------------------------------

async def accept_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    search = _get_search(context)
    if not search:
        await query.edit_message_text("🔍 Поиск уже завершён.")
        return

    searcher_id = search["searcher_id"]
    searcher_name = search["searcher_name"]
    searcher_chat = search["searcher_chat_id"]
    acceptor_name = utils.display_name(query.from_user)

    # Очистить все уведомления
    await _clear_search_notifications(context)

    # Уведомить принявшего
    await query.edit_message_text(
        f"✅ Вы приняли вызов {searcher_name}!"
    )

    # Уведомить инициатора и показать свободные слоты
    now_local = utils.local_now()
    date_prefix = now_local.strftime("%Y-%m-%d")
    booked = await database.get_booked_slots_today(date_prefix)
    slots_kb = keyboards.slots_keyboard(booked)

    text = f"✅ {acceptor_name} принял ваш вызов!"
    if slots_kb:
        text += "\n\nВыберите время для бронирования:"

    try:
        await context.bot.send_message(
            searcher_chat,
            text,
            reply_markup=slots_kb,
        )
    except TelegramError as e:
        logger.warning("Failed to notify searcher %s: %s", searcher_id, e)


# ---------------------------------------------------------------------------
# Отказаться от вызова
# ---------------------------------------------------------------------------

async def decline_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    search = _get_search(context)
    if not search:
        await query.edit_message_text("🔍 Поиск уже завершён.")
        return

    # Просто убрать кнопки у этого пользователя
    searcher_name = search["searcher_name"]
    await query.edit_message_text(
        f"Вы отклонили вызов {searcher_name}."
    )

    # Удалить из списка уведомлений
    search["notifications"].pop(query.from_user.id, None)


# ---------------------------------------------------------------------------
# Отменить поиск
# ---------------------------------------------------------------------------

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    search = _get_search(context)
    if not search:
        await query.edit_message_text("🔍 Поиск уже завершён.")
        return

    if search["searcher_id"] != query.from_user.id:
        await query.answer("Только инициатор может отменить поиск.", show_alert=True)
        return

    await _clear_search_notifications(context)

    await query.edit_message_text("🔍 Поиск соперника отменён.")
