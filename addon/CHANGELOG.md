# Changelog

## 1.1.0 — 2026-05-02

- **Flat config schema** — all options are now top-level fields in the HA UI
  (no more collapsible nested sections).
- **Internal Whisper removed** — only external STT servers are supported.
  Point `whisper_url` at any OpenAI-compatible `/v1/audio/transcriptions`
  endpoint (see `infra/faster_whisper/`).
- **Debian base image** — switched from Alpine to `base-debian:bookworm` for
  full `sqlite-vec` wheel support (no more build-from-source on aarch64).
- Removed `whisper_vocabulary.md` user-config file (no longer needed without
  local Whisper).
- Multi-arch: `amd64`, `aarch64` (armv7 dropped — HAOS on RPi 3/4 runs aarch64).

## 1.0.0 — 2026-04-27

Initial release.

- Single container running `voice_gateway`, `notify_gateway`, `telegram_bot`
  under s6-overlay.
- Per-service enable/disable toggles.
- Persistent paths: `/data/voice/`, `/data/rag/entities.sqlite`.
- No `finish` scripts — s6 restarts a single crashed service without
  bringing down siblings.
