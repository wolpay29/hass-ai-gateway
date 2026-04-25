"""

Raspberry Pi voice client — keyword detection + audio capture + gateway call + TTS.

Flow:
  1. Listen continuously with openwakeword for the wake word
  2. On detection: play an acknowledgement beep, start recording
  3. Record until VAD silence (1.0 s of quiet after speech begins)
  4. POST the WAV to the voice gateway /audio endpoint with tts=true
  5. If gateway returns audio/wav (external TTS active): play it directly via aplay
     If gateway returns JSON (no external TTS): synthesize locally via Piper/pyttsx3
  6. Repeat

Requirements: see requirements.txt
Config: edit the CONFIG block below or set the matching env vars.
"""

import io
import json
import os
import re
import subprocess
import sys
import time
import wave
import logging
from pathlib import Path

# Load .env from the same directory as this script automatically.
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import numpy as np
import requests
import sounddevice as sd
from openwakeword.model import Model as WakeWordModel

# ---------------------------------------------------------------------------
# LED — ReSpeaker 2-Mic HAT (3x APA102 via spidev)
# ---------------------------------------------------------------------------
try:
    import spidev
    _LED_DEV = spidev.SpiDev()
    _LED_DEV.open(0, 0)          # Bus 0, Device 0 (ReSpeaker 2Mic HAT)
    _LED_DEV.max_speed_hz = 8000000
    _LED_AVAILABLE = True
except Exception:
    _LED_DEV = None
    _LED_AVAILABLE = False

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

# ALSA device strings — use plughw:X,0 format for both input and output.
# AUDIO_INPUT_DEVICE ist als Alias erlaubt, falls in der .env so benannt.
ALSA_INPUT_DEVICE: str  = os.getenv("ALSA_INPUT_DEVICE") or os.getenv("AUDIO_INPUT_DEVICE", "plughw:1,0")
ALSA_OUTPUT_DEVICE: str = os.getenv("ALSA_OUTPUT_DEVICE") or os.getenv("AUDIO_OUTPUT_DEVICE", "plughw:1,0")

# Derive the sounddevice index from the ALSA card number in ALSA_INPUT_DEVICE.
# sounddevice needs an integer index for its InputStream used in wake word detection.
def _resolve_input_device(alsa_dev: str) -> "int | None":
    m = re.search(r":(\d+),", alsa_dev)
    if not m:
        return None
    card = m.group(1)
    for i, dev in enumerate(sd.query_devices()):
        name = dev.get("name", "")
        if f"hw:{card}," in name and dev.get("max_input_channels", 0) > 0:
            return i
    return None

AUDIO_INPUT_DEVICE: int | None = _resolve_input_device(ALSA_INPUT_DEVICE)
logger.info(f"[Audio] Input: {ALSA_INPUT_DEVICE} → sounddevice index {AUDIO_INPUT_DEVICE}")

# Wake word model — openwakeword built-in choices:
#   "hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy", "timer", "weather"
# You can also pass a path to a custom .onnx model file.
WAKE_WORD: str = os.getenv("WAKE_WORD", "hey_jarvis")

SAMPLE_RATE: int = 16000   # Hz — openwakeword and Whisper both expect 16 kHz
CHUNK_MS: int    = 80      # ms per processing chunk (openwakeword default)
CHUNK_FRAMES: int = int(SAMPLE_RATE * CHUNK_MS / 1000)

# VAD settings for recording after wake word.
# Threshold is in int16 RMS units (0-32767). 500 = roughly -36 dBFS.
# Raise if it cuts off too early in a noisy room, lower if it records too long.
VAD_SILENCE_THRESHOLD: float = float(os.getenv("VAD_SILENCE_THRESHOLD", "500"))
VAD_SILENCE_DURATION: float  = float(os.getenv("VAD_SILENCE_DURATION", "1.0"))
VAD_MAX_DURATION: float      = float(os.getenv("VAD_MAX_DURATION", "10.0"))
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

