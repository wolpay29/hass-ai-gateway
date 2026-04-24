# TTS Server

Piper TTS wrapped in a FastAPI HTTP server. Called by the Voice Gateway to synthesize reply text into WAV audio.

## Setup

```bash
# 1. Download a voice model
mkdir -p models
wget -P models https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/low/de_DE-thorsten-low.onnx
wget -P models https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/low/de_DE-thorsten-low.onnx.json

# 2. Start
docker compose up -d

# 3. Verify
curl http://localhost:10400/health
```

## Config (docker-compose.yml environment)

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_VOICE` | `de_DE-thorsten-low` | Voice model filename without extension |
| `MODELS_DIR` | `/models` | Path to model files inside the container |
| `TTS_PORT` | `10400` | Listening port |
| `RESAMPLE_RATE` | `16000` | Resample output to this Hz. Set to `0` for native model rate. Required for ReSpeaker HAT (WM8960 only supports multiples of 8000 Hz — 22050 Hz models play silently without this). |

## API

```bash
# Synthesize text → WAV
curl -X POST http://localhost:10400/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hallo Welt", "voice": "de_DE-thorsten-low"}' \
  --output reply.wav
```
