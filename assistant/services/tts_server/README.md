# TTS Server

Piper TTS wrapped in a FastAPI HTTP server. Called by the Voice Gateway to synthesize reply text into WAV audio.

## Auto-start on reboot

The container has `restart: unless-stopped` set, so Docker will restart it automatically after a host reboot. You only need to ensure the Docker daemon itself starts on boot — this is a one-time host setup:

```bash
# Linux
sudo systemctl enable docker
```

On **Windows**, go to Docker Desktop → Settings → General → enable "Start Docker Desktop when you log in".

## Setup

```bash
# Start — model is downloaded automatically on first run
docker compose up -d

# Restart
docker compose restart

# Stop
docker compose down

# Logs (follow)
docker compose logs -f

# Verify
curl http://localhost:10400/health
```

The entrypoint script checks whether the model files are present in `./models/` and downloads them from HuggingFace if not. Subsequent starts skip the download.

## Config (docker-compose.yml environment)

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_VOICE` | `de_DE-thorsten-low` | Voice model filename without extension |
| `MODELS_DIR` | `/models` | Path to model files inside the container |
| `TTS_PORT` | `10400` | Listening port — controls both the internal container port and the host mapping (`10400:10400`). Change both together if you need a different port. |
| `RESAMPLE_RATE` | `16000` | Resample output to this Hz. Set to `0` for native model rate. Required for ReSpeaker HAT (WM8960 only supports multiples of 8000 Hz — 22050 Hz models play silently without this). |

## API

```bash
# Synthesize text → WAV
curl -X POST http://localhost:10400/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hallo Welt", "voice": "de_DE-thorsten-low"}' \
  --output reply.wav
```
