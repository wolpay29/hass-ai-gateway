# Telegram Home Assistant Bot

Telegram bot for Home Assistant control with menu-based actions, battery monitoring, and optional voice-message transcription via Faster Whisper.

## What it does

- Shows a persistent Telegram main menu with submenus for gate and pool control.
- Reads the current battery SOC and PV surplus from Home Assistant.
- Sends a notification when the battery level is above a configured threshold.
- Lets you quickly turn on the pool heating with a button via Home Assistant automations.
- Downloads Telegram voice messages and transcribes them locally with Faster Whisper.
- Optionally replies with the recognized transcript.

## Key files

- `telegram_ha_bot.py`  
  Main bot code.

- `bot/voice.py`  
  Voice download directory handling and Faster Whisper transcription.

- `bot/config.py`  
  Loads environment variables and application settings.

- `.env`  
  Config values (bot token, chat ID, HA URL, HA token, thresholds, Whisper settings). Not committed.

- `requirements.txt`  
  Python dependencies (`python-telegram-bot[job-queue]`, `requests`, `python-dotenv`, `faster-whisper`).

- `systemd/telegram-bot.service`  
  Example systemd service file; can be copied to `/etc/systemd/system/`.

## Requirements

- Python 3
- Telegram bot token
- Home Assistant instance with automations for the bot
- Home Assistant long-lived access token
- FFmpeg installed on the system
- Sufficient CPU performance for local Whisper transcription

## Setup

### 1. Config

Create a `.env` file in the same folder as `telegram_ha_bot.py`:

```ini
BOT_TOKEN=your_telegram_bot_token
MY_CHAT_ID=-123456789

HA_URL=http://10.1.10.100:8123
HA_TOKEN=your_long-lived_token

CHECK_INTERVAL_SECONDS=300
BATTERY_THRESHOLD=80

VOICE_REPLY_WITH_TRANSCRIPT=true
VOICE_DOWNLOAD_DIR=data/voice

WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

### 2. Virtual environment

Inside the bot folder:

```bash
cd /root/smarthome/bots/telegram_bot
python3 -m venv telegram_bot_env
source telegram_bot_env/bin/activate
pip install -r requirements.txt
deactivate
```

### 3. Install FFmpeg

Faster Whisper uses FFmpeg for audio handling. Install it on the host system:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

### 4. Test manually

```bash
cd /root/smarthome/bots/telegram_bot
source telegram_bot_env/bin/activate
python telegram_ha_bot.py
```

Use `Ctrl+C` to stop the bot while testing.

### 5. Run with systemd

Copy the service file:

```bash
cp /root/smarthome/bots/telegram_bot/systemd/telegram-bot.service /etc/systemd/system/telegram-bot.service
```

Reload systemd, enable and start the bot:

```bash
systemctl daemon-reload
systemctl enable telegram-bot.service
systemctl restart telegram-bot.service
systemctl status telegram-bot.service
```

Check logs:

```bash
journalctl -u telegram-bot.service -n 50 --no-pager
```

## Voice transcription notes

- Voice messages are downloaded from Telegram and transcribed locally.
- `WHISPER_MODEL=small` uses a small Whisper model for CPU-friendly performance.
- `WHISPER_COMPUTE_TYPE=int8` enables quantization for faster inference.
- `VOICE_REPLY_WITH_TRANSCRIPT=true` enables reply with transcript text.
- Whisper handles language detection automatically when no language is forced.
- Fuller settings like `language` and `beam_size` can be added via `.env` if needed. [web:464][web:468]

## Recommended config (CPU)

For light CPU usage and decent quality:

```ini
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
VOICE_REPLY_WITH_TRANSCRIPT=true
```

## Changelog

## Changelog

### v0.2.0 (2026-04-17)

- Added voice message transcription with Faster Whisper
- Added Whisper runtime config via .env
- Added optional transcript replies and voice download dir