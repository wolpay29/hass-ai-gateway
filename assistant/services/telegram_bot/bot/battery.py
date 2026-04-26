import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.config import MY_CHAT_ID, BATTERY_THRESHOLD
from core.ha import get_ha_state
from bot.menu import delete_last_bot_message, save_bot_message

logger = logging.getLogger(__name__)


def _battery_keyboard() -> InlineKeyboardMarkup:
    from bot.menu_config import get_battery_notification_rows
    rows = get_battery_notification_rows()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(btn["label"], callback_data=btn["callback_data"]) for btn in row]
        for row in rows
    ])


async def check_battery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    battery_state = get_ha_state("sensor.sn_3015651602_battery_soc_total")
    pv_surplus = get_ha_state("sensor.sn_3015651602_metering_power_supplied")

    if battery_state is None:
        await update.message.reply_text("❌ Batterie-Sensor nicht erreichbar.")
        return

    try:
        battery_value = float(battery_state)
    except ValueError:
        await update.message.reply_text(f"❌ Ungültiger Wert: {battery_state}")
        return

    if pv_surplus is None:
        pv_surplus = "unbekannt"

    message = (
        f"🔋 Batterie aktuell: {battery_value}%\n"
        f"☀️ PV-Überschuss: {pv_surplus} W\n\n"
        f"⚡ Pool-Heizung einschalten?"
    )
    await delete_last_bot_message(update, context)
    msg = await update.message.reply_text(message, reply_markup=_battery_keyboard())
    await save_bot_message(context, msg)
