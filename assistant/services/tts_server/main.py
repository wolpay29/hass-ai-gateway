"""
Piper TTS Server — converts text to WAV via the piper binary.

Endpoints
---------
  POST /tts     JSON: {"text": "...", "voice": "de_DE-thorsten-low"} → audio/wav
  GET  /health

Setup
-----
  1. Place .onnx and .onnx.json model files in the MODELS_DIR volume.
  2. Set DEFAULT_VOICE to the model filename without extension.
  3. Run with Docker or: pip install -r requirements.txt && python main.py
"""
import io
import json
import logging
import os
import shutil
import subprocess
import wave
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(
    format="%(asctime)s [tts-server] %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MODELS_DIR: Path = Path(os.getenv("MODELS_DIR", "/models"))
DEFAULT_VOICE: str = os.getenv("DEFAULT_VOICE", "de_DE-thorsten-low")
TTS_PORT: int = int(os.getenv("TTS_PORT", "10400"))

# Resample output to this rate before sending.
# Required for devices whose hardware only supports multiples of 8000 Hz
# (e.g. ReSpeaker HAT on Raspberry Pi — 22050 Hz models play silently there).
# Set to 0 to disable resampling and send at the model's native rate.
_resample_env = os.getenv("RESAMPLE_RATE", "16000")
RESAMPLE_RATE: int = int(_resample_env) if _resample_env.strip().isdigit() else 0

PIPER_BIN: str = shutil.which("piper") or "piper"
logger.info(f"[Init] Piper binary:   {PIPER_BIN}")
logger.info(f"[Init] Models dir:     {MODELS_DIR}")
logger.info(f"[Init] Default voice:  {DEFAULT_VOICE}")
logger.info(f"[Init] Resample rate:  {RESAMPLE_RATE or 'disabled (native)'}")

app = FastAPI(title="Piper TTS Server", version="1.0")

_sample_rate_cache: dict[str, int] = {}


def _get_sample_rate(model_path: Path) -> int:
    key = str(model_path)
    if key not in _sample_rate_cache:
        config_path = model_path.with_suffix(".onnx.json")
        with open(config_path, encoding="utf-8") as f:
            _sample_rate_cache[key] = json.load(f)["audio"]["sample_rate"]
    return _sample_rate_cache[key]


class TTSRequest(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "models_dir": str(MODELS_DIR), "default_voice": DEFAULT_VOICE}


@app.post("/tts")
def tts(req: TTSRequest) -> Response:
    model_path = MODELS_DIR / f"{req.voice}.onnx"
    if not model_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Voice model '{req.voice}' not found in {MODELS_DIR}. "
                   f"Download it and place both .onnx and .onnx.json files there.",
        )

    try:
        sample_rate = _get_sample_rate(model_path)
        proc = subprocess.run(
            [PIPER_BIN, "--model", str(model_path), "--output-raw"],
            input=req.text.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"piper exited {proc.returncode}: {proc.stderr.decode()[:200]}")

        raw = proc.stdout
        out_rate = sample_rate

        if RESAMPLE_RATE and RESAMPLE_RATE != sample_rate:
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            g = gcd(sample_rate, RESAMPLE_RATE)
            audio = resample_poly(audio, RESAMPLE_RATE // g, sample_rate // g)
            raw = (audio.clip(-32768, 32767).astype(np.int16)).tobytes()
            out_rate = RESAMPLE_RATE

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(out_rate)
            wf.writeframes(raw)

        logger.info(f"[TTS] '{req.voice}' — {len(req.text)} chars @ {sample_rate}Hz → {out_rate}Hz")
        return Response(content=buf.getvalue(), media_type="audio/wav")

    except Exception as e:
        logger.error(f"[TTS] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=TTS_PORT, reload=False)
