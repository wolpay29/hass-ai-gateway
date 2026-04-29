# Voice Gateway

HTTP bridge between local devices (Raspberry Pi) and the assistant core. Receives audio, transcribes via Whisper, processes via LLM, returns reply as JSON or WAV.

## Start

```bash
cd assistant
python services/voice_gateway/main.py
```

## Config (gateway/.env)

| Variable | Default | Description |
|---|---|---|
| `GATEWAY_PORT` | `8765` | Listening port |
| `GATEWAY_API_KEY` | `` | Auth key sent as `X-Api-Key` header. Empty = no auth |
| `GATEWAY_TELEGRAM_PUSH` | `true` | Push command receipt to Telegram |
| `TTS_EXTERNAL_URL` | `` | TTS server URL e.g. `http://10.1.10.78:10400/tts` |
| `TTS_EXTERNAL_VOICE` | `de_DE-thorsten-low` | Voice model to request from TTS server |

## API

```bash
# Health check
curl http://localhost:8765/health

# Send audio (returns WAV when TTS configured, JSON otherwise)
curl -X POST http://localhost:8765/audio \
  -F "file=@command.wav" \
  -F "device_id=rpi-wohnzimmer" \
  -F "tts=true"

# Send text
curl -X POST http://localhost:8765/text \
  -H "Content-Type: application/json" \
  -d '{"text": "Licht einschalten", "device_id": "rpi-wohnzimmer"}'
```
