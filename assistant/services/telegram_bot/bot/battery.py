import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.config import MY_CHAT_ID, BATTERY_THRESHOLD
from bot.ha import get_ha_state
from bot.menu import delete_last_bot_message, save_bot_message

logger = logging.getLogger(__name__)

battery_notified = False


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
    keyboard = [
        [InlineKeyboardButton("🔥 Heat Pool", callback_data="battery_heat_pool")],
        [InlineKeyboardButton("❌ Ignore", callback_data="battery_ignore")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await delete_last_bot_message(update, context)
    msg = await update.message.reply_text(message, reply_markup=reply_markup)
    await save_bot_message(context, msg)


async def periodic_battery_check(context: ContextTypes.DEFAULT_TYPE):
    global battery_notified

    battery_state = get_ha_state("sensor.sn_3015651602_battery_soc_total")
    if battery_state is None:
        return

    try:
        battery_value = float(battery_state)
    except ValueError:
        return

    if battery_value > BATTERY_THRESHOLD and not battery_notified:
        pv_surplus = get_ha_state("sensor.sn_3015651602_metering_power_supplied") or "unbekannt"
        message = (
            f"🔋 Batterie auf {battery_value}% geladen.\n"
            f"☀️ PV-Überschuss: {pv_surplus} W."
        )
        keyboard = [
            [InlineKeyboardButton("🔥 Heat Pool", callback_data="battery_heat_pool")],
            [InlineKeyboardButton("❌ Ignore", callback_data="battery_ignore")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.send_message(
                chat_id=MY_CHAT_ID,
                text=message,
                reply_markup=reply_markup,
            )
            battery_notified = True
            logger.info("Battery notification sent")
        except Exception as e:
            logger.error(f"Error sending battery notification: {e}")

    elif battery_value <= BATTERY_THRESHOLD:
        battery_notified = False
