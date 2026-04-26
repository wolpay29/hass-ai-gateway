# Faster Whisper Server

GPU-accelerated speech-to-text service using [faster-whisper-server](https://github.com/fedirz/faster-whisper-server). Provides an OpenAI-compatible `/v1/audio/transcriptions` endpoint consumed by the Telegram bot and Voice Gateway.

## Requirements

- NVIDIA GPU with CUDA support
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed on the host — this is a one-time host-level setup and is not part of the Docker image. Without it, the container cannot access the GPU.

## Auto-start on reboot

The container has `restart: unless-stopped` set, so Docker will restart it automatically after a host reboot. You only need to ensure the Docker daemon itself starts on boot — this is a one-time host setup:

```bash
# Linux
sudo systemctl enable docker
```

On **Windows**, go to Docker Desktop → Settings → General → enable "Start Docker Desktop when you log in".

## Setup

```bash
# Start (model is downloaded automatically on first run)
docker compose up -d

# Restart
docker compose restart

# Stop
docker compose down

# Logs (follow)
docker compose logs -f

# Verify
curl http://localhost:10300/health
```

The model (`faster-whisper-large-v3-turbo-ct2`) is pulled from HuggingFace on first startup and cached in `./model-cache/` (mounted into the container). Subsequent starts skip the download entirely. The cache directory is gitignored and stays on the host only.

## Config (docker-compose.yml environment)

| Variable | Default | Description |
|---|---|---|
| `WHISPER__MODEL` | `deepdml/faster-whisper-large-v3-turbo-ct2` | HuggingFace model ID |
| `WHISPER__INFERENCE_DEVICE` | `cuda` | `cuda` or `cpu` |
| `WHISPER__COMPUTE_TYPE` | `float16` | `float16` (GPU) or `int8` (CPU) |
| `WHISPER__TTL` | `-1` | Seconds before model is unloaded. `-1` = never |
| `WHISPER__LANGUAGE` | `de` | ISO language code, or omit for auto-detect |
| `WHISPER__USE_VAD` | `true` | Voice Activity Detection — filters silence before transcription |

Port mapping: host `10300` → container `8000`. The internal port `8000` is baked into the `fedirz/faster-whisper-server` image and cannot be changed — only the host-side port (`10300`) can be adjusted.

## API

The server exposes an OpenAI-compatible transcription endpoint:

```bash
# Transcribe an audio file
curl -X POST http://localhost:10300/v1/audio/transcriptions \
  -F "file=@audio.wav" \
  -F "model=deepdml/faster-whisper-large-v3-turbo-ct2"

# Health check
curl http://localhost:10300/health
```

## Integration

The Telegram bot and Voice Gateway point to this service via the `.env` variable:

```env
WHISPER_BACKEND=http://localhost:10300
```

See [voice_gateway/README.md](../voice_gateway/README.md) and [OVERVIEW.md](../../../OVERVIEW.md) for full configuration details.