# Beep: two-note ascending chime played on wake detection (Alexa-style)
BEEP_FREQ: int = 800    # first note (Hz)
BEEP_FREQ2: int = 1200  # second note (Hz)
BEEP_MS: int   = 130    # duration of each note (ms)

# Debug: set DEBUG=true to print wake word score and RMS on every audio chunk.
# Useful for tuning WAKE_THRESHOLD and VAD_SILENCE_THRESHOLD.
DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

# Speaker volume set at startup via amixer. Format: "80%" or leave empty to skip.
SPEAKER_VOLUME: str = os.getenv("SPEAKER_VOLUME", "100%")
# ALSA card number derived from ALSA_OUTPUT_DEVICE (e.g. plughw:1,0 → card 1)
_card_match = re.search(r":(\d+),", ALSA_OUTPUT_DEVICE)
_ALSA_CARD: str = _card_match.group(1) if _card_match else "1"


# ---------------------------------------------------------------------------
# LED Farben aus .env laden
# ---------------------------------------------------------------------------

def _parse_color(value: str) -> tuple[int, int, int]:
    """Parst 'R,G,B' aus der .env zu einem (r, g, b)-Tuple."""
    try:
        parts = [int(p.strip()) for p in value.split(",")]
        if len(parts) == 3:
            return (max(0, min(255, parts[0])),
                    max(0, min(255, parts[1])),
                    max(0, min(255, parts[2])))
    except Exception:
        pass
    return (0, 0, 0)


LED_BRIGHTNESS: int = max(0, min(31, int(os.getenv("LED_BRIGHTNESS", "15"))))

COLOR_RECORDING  = _parse_color(os.getenv("LED_COLOR_RECORDING",  "0,0,255"))
COLOR_PROCESSING = _parse_color(os.getenv("LED_COLOR_PROCESSING", "255,165,0"))
COLOR_SPEAKING   = _parse_color(os.getenv("LED_COLOR_SPEAKING",   "0,255,0"))
COLOR_OFF        = _parse_color(os.getenv("LED_COLOR_OFF",        "0,0,0"))

logger.info(f"[LED] Brightness={LED_BRIGHTNESS}, Recording={COLOR_RECORDING}, "
            f"Processing={COLOR_PROCESSING}, Speaking={COLOR_SPEAKING}, Off={COLOR_OFF}")


# ---------------------------------------------------------------------------
# LED — ReSpeaker 2-Mic HAT (3x APA102). No-ops if spidev not available.
# ---------------------------------------------------------------------------

def _led(r: int, g: int, b: int, brightness: int = LED_BRIGHTNESS) -> None:
    """Set all 3 APA102 LEDs to the same color.
    APA102 frame: [0xE0 | brightness, B, G, R] per LED.
    """
    if not _LED_AVAILABLE:
        return
    # brightness: 0-31, top 3 bits must be 0b111 (0xE0)
    br = 0xE0 | (brightness & 0x1F)
    start = [0, 0, 0, 0]
    pixel = [br, b & 0xFF, g & 0xFF, r & 0xFF]
    end = [0xFF, 0xFF, 0xFF, 0xFF]
    data = start + pixel * 3 + end
    _LED_DEV.xfer2(data)


def _led_off() -> None:
    """Turn all LEDs off (uses COLOR_OFF from .env)."""
    if not _LED_AVAILABLE:
        return
    _led(*COLOR_OFF, brightness=0)


# ---------------------------------------------------------------------------
# Audio output — all playback goes through aplay (proven to work with HAT)
# ---------------------------------------------------------------------------

def _aplay(wav_bytes: bytes) -> None:
    """Play a WAV byte buffer through aplay. plughw handles rate/format conversion."""
    subprocess.run(
        ["aplay", "-D", ALSA_OUTPUT_DEVICE, "-q", "-"],
        input=wav_bytes,
        check=False,
    )


def _make_tone(freq: int, ms: int, volume: float = 0.25) -> np.ndarray:
    n = int(SAMPLE_RATE * ms / 1000)
    t = np.linspace(0, ms / 1000, n, False)
    tone = np.sin(2 * np.pi * freq * t)
    fade = int(n * 0.25)
    envelope = np.ones(n)
    envelope[:fade] = np.linspace(0, 1, fade)
    envelope[-fade:] = np.linspace(1, 0, fade)
    return (tone * envelope * volume * 32767).astype(np.int16)


