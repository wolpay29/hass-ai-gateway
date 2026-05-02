# Changelog

## 1.2.0 — 2026-05-02

- Config UI now has 10 collapsible sections (Services, Telegram, Home Assistant, LM Studio, Whisper, TTS, Gateways, RAG, Preprocessor, Fallback & History).

## 1.1.0 — 2026-05-02

- Internal Whisper removed — external STT server only (`whisper.url`).
- Debian base image — fixes `sqlite-vec` install on aarch64.
- armv7 dropped — HAOS on RPi 3/4 uses aarch64.

## 1.0.0 — 2026-04-27

Initial release. Three services (`voice_gateway`, `notify_gateway`, `telegram_bot`) in one container under s6-overlay.
