#!/usr/bin/env python3
"""
Telegram bot with persistent main menu, gate control, pool control
and periodic battery check via Home Assistant REST API.
"""

import logging
import os

import requests
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from bot.handlers import handle_voice

# Load config from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))

HA_URL = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 300))
BATTERY_THRESHOLD = float(os.getenv("BATTERY_THRESHOLD", 80))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

battery_notified = False


# Home Assistant helpers
def get_ha_state(entity_id: str) -> str | None:
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    url = f"{HA_URL}/api/states/{entity_id}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get("state")
    except Exception as e:
        logger.error(f"Error reading state for {entity_id}: {e}")
        return None


def trigger_ha_automation(automation_entity_id: str):
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    url = f"{HA_URL}/api/services/automation/trigger"
    payload = {"entity_id": automation_entity_id}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Triggered automation: {automation_entity_id}")
    except Exception as e:
        logger.error(f"Error triggering automation {automation_entity_id}: {e}")


# Delete last bot message if available
async def delete_last_bot_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "last_bot_msg_id" not in context.user_data:
        return

    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=context.user_data["last_bot_msg_id"],
        )
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")
    finally:
        context.user_data.pop("last_bot_msg_id", None)


# Store last sent bot message id
async def save_bot_message(context: ContextTypes.DEFAULT_TYPE, message):
    context.user_data["last_bot_msg_id"] = message.message_id


# Persistent reply keyboard
def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🚪 TOR-Steuerung"), KeyboardButton("🏊 Pool-Steuerung")],
        [KeyboardButton("🔋 Batterie prüfen")],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_startup=False):
    if not is_startup and update.effective_chat:
        await delete_last_bot_message(update, context)

    reply_markup = get_main_menu_keyboard()

    if update.callback_query:
        msg = await update.callback_query.message.reply_text(
            "🏠 Hauptmenü – wähle eine Option:",
            reply_markup=reply_markup,
        )
        try:
            await update.callback_query.answer()
        except Exception:
            pass
    elif update.message:
        msg = await update.message.reply_text(
            "🏠 Hauptmenü – wähle eine Option:",
            reply_markup=reply_markup,
        )
    else:
        return

    await save_bot_message(context, msg)


async def startup_menu(app: Application):
    try:
        reply_markup = get_main_menu_keyboard()
        await app.bot.send_message(
            chat_id=MY_CHAT_ID,
            text="🏠 Bot wurde gestartet – Hauptmenü aktiviert.",
            reply_markup=reply_markup,
        )
        logger.info("Startup menu sent")
    except Exception as e:
        logger.error(f"Error sending startup menu: {e}")


# Battery check
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


# Periodic battery job
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
            sent = await context.bot.send_message(
                chat_id=MY_CHAT_ID,
                text=message,
                reply_markup=reply_markup,
            )
            periodic_battery_check.last_msg_id = sent.message_id
            battery_notified = True
            logger.info("Battery notification sent")
        except Exception as e:
            logger.error(f"Error sending battery notification: {e}")

    elif battery_value <= BATTERY_THRESHOLD:
        battery_notified = False


# Submenus
async def show_tor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🚶 Tor Geh", callback_data="tor_geh")],
        [InlineKeyboardButton("🔒 Tor Geh Fix", callback_data="tor_geh_fix")],
        [InlineKeyboardButton("🚗 Tor Auto", callback_data="tor_auto")],
        [InlineKeyboardButton("🔧 Tor Auto Fix", callback_data="tor_auto_fix")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="zurueck_hauptmenue")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text("🚪 TOR-Optionen wählen:", reply_markup=reply_markup)
    await save_bot_message(context, msg)


async def show_pool_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💧 Pump ON", callback_data="pool_pump_on")],
        [InlineKeyboardButton("💧 Pump OFF", callback_data="pool_pump_off")],
        [InlineKeyboardButton("🔥 Heat Pool", callback_data="pool_heat_on")],
        [InlineKeyboardButton("❄️ Heat OFF", callback_data="pool_heat_off")],
        [InlineKeyboardButton("⬅️ Zurück", callback_data="zurueck_hauptmenue")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text("🏊 Pool-Steuerung:", reply_markup=reply_markup)
    await save_bot_message(context, msg)


# Handle persistent main menu buttons
async def handle_main_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    await delete_last_bot_message(update, context)

    if text == "🚪 TOR-Steuerung":
        await show_tor_menu(update, context)
    elif text == "🏊 Pool-Steuerung":
        await show_pool_menu(update, context)
    elif text == "🔋 Batterie prüfen":
        await check_battery(update, context)
    else:
        await update.message.reply_text("Bitte nutze die Buttons im Hauptmenü.")


# Back to main menu
async def zurueck_hauptmenue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        await query.message.delete()
    except Exception:
        pass

    reply_markup = get_main_menu_keyboard()
    msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🏠 Hauptmenü – wähle eine Option:",
        reply_markup=reply_markup,
    )
    context.user_data["last_bot_msg_id"] = msg.message_id


