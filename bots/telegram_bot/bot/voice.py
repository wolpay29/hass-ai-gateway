from pathlib import Path
from faster_whisper import WhisperModel
from bot.config import (
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    VOICE_DOWNLOAD_DIR,
)

_model = None


def get_whisper_model():
    global _model

    if _model is None:
        _model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )

    return _model


def ensure_voice_dir() -> Path:
    path = Path(VOICE_DOWNLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def transcribe_audio(file_path: str) -> str:
    model = get_whisper_model()
    segments, info = model.transcribe(file_path, beam_size=5)

    text_parts = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            text_parts.append(text)

    return " ".join(text_parts).strip()
