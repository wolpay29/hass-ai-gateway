# Changelog

## 1.0.0 — 2026-04-27

Initial release.

- Single container running `voice_gateway`, `notify_gateway`, `telegram_bot`
  under s6-overlay.
- HA UI configuration via grouped `options` / `schema` blocks (Telegram, HA,
  Whisper, LM Studio, RAG, fallback, advanced).
- Per-service enable/disable toggles under `services:`.
- Whisper external-only (`WHISPER_BACKEND=external` pinned at image level).
- Multi-arch: `amd64`, `aarch64`, `armv7`.
- Persistent paths: `/data/voice/`, `/data/rag/entities.sqlite`.
- No `finish` scripts — s6 restarts a single crashed service without
  bringing down siblings.
