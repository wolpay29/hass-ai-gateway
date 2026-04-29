# Hass AI Gateway

LLM-powered voice, Telegram, and notification gateway for Home Assistant.
Bundles voice -> Whisper STT -> LM Studio -> HA service-call orchestration into
a single shared brain (`gateway/core`) with three frontends.

## Layout

| Path | What's there |
|------|--------------|
| [`gateway/`](gateway) | Application code: `core/` (HA + LLM + RAG), `services/` (voice_gateway, notify_gateway, telegram_bot, faster_whisper, tts_server), `devices/` (Raspberry Pi client), `systemd/` units |
| [`addon/`](addon) | Home Assistant Supervisor add-on packaging (`Dockerfile`, `config.yaml`, `rootfs/` with s6-overlay services) |
| [`docs/`](docs) | Architecture / overview / workflow documentation |

## Two ways to run

1. **HA Add-on** (recommended) — install via the Add-on Store from this
   repository. See [`addon/README.md`](addon/README.md) and
   [`addon/DOCS.md`](addon/DOCS.md).
2. **Bare-metal / systemd** — run the services directly on a host using the
   units in [`gateway/systemd/`](gateway/systemd). See
   [`gateway/systemd/README.md`](gateway/systemd/README.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — high-level component map
- [Overview](docs/OVERVIEW.md) — folder-by-folder tour
- [Workflow](docs/WORKFLOW.md) — request flow from voice/text to HA action

## Configuration

All services share a single `gateway/.env` (see
[`gateway/.env.example`](gateway/.env.example)). When running as the HA
add-on, options from the Configuration tab are exported into the same
environment variables — no `.env` needed.
