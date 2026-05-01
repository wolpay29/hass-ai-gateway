"""
Voice Gateway — FastAPI HTTP adapter on top of core.processor.

All it does is:
  - receive audio (or plain text) from local devices (Raspberry Pi, ESP32, ...),
  - run core.processor.process_transcript(),
  - optionally synthesize the reply via an external TTS server and return WAV,
  - otherwise return the result as JSON,
  - optionally push a Telegram receipt to the owner.

No command logic lives here — that's all in core/processor.py. If you want to
change *what* the bot does, edit core/processor.py; that change will apply to
both the Telegram bot and this gateway simultaneously.

Endpoints
---------
  POST /audio   multipart:  file=<wav/ogg/mp3>, device_id=<str>, tts=<bool>
  POST /text    JSON:       {"text": "...", "device_id": "...", "tts": false}
  GET  /health

Auth
----
Set GATEWAY_API_KEY in the shared .env and send it as X-Api-Key header.
Empty = no auth (fine on a trusted LAN).

TTS mode
--------
Set TTS_EXTERNAL_URL in .env to point to a running tts_server instance.
When a device sends tts=true, the gateway synthesizes the reply and returns
audio/wav instead of JSON. Devices that don't send tts=true always get JSON.

History sharing with Telegram
-----------------------------
core.processor keys conversation history by chat_id (int). If your RPi sends
`device_id` as a numeric string matching your Telegram chat_id, the RPi and
Telegram share the same history. Use any other string and it gets hashed into
a separate history space.
"""
import os
import re
import sys
import logging
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from core.voice import transcribe_audio
from core.config import BOT_TOKEN, MY_CHAT_ID, TTS_EXTERNAL_URL, TTS_EXTERNAL_VOICE, RAG_ENABLED
from core.processor import process_transcript_split

