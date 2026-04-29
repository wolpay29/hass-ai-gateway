# Notify Gateway

Stateless FastAPI dispatcher. Listens on port **8766** for webhook calls from
Home Assistant and fans the message out to each requested target. No device
registry, no per-target config — HA decides who gets what, per request.

## Endpoints

### `POST /notify`

```json
{
  "message": "Battery at 83%",
  "targets": [
    {"type": "tts", "url": "http://192.168.1.42:8765"},
    {"type": "telegram"}
  ]
}
```

- `tts` → `POST {url}/text` with `{"text": message, "device_id": "ha-notify"}`
  and `X-Api-Key: $GATEWAY_API_KEY`. The `url` points at a `voice_gateway`
  instance (e.g. on a Raspberry Pi).
- `telegram` → sends the message to `MY_CHAT_ID` via the Bot API using
  `BOT_TOKEN`.

Response: `{"results": [{"type": "...", "ok": true/false, ...}, ...]}`.
A single failed target does not abort the others.

### `GET /health`

Liveness probe.

## Config

Reads from `gateway/.env` via `core/config.py`:

| Var | Purpose |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token (used for `telegram` targets) |
| `MY_CHAT_ID` | Telegram chat id messages are sent to |
| `GATEWAY_API_KEY` | Sent as `X-Api-Key` to voice_gateway `/text` |
| `NOTIFY_PORT` | Listen port (default `8766`) |
| `NOTIFY_HTTP_TIMEOUT` | Per-target HTTP timeout in seconds (default `10`) |

## Run

```bash
python -m venv notify_gateway_env
notify_gateway_env/bin/pip install -r requirements.txt
notify_gateway_env/bin/python main.py
```

Or via systemd: copy `gateway/systemd/notify-gateway.service` to
`/etc/systemd/system/` and `systemctl enable --now notify-gateway`.

## HA example

```yaml
rest_command:
  notify_dispatch:
    url: "http://<server>:8766/notify"
    method: POST
    content_type: "application/json"
    payload: >
      {"message": "{{ message }}",
       "targets": [{"type": "tts", "url": "http://192.168.1.42:8765"},
                   {"type": "telegram"}]}
```
