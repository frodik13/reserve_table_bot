"""Фабрики клавиатур."""
from __future__ import annotations

from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import utils

SLOT_MINUTES = 15


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📅 Забронировать стол"],
            ["🎾 Начать игру"],
            ["🔍 Поиск соперника"],
            ["📋 Расписание на сегодня"],
        ],
        resize_keyboard=True,
    )


def opponent_challenge_keyboard(searcher_id: int) -> InlineKeyboardMarkup:
    """Кнопки «Принять вызов» / «Отказаться» для уведомления о поиске соперника."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Принять вызов", callback_data=f"accept_challenge:{searcher_id}"),
            InlineKeyboardButton("❌ Отказаться", callback_data=f"decline_challenge:{searcher_id}"),
        ]
    ])


def cancel_search_keyboard() -> InlineKeyboardMarkup:
    """Кнопка «Отменить поиск» для инициатора поиска."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отменить поиск", callback_data="cancel_opponent_search")]
    ])


def slots_keyboard(booked_slots_utc: list[str]) -> InlineKeyboardMarkup | None:
    """
    Построить клавиатуру из доступных слотов.
    booked_slots_utc — список занятых slot_start из БД (UTC строки).
    """
    slots = utils.next_slots()
    buttons: list[InlineKeyboardButton] = []

    for slot in slots:
        slot_db = utils.slot_to_db(slot)
        if slot_db in booked_slots_utc:
            continue  # пропустить занятые
        label = utils.fmt_time(slot)
        buttons.append(InlineKeyboardButton(label, callback_data=f"slot:{slot_db}"))

    if not buttons:
        return None

    # Разбить на ряды по 4 кнопки
    rows = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
    return InlineKeyboardMarkup(rows)


def confirm_booking_keyboard(slot_db: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm|{slot_db}"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_booking"),
        ]
    ])


def end_game_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏁 Закончить игру", callback_data=f"end_game:{game_id}")]
    ])
