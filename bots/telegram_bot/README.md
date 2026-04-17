# Telegram Home Assistant Bot

Simple Telegram bot that triggers a few automations in Home Assistant (e.g. gate, pool pump, heating) and checks the battery state.

## What it does

- Shows a persistent Telegram main menu with submenus for gate and pool control.
- Reads the current battery SOC and PV surplus from Home Assistant.
- Sends a notification when the battery level is above a configured threshold.
- Lets you quickly turn on the pool heating with a button via Home Assistant automations.

## Key files

- `telegram_ha_bot.py`  
  Main bot code.

- `.env`  
  Config values (bot token, chat ID, HA URL, HA token, thresholds). Not committed.

- `requirements.txt`  
  Python dependencies (`python-telegram-bot[job-queue]`, `requests`, `python-dotenv`).

- `systemd/telegram-bot.service`  
  Example systemd service file; can be copied to `/etc/systemd/system/`.

## Requirements

- Python 3  
- Telegram bot token  
- Home Assistant instance with automations for the bot  
- Home Assistant long-lived access token  

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
```

### 2. Virtual environment

Inside the bot folder:

```bash
cd /root/smarthome/smarthome/bots/telegram_bot
python3 -m venv telegram_bot_env
source telegram_bot_env/bin/activate
pip install -r requirements.txt
deactivate
```

### 3. Test manually

```bash
cd /root/smarthome/smarthome/bots/telegram_bot
source telegram_bot_env/bin/activate
python telegram_ha_bot.py
```

Use `Ctrl+C` to stop the bot while testing.

### 4. Run with systemd

Copy the service file:

```bash
cp /root/smarthome/smarthome/bots/telegram_bot/systemd/telegram-bot.service /etc/systemd/system/telegram-bot.service
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

## Using sparse checkout in this repo

If you only want this bot folder from the big `smarthome` repo, you can clone it with sparse checkout:

```bash
git clone --filter=blob:none --sparse git@github.com:YOUR_USER/smarthome.git smarthome
cd smarthome
git sparse-checkout init --cone
git sparse-checkout set smarthome/bots/telegram_bot
```

After that the working tree only contains this folder.

### Typical setup after cloning with sparse checkout

1. Create the systemd folder (if needed):

```bash
mkdir -p /root/smarthome/smarthome/bots/telegram_bot/systemd
```

2. Create the venv and install:

```bash
cd /root/smarthome/smarthome/bots/telegram_bot
python3 -m venv telegram_bot_env
source telegram_bot_env/bin/activate
pip install -r requirements.txt
deactivate
```

3. Copy your `.env`:

```bash
cp /path/to/your/telegram_ha_bot/.env /root/smarthome/smarthome/bots/telegram_bot/.env
```

4. Copy and start the service:

```bash
cp /root/smarthome/smarthome/bots/telegram_bot/systemd/telegram-bot.service /etc/systemd/system/telegram-bot.service
systemctl daemon-reload
systemctl enable telegram-bot.service
systemctl restart telegram-bot.service
```