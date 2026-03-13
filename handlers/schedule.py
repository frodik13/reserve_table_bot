"""Хэндлер расписания на сегодня."""
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import database
import utils


async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = utils.local_now()
    date_prefix = now.strftime("%Y-%m-%d")
    bookings = await database.get_bookings_for_date(date_prefix)

    if not bookings:
        await update.effective_message.reply_text("На сегодня броней нет. 🎾")
        return

    lines = [f"📋 Расписание на {now.strftime('%d %b %Y')}:\n"]
    for b in bookings:
        slot_local = utils.db_to_local(b["slot_start"])
        lines.append(f"• {utils.fmt_time(slot_local)} — {b['player_name']}")

    active = await database.get_active_game()
    if active:
        started = utils.db_to_local(active["started_at"])
        lines.append(f"\n🎾 Сейчас играет: {active['player_name']} (с {utils.fmt_time(started)})")

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )
