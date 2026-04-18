import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))

HA_URL = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))
BATTERY_THRESHOLD = float(os.getenv("BATTERY_THRESHOLD", "80"))

# Whisper Backend: "local" oder "external"
WHISPER_BACKEND = os.getenv("WHISPER_BACKEND", "local").lower()

# Lokales Whisper (faster-whisper)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_THREADS = int(os.getenv("WHISPER_THREADS", "4"))
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "de")

# Externes Whisper (HTTP API auf KI-PC)
WHISPER_EXTERNAL_URL = os.getenv("WHISPER_EXTERNAL_URL", "http://10.1.10.78:10300/v1/audio/transcriptions")
WHISPER_EXTERNAL_MODEL = os.getenv("WHISPER_EXTERNAL_MODEL", "deepdml/faster-whisper-large-v3-turbo-ct2")

VOICE_REPLY_WITH_TRANSCRIPT = os.getenv("VOICE_REPLY_WITH_TRANSCRIPT", "true").lower() == "true"
VOICE_DOWNLOAD_DIR = os.getenv("VOICE_DOWNLOAD_DIR", "data/voice")

# Ollama LLM
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://10.1.10.111:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:0.8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))
OLLAMA_KEEP_ALIVE = int(os.getenv("OLLAMA_KEEP_ALIVE", "-1"))

# Modellparameter (Quality/Geschwindigkeit)
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9"))
OLLAMA_TOP_K = int(os.getenv("OLLAMA_TOP_K", "20"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "2048"))

OLLAMA_NO_THINK = os.getenv("OLLAMA_NO_THINK", "true").lower() == "true"