# Telegram Bot

Telegram adapter for the smart home assistant. Provides a button-driven menu for direct Home Assistant control and accepts free-form voice/text commands processed by the assistant core.

For the full pipeline (LLM, RAG, fallback modes, conversation history, config reference) see [OVERVIEW.md](../../../OVERVIEW.md).

## What it does

- Persistent reply-keyboard with configurable submenus — all buttons defined in `menus.yaml`, no code changes needed.
- Inline buttons call Home Assistant automations or any HA service directly.
- Submenu titles support `{entity_id}` placeholders that show live HA state when the menu opens.
- Accepts voice messages (transcribed via Whisper) and free-form text, routed to the assistant core.

## Menu configuration

All menus and buttons live in `menus.yaml`. Edit that file and restart the bot — no Python needed.

Each inline button supports:

```yaml
# Trigger an automation
callback_data: pool_pump_on
automation: automation.trigger_pool_pump_on
response: "✅ Pool-Pumpe EIN"

# Call any HA service directly
callback_data: light_wz_on
service: light.turn_on
entity_id: light.wohnzimmer
response: "✅ Licht EIN"

# Button with no HA call (e.g. dismiss)
callback_data: battery_ignore
response: "Benachrichtigung ignoriert."
```

Live HA state in the submenu title:

```yaml
"🔋 Batterie prüfen":
  title: "🔋 Batterie: {sensor.my_battery_soc}%\n☀️ PV: {sensor.pv_surplus} W"
  rows: ...
```

Button layout — multiple buttons per row:

```yaml
    rows:
      - - label: "⬇️ AB"
          callback_data: rollo_ab
          ...
        - label: "⬆️ AUF"
          callback_data: rollo_auf
          ...
```

## Key files

| File | Purpose |
|---|---|
| `main.py` | Entry point — registers all handlers dynamically from `menus.yaml` |
| `menus.yaml` | All menu/button configuration |
| `bot/menu_config.py` | Loads and parses `menus.yaml` |
| `bot/menu.py` | Reply-keyboard helpers, startup menu |
| `bot/callbacks.py` | Menu routing, generic HA action dispatcher, live state resolver |
| `bot/handlers.py` | Voice/text → `core.processor` → Telegram Markdown reply |

## Setup

### 1. Config

Minimum required entries in `.env`:

```ini
BOT_TOKEN=your-telegram-bot-token
MY_CHAT_ID=123456789
HA_URL=http://192.168.1.x:8123
HA_TOKEN=your-long-lived-ha-token
```

For Whisper, LLM, RAG, and fallback settings see [OVERVIEW.md](../../../OVERVIEW.md).

### 2. Virtual environment

```bash
cd services/telegram_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. FFmpeg (only needed for local Whisper)

```bash
sudo apt update && sudo apt install -y ffmpeg
```

### 4. Run

```bash
cd services/telegram_bot
source venv/bin/activate
python main.py
```

### 5. Systemd

```bash
cp systemd/telegram-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable telegram-bot
systemctl start telegram-bot
journalctl -u telegram-bot -n 50 --no-pager
```

## Changelog

### v0.5.0 (2026-04-26)

- YAML-driven menus: all buttons, automations/services, and responses defined in `menus.yaml` — no Python changes needed.
- Buttons support `automation` or `service`+`entity_id` HA call types.
- Submenu titles support `{entity_id}` placeholders for live HA state.
- Removed periodic battery polling and automatic battery notification.

### v0.4.0 (2026-04-23)

- Added RAG mode, `/rag_rebuild` command, conversation history.

### v0.3.0 (2026-04-20)

- Added three-tier fallback system (off / REST / MCP).

### v0.2.0 (2026-04-17)

- Added voice message transcription with Faster Whisper.
