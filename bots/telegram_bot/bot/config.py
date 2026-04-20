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

# LM Studio (OpenAI-kompatible /v1 API). Wird sowohl fuer den Primaerpfad
# (parse_command / format_state_reply) als auch fuer den MCP-Fallback (Mode 2)
# genutzt - gleiche Instanz, gleiches Modell.
LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "http://10.1.10.78:1234")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "qwen2.5-7b-instruct")
LMSTUDIO_TIMEOUT = int(os.getenv("LMSTUDIO_TIMEOUT", "30"))
LMSTUDIO_KEEP_ALIVE = int(os.getenv("LMSTUDIO_KEEP_ALIVE", "-1"))
# LMSTUDIO_API_KEY: Pflicht wenn LM Studio Server-Auth aktiv ist (fuer MCP noetig).
LMSTUDIO_API_KEY = os.getenv("LMSTUDIO_API_KEY", "")

# Modellparameter (Quality/Geschwindigkeit)
LMSTUDIO_TEMPERATURE = float(os.getenv("LMSTUDIO_TEMPERATURE", "0.1"))
LMSTUDIO_TOP_P = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))
LMSTUDIO_TOP_K = int(os.getenv("LMSTUDIO_TOP_K", "20"))
LMSTUDIO_NUM_CTX = int(os.getenv("LMSTUDIO_NUM_CTX", "2048"))

LMSTUDIO_NO_THINK = os.getenv("LMSTUDIO_NO_THINK", "true").lower() == "true"

# MCP (Mode 2) - Context-Groesse fuer /api/v1/chat
LMSTUDIO_CONTEXT_LENGTH = int(os.getenv("LMSTUDIO_CONTEXT_LENGTH", "8000"))

# MCP (Mode 2) - Whitelist der erlaubten HA-MCP-Tools.
# Leer/"{}"/"[]" = kein Filter (LM Studio erlaubt alle vom Server gemeldeten Tools).
_mcp_tools_raw = os.getenv(
    "LMSTUDIO_MCP_ALLOWED_TOOLS",
    "HassTurnOn,HassTurnOff,HassCancelAllTimers,HassBroadcast,"
    "HassClimateSetTemperature,HassLightSet,GetDateTime,GetLiveContext"
).strip()
if _mcp_tools_raw in ("", "{}", "[]"):
    LMSTUDIO_MCP_ALLOWED_TOOLS: list[str] = []
else:
    LMSTUDIO_MCP_ALLOWED_TOOLS = [t.strip() for t in _mcp_tools_raw.split(",") if t.strip()]

LLM_HISTORY_SIZE = int(os.getenv("LLM_HISTORY_SIZE", "0"))
MAX_ACTIONS_PER_COMMAND = int(os.getenv("MAX_ACTIONS_PER_COMMAND", "0"))

# Fallback-Modus wenn parse_command() keine Action findet:
#   0 = aus (bisheriges Verhalten, keine Treffer -> Fehlermeldung)
#   1 = einfacher Fallback: alle HA-Entities per REST holen und LLM erneut fragen
#   2 = MCP-Fallback: LM Studio mit konfiguriertem HA-MCP-Server aufrufen
FALLBACK_MODE = int(os.getenv("FALLBACK_MODE", "0"))

# Mode 1 - REST Fallback Filter/Limit.
# Leer/"{}"/"[]" bei DOMAINS = kein Domain-Filter (alle werden uebergeben).
# 0 bei MAX_ENTITIES = kein Limit.
FALLBACK_REST_MAX_ENTITIES = int(os.getenv("FALLBACK_REST_MAX_ENTITIES", "150"))
_fb_domains_raw = os.getenv(
    "FALLBACK_REST_DOMAINS",
    "light,switch,sensor,binary_sensor,climate,automation,cover"
).strip()
if _fb_domains_raw in ("", "{}", "[]"):
    FALLBACK_REST_DOMAINS: list[str] = []
else:
    FALLBACK_REST_DOMAINS = [d.strip() for d in _fb_domains_raw.split(",") if d.strip()]