# Gate actions
async def action_tor_geh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_ha_automation("automation.trigger_tor_geh")
    await query.edit_message_text("✅ Tor Geh wird ausgelöst...")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_tor_geh_fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_ha_automation("automation.trigger_tor_geh_fix")
    await query.edit_message_text("✅ Tor Geh Fix wird ausgelöst...")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_tor_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_ha_automation("automation.trigger_tor_auto")
    await query.edit_message_text("✅ Tor Auto wird ausgelöst...")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_tor_auto_fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_ha_automation("automation.trigger_tor_auto_fix")
    await query.edit_message_text("✅ Tor Auto Fix wird ausgelöst...")
    context.user_data["last_bot_msg_id"] = query.message.message_id


# Pool actions
async def action_pool_pump_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_ha_automation("automation.trigger_pool_pump_on")
    await query.edit_message_text("✅ Pool-Pumpe EIN")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_pool_pump_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_ha_automation("automation.trigger_pool_pump_off")
    await query.edit_message_text("✅ Pool-Pumpe AUS")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_pool_heat_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_ha_automation("automation.trigger_pool_heat_pump_on")
    await query.edit_message_text("🔥 Pool-Heizung EIN")
    context.user_data["last_bot_msg_id"] = query.message.message_id


async def action_pool_heat_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger_ha_automation("automation.trigger_pool_heat_pump_off")
    await query.edit_message_text("❄️ Pool-Heizung AUS")
    context.user_data["last_bot_msg_id"] = query.message.message_id


# Battery notification actions
async def battery_notification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "battery_heat_pool":
        trigger_ha_automation("automation.trigger_pool_heat_pump_on")
        await query.edit_message_text("🔥 Pool-Heizung wurde eingeschaltet.")
    elif query.data == "battery_ignore":
        await query.edit_message_text("Benachrichtigung ignoriert.")

    context.user_data["last_bot_msg_id"] = query.message.message_id


# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu(update, context)
    logger.info(f"Start from user {update.effective_user.id}")


def main():
    if not BOT_TOKEN or not HA_URL or not HA_TOKEN:
        raise ValueError("Missing config in .env file")

    app = Application.builder().token(BOT_TOKEN).post_init(startup_menu).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check_battery", check_battery))

    app.add_handler(
        MessageHandler(
            filters.Regex(r"^(🚪 TOR-Steuerung|🏊 Pool-Steuerung|🔋 Batterie prüfen)$"),
            handle_main_menu_selection,
        )
    )

    app.add_handler(CallbackQueryHandler(zurueck_hauptmenue_callback, pattern=r"^zurueck_hauptmenue$"))

    app.add_handler(CallbackQueryHandler(action_tor_geh, pattern=r"^tor_geh$"))
    app.add_handler(CallbackQueryHandler(action_tor_geh_fix, pattern=r"^tor_geh_fix$"))
    app.add_handler(CallbackQueryHandler(action_tor_auto, pattern=r"^tor_auto$"))
    app.add_handler(CallbackQueryHandler(action_tor_auto_fix, pattern=r"^tor_auto_fix$"))

    app.add_handler(CallbackQueryHandler(action_pool_pump_on, pattern=r"^pool_pump_on$"))
    app.add_handler(CallbackQueryHandler(action_pool_pump_off, pattern=r"^pool_pump_off$"))
    app.add_handler(CallbackQueryHandler(action_pool_heat_on, pattern=r"^pool_heat_on$"))
    app.add_handler(CallbackQueryHandler(action_pool_heat_off, pattern=r"^pool_heat_off$"))

    app.add_handler(
        CallbackQueryHandler(
            battery_notification_callback,
            pattern=r"^(battery_heat_pool|battery_ignore)$",
        )
    )

    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            periodic_battery_check,
            interval=CHECK_INTERVAL_SECONDS,
            first=10,
        )
        logger.info(f"Battery check started every {CHECK_INTERVAL_SECONDS} seconds")
    else:
        logger.warning("JobQueue not available. Install python-telegram-bot[job-queue]")

    logger.info("Bot is starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()