logging.basicConfig(
    format="%(asctime)s [gateway] %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

GATEWAY_API_KEY: str = os.getenv("GATEWAY_API_KEY", "")
GATEWAY_TELEGRAM_PUSH: bool = os.getenv("GATEWAY_TELEGRAM_PUSH", "true").lower() == "true"
GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8765"))

if TTS_EXTERNAL_URL:
    logger.info(f"[TTS] External TTS enabled: {TTS_EXTERNAL_URL} voice={TTS_EXTERNAL_VOICE}")
else:
    logger.info("[TTS] External TTS not configured — returning JSON to all devices")

app = FastAPI(title="Voice Gateway", version="1.0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth(key: str) -> None:
    if GATEWAY_API_KEY and key != GATEWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _device_to_chat_id(device_id: str) -> int:
    """
    Map a device identifier to the int used by core.processor as history key.

    If device_id is numeric (e.g. a Telegram chat_id like "123456789"), use it
    directly — this is how you opt into sharing history with the Telegram bot.

    Otherwise (e.g. "rpi-wohnzimmer"), hash it to a stable positive int so the
    device gets its own isolated history space.
    """
    try:
        return int(device_id)
    except ValueError:
        return abs(hash(device_id)) % (10 ** 9)


def _telegram_push(device_id: str, transcript: str, result: dict) -> None:
    """Optional receipt of the command in the owner's Telegram chat."""
    if not GATEWAY_TELEGRAM_PUSH or not BOT_TOKEN or not MY_CHAT_ID:
        return

    def _esc(s: str) -> str:
        """Escape MarkdownV2 special characters."""
        for ch in r"\_*[]()~`>#+-=|{}.!":
            s = s.replace(ch, f"\\{ch}")
        return s

    lines = [f"🎙️ *{_esc(device_id)}*: {_esc(transcript)}"]
    if result.get("reply"):
        lines.append(f"💬 {_esc(result['reply'])}")
    for a in result.get("actions_executed", []):
        status = a.get("status", "ok")
        icon = "✅" if status == "ok" else ("⏱️❌" if status == "timeout" else "❌")
        lines.append(f"{icon} `{a['action']}` → `{a['entity_id']}`")
    if result.get("error"):
        lines.append(f"⚠️ error: {_esc(result['error'])}")

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": MY_CHAT_ID, "text": "\n".join(lines), "parse_mode": "MarkdownV2"},
            timeout=10,
        )
        if not resp.ok:
            logger.warning(f"[Gateway] Telegram push failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.warning(f"[Gateway] Telegram push failed: {e}")


_UNIT_SUBS: list[tuple[str, str]] = [
    # Order matters: longer/more-specific patterns first
    (r"µg/m³",      "Mikrogramm pro Kubikmeter"),
    (r"mg/m³",      "Milligramm pro Kubikmeter"),
    (r"m³",         "Kubikmeter"),
    (r"km/h",       "Kilometer pro Stunde"),
    (r"m/s",        "Meter pro Sekunde"),
    (r"°C",         "Grad Celsius"),
    (r"°F",         "Grad Fahrenheit"),
    (r"kWh",        "Kilowattstunden"),
    (r"Wh",         "Wattstunden"),
    (r"kW",         "Kilowatt"),
    (r"\bW\b",      "Watt"),
    (r"hPa",        "Hektopascal"),
    (r"mbar",       "Millibar"),
    (r"\blx\b",     "Lux"),
    (r"\bV\b",      "Volt"),
    (r"\bA\b",      "Ampere"),
    (r"\bdB\b",     "Dezibel"),
    (r"ppm",        "ppm"),
    (r"\bL\b",      "Liter"),
    (r"%",          "Prozent"),
]


def _normalize_for_tts(text: str) -> str:
    for pattern, replacement in _UNIT_SUBS:
        text = re.sub(pattern, replacement, text)
    return text


def _tts_to_wav(text: str) -> bytes | None:
    """Call external TTS server and return WAV bytes, or None on failure."""
    if not TTS_EXTERNAL_URL or not text:
        return None
    try:
        resp = requests.post(
            TTS_EXTERNAL_URL,
            json={"text": text, "voice": TTS_EXTERNAL_VOICE},
            timeout=15,
        )
        resp.raise_for_status()
        logger.info(f"[TTS] Synthesized {len(text)} chars → {len(resp.content)} bytes WAV")
        return resp.content
    except Exception as e:
        logger.warning(f"[TTS] External TTS failed: {e}")
        return None


def _reply_or_wav(result: dict, tts: bool) -> Response | JSONResponse:
    """Return WAV if tts=True and TTS service is available, else JSON."""
    if not tts:
        return JSONResponse(result)

    reply_text = result.get("reply") or ""
    if result.get("error") == "no_speech":
        reply_text = "Ich habe dich leider nicht verstanden."
    elif result.get("error"):
        reply_text = f"Fehler: {result['error']}"

    wav = _tts_to_wav(_normalize_for_tts(reply_text))
    if wav:
        return Response(content=wav, media_type="audio/wav")

    # TTS service unavailable — fall back to JSON so device can use local TTS
    logger.warning("[TTS] Falling back to JSON response")
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "tts": bool(TTS_EXTERNAL_URL)}


@app.post("/rag_rebuild")
def rag_rebuild_endpoint(
    x_api_key: str = Header(default=""),
) -> JSONResponse:
    """Trigger a RAG index rebuild.

    Same effect as the Telegram `/rag_rebuild` command but callable from a
    terminal (`curl`) or Home Assistant via `rest_command`. Synchronous - the
    response only returns once the rebuild is finished.
    """
    _auth(x_api_key)
    if not RAG_ENABLED:
        return JSONResponse(
            status_code=400,
            content={"status": "disabled", "error": "RAG_ENABLED=false"},
        )
    try:
        from core.rag.index import build as rag_build, status as rag_status
        count = rag_build()
        info = rag_status()
        logger.info(f"[Gateway] /rag_rebuild OK: {count} entities")
        return JSONResponse({
            "status": "ok",
            "entities": count,
            "last_indexed": info.get("last_indexed"),
        })
    except Exception as e:
        logger.error(f"[Gateway] /rag_rebuild failed: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


@app.post("/audio")
async def audio_endpoint(
    file: UploadFile = File(...),
    device_id: str = Form(default="rpi-default"),
    tts: bool = Form(default=False),
    x_api_key: str = Header(default=""),
) -> Response:
    """
    Receive an audio file (WAV, OGG, MP3) from a device.
    Send tts=true to receive audio/wav back instead of JSON.
    """
    _auth(x_api_key)

    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        logger.info(f"[Gateway] /audio from '{device_id}' — transcribing {suffix}")
        transcript = transcribe_audio(tmp_path)
    finally:
        os.unlink(tmp_path)

    if not transcript:
        logger.warning(f"[Gateway] No speech detected from '{device_id}'")
        return _reply_or_wav({"transcript": "", "reply": "", "error": "no_speech"}, tts)

    logger.info(f"[Gateway] '{device_id}' transcript: '{transcript}'")
    chat_id = _device_to_chat_id(device_id)
    partial, execute_fn = process_transcript_split(transcript, chat_id=chat_id)

    # Return TTS/JSON immediately with the LLM reply, run HA actions in background
    response = _reply_or_wav(partial, tts)

    def _bg():
        if execute_fn:
            execute_fn()
        _telegram_push(device_id, transcript, partial)

    threading.Thread(target=_bg, daemon=True).start()
    return response


class TextRequest(BaseModel):
    text: str
    device_id: str = "rpi-default"
    tts: bool = False


@app.post("/text")
def text_endpoint(
    body: TextRequest,
    x_api_key: str = Header(default=""),
) -> Response:
    """Receive a plain-text command. Send tts=true to receive audio/wav back."""
    _auth(x_api_key)

    transcript = body.text.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="text must not be empty")

    logger.info(f"[Gateway] /text from '{body.device_id}': '{transcript}'")
    chat_id = _device_to_chat_id(body.device_id)
    partial, execute_fn = process_transcript_split(transcript, chat_id=chat_id)

    response = _reply_or_wav(partial, body.tts)

    def _bg():
        if execute_fn:
            execute_fn()
        _telegram_push(body.device_id, transcript, partial)

    threading.Thread(target=_bg, daemon=True).start()
    return response


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=GATEWAY_PORT, reload=False)