def _play_chime(first: int, second: int) -> None:
    gap = np.zeros(int(SAMPLE_RATE * 0.04), dtype=np.int16)
    chime = np.concatenate([_make_tone(first, BEEP_MS), gap, _make_tone(second, BEEP_MS)])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(chime.tobytes())
    _aplay(buf.getvalue())


def _beep() -> None:
    _play_chime(BEEP_FREQ, BEEP_FREQ2)  # ascending — wake detected


def _beep_end() -> None:
    _play_chime(BEEP_FREQ2, BEEP_FREQ)  # descending — recording stopped


def _set_volume() -> None:
    if not SPEAKER_VOLUME:
        return

    # 1. Die "Leitungen" (Mixer) physisch einschalten (MUSS auf 'on' sein)
    # Ohne das bleibt der Lautsprecher stumm, egal wie laut man stellt.
    subprocess.run(["amixer", "-c", _ALSA_CARD, "sset", "Left Output Mixer PCM", "on"], capture_output=True)
    subprocess.run(["amixer", "-c", _ALSA_CARD, "sset", "Right Output Mixer PCM", "on"], capture_output=True)

    # 2. Digitales Playback immer auf 100% lassen (verhindert Rauschen/Stille)
    subprocess.run(["amixer", "-c", _ALSA_CARD, "sset", "Playback", "100%"], capture_output=True)

    # 3. Die eigentliche Lautstärke nur an den Endstufen regeln
    controls = ["Speaker", "Headphone"]
    for ctrl in controls:
        result = subprocess.run(
            ["amixer", "-c", _ALSA_CARD, "sset", ctrl, SPEAKER_VOLUME],
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info(f"[Volume] {ctrl} set to {SPEAKER_VOLUME}")


# ---------------------------------------------------------------------------
# TTS — Piper binary (primary) or pyttsx3 (fallback)
# ---------------------------------------------------------------------------

# Path to the piper binary — lives in the same venv bin as this Python.
_PIPER_BIN = str(Path(sys.executable).parent / "piper")

_piper_sample_rate: int | None = None
_pyttsx3_engine = None


def _init_tts() -> None:
    global _piper_sample_rate, _pyttsx3_engine

    if TTS_MODEL and Path(TTS_MODEL).is_file():
        config_path = Path(TTS_MODEL).with_suffix(".onnx.json")
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        _piper_sample_rate = config["audio"]["sample_rate"]
        logger.info(f"[TTS] Piper model: {TTS_MODEL} (sample_rate={_piper_sample_rate})")
    else:
        if TTS_MODEL:
            logger.warning(f"[TTS] Piper model not found at '{TTS_MODEL}', falling back to pyttsx3")
        else:
            logger.info("[TTS] No TTS_MODEL set, using pyttsx3/espeak")

        import pyttsx3
        os.environ["AUDIODEV"] = ALSA_OUTPUT_DEVICE.replace("plughw:", "hw:")
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

    if _piper_sample_rate is not None:
        p1 = subprocess.Popen(
            [_PIPER_BIN, "--model", TTS_MODEL, "--output-raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        p2 = subprocess.Popen(
            ["aplay", "-D", ALSA_OUTPUT_DEVICE, "-q",
             "-r", str(_piper_sample_rate), "-f", "S16_LE", "-c", "1"],
            stdin=p1.stdout,
        )
        p1.stdout.close()
        p1.communicate(input=text.encode())
        p2.wait()
    else:
        _pyttsx3_engine.say(text)
        _pyttsx3_engine.runAndWait()


# ---------------------------------------------------------------------------
# Audio input helpers
# ---------------------------------------------------------------------------

def _rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def _record_command(stream: sd.InputStream) -> bytes | None:
    """
    Record audio from the already-open wake word stream until VAD silence.
    Returns raw 16-bit PCM bytes (mono, 16 kHz) or None if too short.
    """
    logger.info("[Record] Listening for command…")
    frames: list[np.ndarray] = []
    silence_start: float | None = None
    speech_started = False
    start_time = time.time()

    while True:
        chunk, _ = stream.read(CHUNK_FRAMES)
        chunk = chunk[:, 0]  # mono
        rms = _rms(chunk)
        frames.append(chunk)
        elapsed = time.time() - start_time

        if DEBUG:
            logger.info(f"[Debug] state=recording   rms={rms:.0f}/{VAD_SILENCE_THRESHOLD}  speech_started={speech_started}")

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

def _send_audio(wav_bytes: bytes) -> tuple[bytes | None, str]:
    """
    POST WAV to the gateway with tts=true.
    Returns (wav_bytes, text) — wav_bytes is set when gateway returns audio/wav
    (external TTS active), text is set when gateway returns JSON (local TTS fallback).
    """
    headers = {}
    if GATEWAY_API_KEY:
        headers["X-Api-Key"] = GATEWAY_API_KEY

    try:
        resp = requests.post(
            f"{GATEWAY_URL}/audio",
            files={"file": ("command.wav", wav_bytes, "audio/wav")},
            data={"device_id": DEVICE_ID, "tts": "true"},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()

        if resp.headers.get("content-type", "").startswith("audio/"):
            logger.info(f"[Gateway] Received WAV reply ({len(resp.content)} bytes)")
            return resp.content, ""

        data = resp.json()
        logger.info(f"[Gateway] Received JSON reply: {data}")
        if data.get("error") == "no_speech":
            return None, "Ich habe dich leider nicht verstanden."
        if data.get("error"):
            return None, f"Fehler: {data['error']}"
        return None, data.get("reply") or ""

    except requests.exceptions.ConnectionError:
        logger.error(f"[Gateway] Cannot connect to {GATEWAY_URL}")
        return None, "Gateway nicht erreichbar."
    except Exception as e:
        logger.error(f"[Gateway] Request failed: {e}")
        return None, "Fehler beim Senden."


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    # LEDs beim Start ausschalten
    _led_off()

    _set_volume()
    _init_tts()

    logger.info(f"[Init] Loading wake word model: '{WAKE_WORD}'")
    oww = WakeWordModel(wakeword_models=[WAKE_WORD], inference_framework="onnx")
    logger.info(f"[Init] Listening for '{WAKE_WORD}' on device '{DEVICE_ID}'")
    logger.info(f"[Init] Gateway: {GATEWAY_URL}")
    logger.info(f"[Init] Audio output: {ALSA_OUTPUT_DEVICE}")

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=CHUNK_FRAMES, device=AUDIO_INPUT_DEVICE) as stream:
        while True:
            chunk, _ = stream.read(CHUNK_FRAMES)
            chunk = chunk[:, 0]

            # openwakeword expects raw int16 audio
            prediction = oww.predict(chunk)

            score = max(prediction.values()) if prediction else 0.0

            if DEBUG:
                rms = _rms(chunk)
                logger.info(f"[Debug] state=listening  score={score:.3f}/{WAKE_THRESHOLD}  rms={rms:.0f}/{VAD_SILENCE_THRESHOLD}")

            if score >= WAKE_THRESHOLD:
                logger.info(f"[WakeWord] Detected '{WAKE_WORD}' (score={score:.2f})")
                oww.reset()

                _led(*COLOR_RECORDING, LED_BRIGHTNESS)   # blau — recording
                _beep()

                pcm = _record_command(stream)
                _beep_end()
                _led(*COLOR_PROCESSING, LED_BRIGHTNESS)  # orange — processing
                if pcm is None:
                    _led_off()
                    _speak("Entschuldigung, ich habe nichts gehört.")
                    continue

                wav_reply, text_reply = _send_audio(_pcm_to_wav(pcm))
                _led(*COLOR_SPEAKING, LED_BRIGHTNESS)    # grün — speaking
                if wav_reply:
                    _aplay(wav_reply)
                elif text_reply:
                    _speak(text_reply)
                _led_off()                               # done


if __name__ == "__main__":
    main()