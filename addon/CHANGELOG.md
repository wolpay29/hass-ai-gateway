# Changelog

## 1.2.7 — 2026-05-09

- Prompts entpersonalisiert: alle setup-spezifischen Beispiele (Personennamen, Pool, OG/EG, Rollos, Räume) aus `prompts_de.yaml` und `prompts_en.yaml` entfernt. Übrig bleibt nur das universelle HA-Vokabular (JSON-Schema, action-Namen, domains, service_data).
- `pre_llm_memory.md` und `post_llm_memory.md` neu strukturiert: Standardinhalt ist leer, ausführlicher Inspirations-Block in HTML-Kommentaren — User editiert dort eigene Setup-Hinweise (Namen, Stockwerke, Spitznamen, STT-Korrekturen, Verbote).
- Doku ergänzt: neuer Abschnitt „Memory files — your per-setup tuning" in DOCS.md, kurzer Hinweis in README.

## 1.2.6 — 2026-05-09

- Auto-RAG-Build beim Add-on-Start, wenn `rag.enabled=true`. Logs erscheinen im Add-on-Log; Fehler blockieren den Service-Start nicht.

## 1.2.5 — 2026-05-09

- Fix: GHCR-Image-Pfad nach Account-Umbenennung (`wolpay29` → `wolpa29`) korrigiert.

## 1.2.4 — 2026-05-09

- Telegram ReplyKeyboard bleibt während Aktionen sichtbar; nach jeder Aktion wird eine frische Trägernachricht gesendet, damit die Tastatur auch bei aktivem 24h-Auto-Delete erhalten bleibt.

## 1.2.3 — 2026-05-03

- Each config section now shows a summary of all its fields in the section description.
- Logo Update

## 1.2.1 — 2026-05-03

- Fix: field descriptions now appear above config inputs in HA UI (removed incorrect `fields:` wrapper from translations).
- Fix: bot token no longer appears in plaintext in addon logs.

## 1.2.0 — 2026-05-02

- Config UI now has 10 collapsible sections (Services, Telegram, Home Assistant, LM Studio, Whisper, TTS, Gateways, RAG, Preprocessor, Fallback & History).

## 1.1.0 — 2026-05-02

- Internal Whisper removed — external STT server only (`whisper.url`).
- Debian base image — fixes `sqlite-vec` install on aarch64.
- armv7 dropped — HAOS on RPi 3/4 uses aarch64.

## 1.0.0 — 2026-04-27

Initial release. Three services (`voice_gateway`, `notify_gateway`, `telegram_bot`) in one container under s6-overlay.
