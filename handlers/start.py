"""Хэндлер /start — подписка и главное меню."""
from telegram import Update
from telegram.ext import ContextTypes

import database
import keyboards


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await database.upsert_subscriber(user.id, user.username, user.first_name)

    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Вы подписаны на уведомления о бронированиях теннисного стола.\n"
        "Используйте кнопки ниже для управления.",
        reply_markup=keyboards.main_menu(),
    )
