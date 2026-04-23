"""Хэндлер расписания на сегодня."""
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
import database
import keyboards
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
        mention = utils.mention_html(b["user_id"], b["player_name"])
        lines.append(f"• {utils.fmt_time(slot_local)} — {mention}")

    active = await database.get_active_game()
    if active:
        started = utils.db_to_local(active["started_at"])
        mention = utils.mention_html(active["user_id"], active["player_name"])
        lines.append(f"\n🎾 Сейчас играет: {mention} (с {utils.fmt_time(started)})")

    user_id = update.effective_user.id
    is_admin = user_id in config.ADMIN_IDS
    if is_admin:
        kb = keyboards.admin_schedule_keyboard(bookings)
        if kb is not None:
            lines.append("\n🛠 Нажмите на бронь, чтобы отменить её.")
    else:
        kb = keyboards.user_schedule_keyboard(bookings, user_id)
        if kb is not None:
            lines.append("\n✏️ Передумали? Нажмите на свою бронь, чтобы отменить.")

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
