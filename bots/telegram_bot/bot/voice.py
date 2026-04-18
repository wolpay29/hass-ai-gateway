import logging
from pathlib import Path
from faster_whisper import WhisperModel
from bot.config import (
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_THREADS,
    WHISPER_BEAM_SIZE,
    WHISPER_LANGUAGE,
    VOICE_DOWNLOAD_DIR,
)

logger = logging.getLogger(__name__)
_model = None

def get_whisper_model():
    global _model

    if _model is None:
        logger.info(
            f"[Whisper] Lade Modell: {WHISPER_MODEL} | "
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


def transcribe_audio(file_path: str) -> str:
    model = get_whisper_model()
    
    logger.info(f"[Whisper] Start: Beam={WHISPER_BEAM_SIZE}, Lang={WHISPER_LANGUAGE}")

    segments, info = model.transcribe(
        file_path, 
        beam_size=WHISPER_BEAM_SIZE,
        language=WHISPER_LANGUAGE,
        vad_filter=True
    )

    text_parts = []
    try:
        # Segmente abarbeiten und zu einem String zusammenfügen
        for segment in segments:
            if segment.text:
                text_parts.append(segment.text.strip())
    except Exception as e:
        logger.error(f"[Whisper] Fehler: {e}")
        return ""

    final_text = " ".join(text_parts).strip()
    logger.info(f"[Whisper] Ergebnis: {final_text}")
    return final_text