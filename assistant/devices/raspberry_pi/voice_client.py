"""
Raspberry Pi voice client — keyword detection + audio capture + gateway call + TTS.

Flow:
  1. Listen continuously with openwakeword for the wake word
  2. On detection: play an acknowledgement beep, start recording
  3. Record until VAD silence (1.5 s of quiet after speech begins)
  4. POST the WAV to the voice gateway /audio endpoint
  5. Speak back the reply via Piper TTS (or pyttsx3 if no model configured)
  6. Repeat

Requirements: see requirements.txt
Config: edit the CONFIG block below or set the matching env vars.
"""
import io
import os
import re
import time
import wave
import logging
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd
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

# sounddevice device indices for the ReSpeaker HAT.
# Run: python3 -c "import sounddevice; print(sounddevice.query_devices())"
# Input (mic) and output (speaker/beep) may have different indices on the same card.
# Leave unset to use the system ALSA default (requires ~/.asoundrc).
def _parse_device(env_key: str) -> "int | None":
    v = os.getenv(env_key, "").strip()
    return int(v) if v.lstrip("-").isdigit() else None

AUDIO_INPUT_DEVICE: int | None  = _parse_device("AUDIO_INPUT_DEVICE")
AUDIO_OUTPUT_DEVICE: int | None = _parse_device("AUDIO_OUTPUT_DEVICE")

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

# Piper TTS model path — set this to use high-quality neural TTS.
# Download a voice from: https://huggingface.co/rhasspy/piper-voices
# Example: ~/voice/models/de_DE-thorsten-high.onnx
# Leave empty to fall back to pyttsx3/espeak.
TTS_MODEL: str = os.getenv("TTS_MODEL", "")

# pyttsx3 fallback settings (only used when TTS_MODEL is not set)
TTS_RATE: int = int(os.getenv("TTS_RATE", "165"))

# Beep: frequency (Hz) and duration (ms) played on wake detection
BEEP_FREQ: int = 880
BEEP_MS: int   = 120


# ---------------------------------------------------------------------------
# TTS — Piper (primary) or pyttsx3 (fallback)
# ---------------------------------------------------------------------------

_piper_voice = None
_pyttsx3_engine = None


def _init_tts() -> None:
    global _piper_voice, _pyttsx3_engine

    if TTS_MODEL and Path(TTS_MODEL).is_file():
        from piper.voice import PiperVoice
        logger.info(f"[TTS] Loading Piper model: {TTS_MODEL}")
        _piper_voice = PiperVoice.load(TTS_MODEL)
        logger.info(f"[TTS] Piper ready (sample_rate={_piper_voice.config.sample_rate})")
    else:
        if TTS_MODEL:
            logger.warning(f"[TTS] Piper model not found at '{TTS_MODEL}', falling back to pyttsx3")
        else:
            logger.info("[TTS] No TTS_MODEL set, using pyttsx3/espeak")

        # Route espeak to the correct ALSA output device derived from the sounddevice index
        if AUDIO_OUTPUT_DEVICE is not None:
            info = sd.query_devices(AUDIO_OUTPUT_DEVICE)
            m = re.search(r"hw:(\d+),(\d+)", info.get("name", ""))
            if m:
                os.environ["AUDIODEV"] = f"hw:{m.group(1)},{m.group(2)}"
                logger.info(f"[TTS] espeak routed to AUDIODEV={os.environ['AUDIODEV']}")

        import pyttsx3
        _pyttsx3_engine = pyttsx3.init()
        _pyttsx3_engine.setProperty("rate", TTS_RATE)
        for voice in _pyttsx3_engine.getProperty("voices"):
            if "german" in voice.name.lower() or "de" in voice.id.lower():
                _pyttsx3_engine.setProperty("voice", voice.id)
                break


def _speak(text: str) -> None:
    if not text:
        return
    logger.info(f"[TTS] Speaking: {text!r}")

    if _piper_voice is not None:
        raw = b"".join(_piper_voice.synthesize_stream_raw(text))
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        sd.play(audio, samplerate=_piper_voice.config.sample_rate, device=AUDIO_OUTPUT_DEVICE)
        sd.wait()
    else:
        _pyttsx3_engine.say(text)
        _pyttsx3_engine.runAndWait()


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _beep() -> None:
    t = np.linspace(0, BEEP_MS / 1000, int(SAMPLE_RATE * BEEP_MS / 1000), False)
    tone = (0.4 * np.sin(2 * np.pi * BEEP_FREQ * t)).astype(np.float32)
    sd.play(tone, samplerate=SAMPLE_RATE, device=AUDIO_OUTPUT_DEVICE)
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
                        blocksize=CHUNK_FRAMES, device=AUDIO_INPUT_DEVICE) as stream:
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
    _init_tts()

    logger.info(f"[Init] Loading wake word model: '{WAKE_WORD}'")
    oww = WakeWordModel(wakeword_models=[WAKE_WORD], inference_framework="onnx")
    logger.info(f"[Init] Listening for '{WAKE_WORD}' on device '{DEVICE_ID}'")
    logger.info(f"[Init] Gateway: {GATEWAY_URL}")

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=CHUNK_FRAMES, device=AUDIO_INPUT_DEVICE) as stream:
        while True:
            chunk, _ = stream.read(CHUNK_FRAMES)
            chunk = chunk[:, 0]

            # openwakeword expects float32 in [-1, 1]
            audio_f32 = chunk.astype(np.float32) / 32768.0
            prediction = oww.predict(audio_f32)

            score = max(prediction.values()) if prediction else 0.0

            if score >= WAKE_THRESHOLD:
                logger.info(f"[WakeWord] Detected '{WAKE_WORD}' (score={score:.2f})")
                oww.reset()

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
