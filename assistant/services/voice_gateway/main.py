"""
Voice Gateway — FastAPI HTTP adapter on top of core.processor.

All it does is:
  - receive audio (or plain text) from local devices (Raspberry Pi, ESP32, ...),
  - run core.processor.process_transcript(),
  - return the result as JSON,
  - optionally push a Telegram receipt to the owner.

No command logic lives here — that's all in core/processor.py. If you want to
change *what* the bot does, edit core/processor.py; that change will apply to
both the Telegram bot and this gateway simultaneously.

Endpoints
---------
  POST /audio   multipart:  file=<wav/ogg/mp3>, device_id=<str>
  POST /text    JSON:       {"text": "...", "device_id": "..."}
  GET  /health

Auth
----
Set GATEWAY_API_KEY in the shared .env and send it as X-Api-Key header.
Empty = no auth (fine on a trusted LAN).

History sharing with Telegram
-----------------------------
core.processor keys conversation history by chat_id (int). If your RPi sends
`device_id` as a numeric string matching your Telegram chat_id, the RPi and
Telegram share the same history. Use any other string and it gets hashed into
a separate history space.
"""
import os
import sys
import logging
import tempfile
from pathlib import Path

# Make `core/` importable regardless of where uvicorn is launched from.
# core/ lives at project root; this file is at bots/voice_gateway/main.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.voice import transcribe_audio
from core.config import BOT_TOKEN, MY_CHAT_ID
from core.processor import process_transcript

logging.basicConfig(
    format="%(asctime)s [gateway] %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

GATEWAY_API_KEY: str = os.getenv("GATEWAY_API_KEY", "")
GATEWAY_TELEGRAM_PUSH: bool = os.getenv("GATEWAY_TELEGRAM_PUSH", "true").lower() == "true"
GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8765"))

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

    lines = [f"🎙️ *{device_id}*: {transcript}"]
    if result.get("reply"):
        lines.append(f"💬 {result['reply']}")
    for a in result.get("actions_executed", []):
        icon = "✅" if a.get("success") else "❌"
        lines.append(f"{icon} `{a['action']}` → `{a['entity_id']}`")
    if result.get("error"):
        lines.append(f"⚠️ error: {result['error']}")

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": MY_CHAT_ID, "text": "\n".join(lines), "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"[Gateway] Telegram push failed: {e}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/audio")
async def audio_endpoint(
    file: UploadFile = File(...),
    device_id: str = Form(default="rpi-default"),
    x_api_key: str = Header(default=""),
) -> JSONResponse:
    """
    Receive an audio file (WAV, OGG, MP3) from a device.
    Keyword detection happens on-device — this endpoint receives ONLY the
    command audio captured after the wake word fires.
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
        return JSONResponse({"transcript": "", "reply": "", "error": "no_speech"})

    logger.info(f"[Gateway] '{device_id}' transcript: '{transcript}'")
    result = process_transcript(transcript, chat_id=_device_to_chat_id(device_id))
    _telegram_push(device_id, transcript, result)
    return JSONResponse(result)


class TextRequest(BaseModel):
    text: str
    device_id: str = "rpi-default"


@app.post("/text")
def text_endpoint(
    body: TextRequest,
    x_api_key: str = Header(default=""),
) -> JSONResponse:
    """Receive a plain-text command (already transcribed on-device or typed)."""
    _auth(x_api_key)

    transcript = body.text.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="text must not be empty")

    logger.info(f"[Gateway] /text from '{body.device_id}': '{transcript}'")
    result = process_transcript(transcript, chat_id=_device_to_chat_id(body.device_id))
    _telegram_push(body.device_id, transcript, result)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=GATEWAY_PORT, reload=False)
