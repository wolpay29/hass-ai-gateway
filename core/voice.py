import logging
import mimetypes
import requests
from pathlib import Path
from core.config import (
    WHISPER_LANGUAGE,
    WHISPER_EXTERNAL_URL,
    WHISPER_EXTERNAL_MODEL,
    VOICE_DOWNLOAD_DIR,
)

logger = logging.getLogger(__name__)


def ensure_voice_dir() -> Path:
    path = Path(VOICE_DOWNLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def transcribe_audio(file_path: str) -> str:
    logger.info(
        f"[Whisper] Sende an: {WHISPER_EXTERNAL_URL} | "
        f"Modell: {WHISPER_EXTERNAL_MODEL}"
    )

    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                WHISPER_EXTERNAL_URL,
                files={"file": (Path(file_path).name, f, mime_type)},
                data={
                    "model": WHISPER_EXTERNAL_MODEL,
                    "language": WHISPER_LANGUAGE,
                    "response_format": "json",
                },
                timeout=30,
            )
        response.raise_for_status()
        result = response.json()
        final_text = result.get("text", "").strip()
        logger.info(f"[Whisper] Ergebnis: {final_text}")
        return final_text
    except Exception as e:
        logger.error(f"[Whisper] Fehler: {e}")
        return ""
