"""
Raspberry Pi voice client — keyword detection + audio capture + gateway call + TTS.

Flow:
  1. Listen continuously with openwakeword for the wake word
  2. On detection: play an acknowledgement beep, start recording
  3. Record until VAD silence (1.5 s of quiet after speech begins)
  4. POST the WAV to the voice gateway /audio endpoint
  5. Speak back the reply via pyttsx3 (offline TTS)
  6. Repeat

Requirements: see requirements.txt
Config: edit the CONFIG block below or set the matching env vars.
"""
import io
import os
import time
import wave
import logging
import threading
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd
import pyttsx3
from openwakeword.model import Model as WakeWordModel

logging.basicConfig(
    format="%(asctime)s [rpi-client] %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIG  — override via environment variables or edit directly
# ---------------------------------------------------------------------------
GATEWAY_URL: str     = os.getenv("GATEWAY_URL",     "http://10.1.10.78:8765")
GATEWAY_API_KEY: str = os.getenv("GATEWAY_API_KEY", "")
DEVICE_ID: str       = os.getenv("DEVICE_ID",       "rpi-wohnzimmer")

# Wake word model — openwakeword built-in choices:
#   "hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy", "timer", "weather"
# You can also pass a path to a custom .onnx model file.
WAKE_WORD: str = os.getenv("WAKE_WORD", "hey_jarvis")

SAMPLE_RATE: int = 16000   # Hz — openwakeword and Whisper both expect 16 kHz
CHUNK_MS: int    = 80      # ms per processing chunk (openwakeword default)
CHUNK_FRAMES: int = int(SAMPLE_RATE * CHUNK_MS / 1000)

# VAD settings for recording after wake word
VAD_SILENCE_THRESHOLD: float = 0.015   # RMS amplitude below this = silence
VAD_SILENCE_DURATION: float  = 1.5     # seconds of silence to end recording
VAD_MAX_DURATION: float      = 10.0    # hard cutoff seconds
VAD_MIN_DURATION: float      = 0.4     # ignore clips shorter than this

# Detection threshold (0–1). Lower = more sensitive but more false positives.
WAKE_THRESHOLD: float = float(os.getenv("WAKE_THRESHOLD", "0.5"))

# TTS engine rate (words per minute). Adjust to taste.
TTS_RATE: int = int(os.getenv("TTS_RATE", "165"))

# Beep: frequency (Hz) and duration (ms) played on wake detection
BEEP_FREQ: int = 880
BEEP_MS: int   = 120


# ---------------------------------------------------------------------------
# TTS — initialised once, reused across replies
# ---------------------------------------------------------------------------
_tts_engine = pyttsx3.init()
_tts_engine.setProperty("rate", TTS_RATE)
# Pick a German voice if available; fall back to system default
for voice in _tts_engine.getProperty("voices"):
    if "german" in voice.name.lower() or "de" in voice.id.lower():
        _tts_engine.setProperty("voice", voice.id)
        break


def _speak(text: str) -> None:
    if not text:
        return
    logger.info(f"[TTS] Speaking: {text!r}")
    _tts_engine.say(text)
    _tts_engine.runAndWait()


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _beep() -> None:
    """Play a short sine-wave beep to acknowledge the wake word."""
    t = np.linspace(0, BEEP_MS / 1000, int(SAMPLE_RATE * BEEP_MS / 1000), False)
    tone = (0.4 * np.sin(2 * np.pi * BEEP_FREQ * t)).astype(np.float32)
    sd.play(tone, samplerate=SAMPLE_RATE)
    sd.wait()


def _rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def _record_command() -> bytes | None:
    """
    Record audio until VAD silence is detected.
    Returns raw 16-bit PCM bytes (mono, 16 kHz) or None if too short.
    """
    logger.info("[Record] Listening for command…")
    frames: list[np.ndarray] = []
    silence_start: float | None = None
    speech_started = False
    start_time = time.time()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=CHUNK_FRAMES) as stream:
        while True:
            chunk, _ = stream.read(CHUNK_FRAMES)
            chunk = chunk[:, 0]  # mono
            rms = _rms(chunk)
            frames.append(chunk)
            elapsed = time.time() - start_time

            if rms > VAD_SILENCE_THRESHOLD:
                speech_started = True
                silence_start = None
            elif speech_started:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= VAD_SILENCE_DURATION:
                    logger.info("[Record] Silence detected — end of command")
                    break

            if elapsed >= VAD_MAX_DURATION:
                logger.info("[Record] Max duration reached")
                break

    pcm = np.concatenate(frames)
    duration = len(pcm) / SAMPLE_RATE
    if duration < VAD_MIN_DURATION:
        logger.warning(f"[Record] Clip too short ({duration:.2f}s), ignoring")
        return None

    logger.info(f"[Record] Captured {duration:.2f}s of audio")
    return pcm.tobytes()


def _pcm_to_wav(pcm: bytes) -> bytes:
    """Wrap raw 16-bit mono PCM in a WAV container for the gateway."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Gateway call
# ---------------------------------------------------------------------------

def _send_audio(wav_bytes: bytes) -> str:
    """POST WAV to the gateway /audio endpoint. Returns the reply text."""
    headers = {}
    if GATEWAY_API_KEY:
        headers["X-Api-Key"] = GATEWAY_API_KEY

    try:
        resp = requests.post(
            f"{GATEWAY_URL}/audio",
            files={"file": ("command.wav", wav_bytes, "audio/wav")},
            data={"device_id": DEVICE_ID},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[Gateway] Response: {data}")

        if data.get("error") == "no_speech":
            return "Ich habe dich leider nicht verstanden."
        if data.get("error"):
            return f"Fehler: {data['error']}"

        return data.get("reply") or ""

    except requests.exceptions.ConnectionError:
        logger.error(f"[Gateway] Cannot connect to {GATEWAY_URL}")
        return "Gateway nicht erreichbar."
    except Exception as e:
        logger.error(f"[Gateway] Request failed: {e}")
        return "Fehler beim Senden."


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info(f"[Init] Loading wake word model: '{WAKE_WORD}'")
    oww = WakeWordModel(wakeword_models=[WAKE_WORD], inference_framework="onnx")
    logger.info(f"[Init] Listening for '{WAKE_WORD}' on device '{DEVICE_ID}'")
    logger.info(f"[Init] Gateway: {GATEWAY_URL}")

    chunk_buffer = np.zeros(CHUNK_FRAMES, dtype=np.int16)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=CHUNK_FRAMES) as stream:
        while True:
            chunk, _ = stream.read(CHUNK_FRAMES)
            chunk = chunk[:, 0]

            # openwakeword expects float32 in [-1, 1]
            audio_f32 = chunk.astype(np.float32) / 32768.0
            prediction = oww.predict(audio_f32)

            # prediction is a dict {model_name: score}
            score = max(prediction.values()) if prediction else 0.0

            if score >= WAKE_THRESHOLD:
                logger.info(f"[WakeWord] Detected '{WAKE_WORD}' (score={score:.2f})")
                oww.reset()  # clear sliding window so it doesn't fire again immediately

                _beep()

                pcm = _record_command()
                if pcm is None:
                    _speak("Entschuldigung, ich habe nichts gehört.")
                    continue

                wav = _pcm_to_wav(pcm)
                reply = _send_audio(wav)
                _speak(reply)


if __name__ == "__main__":
    main()
