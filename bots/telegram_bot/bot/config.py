import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))

HA_URL = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))
BATTERY_THRESHOLD = float(os.getenv("BATTERY_THRESHOLD", "80"))

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
VOICE_REPLY_WITH_TRANSCRIPT = os.getenv("VOICE_REPLY_WITH_TRANSCRIPT", "true").lower() == "true"
VOICE_DOWNLOAD_DIR = os.getenv("VOICE_DOWNLOAD_DIR", "data/voice")
