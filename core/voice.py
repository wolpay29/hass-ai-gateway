import logging
import mimetypes
import re
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
    USERCONFIG_DIR,
)

logger = logging.getLogger(__name__)
_model = None
_initial_prompt_cache: str | None = None


def _load_initial_prompt() -> str:
    """Read userconfig/whisper_vocabulary.md and return it as Whisper initial_prompt.

    HTML comments are stripped, so a file that only contains a template comment
    block produces an empty prompt (Whisper default behaviour). Cached after
    the first call - restart the service to pick up edits.
    """
    global _initial_prompt_cache
    if _initial_prompt_cache is not None:
        return _initial_prompt_cache
    path = USERCONFIG_DIR / "whisper_vocabulary.md"
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        cleaned = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL).strip()
    else:
        cleaned = ""
    _initial_prompt_cache = cleaned
    if cleaned:
        logger.info(f"[Whisper] initial_prompt geladen ({len(cleaned)} Zeichen)")
    return cleaned


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
    initial_prompt = _load_initial_prompt() or None
    logger.info(
        f"[Whisper LOCAL] Start: Beam={WHISPER_BEAM_SIZE}, Lang={WHISPER_LANGUAGE}, "
        f"initial_prompt={'set' if initial_prompt else 'none'}"
    )

    segments, info = model.transcribe(
        file_path,
        beam_size=WHISPER_BEAM_SIZE,
        language=WHISPER_LANGUAGE,
        vad_filter=True,
        initial_prompt=initial_prompt,
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
    initial_prompt = _load_initial_prompt() or None
    logger.info(
        f"[Whisper EXTERNAL] Sende an: {WHISPER_EXTERNAL_URL} | "
        f"Modell: {WHISPER_EXTERNAL_MODEL} | "
        f"initial_prompt={'set' if initial_prompt else 'none'}"
    )

    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    try:
        with open(file_path, "rb") as f:
            data = {
                "model": WHISPER_EXTERNAL_MODEL,
                "language": WHISPER_LANGUAGE,
                "response_format": "json",
            }
            if initial_prompt:
                data["prompt"] = initial_prompt
            response = requests.post(
                WHISPER_EXTERNAL_URL,
                files={"file": (Path(file_path).name, f, mime_type)},
                data=data,
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