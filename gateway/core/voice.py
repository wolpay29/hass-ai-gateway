import logging
import requests
from pathlib import Path
from core.config import (
    WHISPER_BACKEND,
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_THREADS,
    WHISPER_BEAM_SIZE,
    WHISPER_LANGUAGE,
    WHISPER_EXTERNAL_URL,
    WHISPER_EXTERNAL_MODEL,
    VOICE_DOWNLOAD_DIR,
)

logger = logging.getLogger(__name__)
_model = None


def get_whisper_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info(
            f"[Whisper] Lade lokales Modell: {WHISPER_MODEL} | "
            f"Device: {WHISPER_DEVICE} | "
            f"Threads: {WHISPER_THREADS} | "
            f"Type: {WHISPER_COMPUTE_TYPE}"
        )
        _model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
            cpu_threads=WHISPER_THREADS
        )
    return _model


def ensure_voice_dir() -> Path:
    path = Path(VOICE_DOWNLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _transcribe_local(file_path: str) -> str:
    model = get_whisper_model()
    logger.info(f"[Whisper LOCAL] Start: Beam={WHISPER_BEAM_SIZE}, Lang={WHISPER_LANGUAGE}")

    segments, info = model.transcribe(
        file_path,
        beam_size=WHISPER_BEAM_SIZE,
        language=WHISPER_LANGUAGE,
        vad_filter=True
    )

    text_parts = []
    try:
        for segment in segments:
            if segment.text:
                text_parts.append(segment.text.strip())
    except Exception as e:
        logger.error(f"[Whisper LOCAL] Fehler: {e}")
        return ""

    final_text = " ".join(text_parts).strip()
    logger.info(f"[Whisper LOCAL] Ergebnis: {final_text}")
    return final_text


def _transcribe_external(file_path: str) -> str:
    logger.info(f"[Whisper EXTERNAL] Sende an: {WHISPER_EXTERNAL_URL} | Modell: {WHISPER_EXTERNAL_MODEL}")

    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                WHISPER_EXTERNAL_URL,
                files={"file": (Path(file_path).name, f, "audio/ogg")},
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
        logger.info(f"[Whisper EXTERNAL] Ergebnis: {final_text}")
        return final_text
    except Exception as e:
        logger.error(f"[Whisper EXTERNAL] Fehler: {e}")
        return ""


def transcribe_audio(file_path: str) -> str:
    if WHISPER_BACKEND == "external":
        return _transcribe_external(file_path)
    else:
        return _transcribe_local(file_path)