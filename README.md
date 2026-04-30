# Hass AI Gateway

LLM-powered voice, Telegram, and notification gateway for Home Assistant.
Bundles voice -> Whisper STT -> LM Studio -> HA service-call orchestration into
a single shared brain (`core/`) used by three frontends.

## Layout

| Path | What's there |
|------|--------------|
| [`core/`](core) | Framework-agnostic command logic: HA REST client, LM Studio LLM, RAG, processor, prompts |
| [`services/`](services) | Add-on services: `voice_gateway`, `notify_gateway`, `telegram_bot` (run inside the HA add-on container) |
| [`infra/`](infra) | Standalone helper servers: `faster_whisper` (STT), `tts_server` — run separately on any host |
| [`clients/`](clients) | Edge-device clients: `raspberry_pi/voice_client.py` |
| [`deploy/systemd/`](deploy/systemd) | systemd unit files + `install.sh` for bare-metal hosts |
| [`addon/`](addon) | Home Assistant Supervisor add-on packaging (Dockerfile, config.yaml, rootfs/) |
| [`docs/`](docs) | Architecture, overview, workflow |

## Two ways to run

1. **HA Add-on** (recommended) -- install via the Add-on Store from this
   repository. See [`addon/README.md`](addon/README.md) and
   [`addon/DOCS.md`](addon/DOCS.md).
2. **Bare-metal / systemd** -- run the services directly on a host using the
   units in [`deploy/systemd/`](deploy/systemd). See
   [`deploy/systemd/README.md`](deploy/systemd/README.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md) -- high-level component map
- [Overview](docs/OVERVIEW.md) -- folder-by-folder tour
- [Workflow](docs/WORKFLOW.md) -- request flow from voice/text to HA action

## Configuration

All services share a single top-level `.env` (see
[`.env.example`](.env.example)). When running as the HA add-on, options from
the Configuration tab are exported into the same environment variables -- no
`.env` needed inside the container.

User-editable files — `entities.yaml`, `entities_blacklist.yaml`,
`pre_llm_memory.md`, `post_llm_memory.md`, `menus.yaml`:

- **HA Add-on**: under `/addon_configs/<slug>/` — edit via Samba or the **File editor** add-on. Persists across updates. See [`addon/DOCS.md`](addon/DOCS.md) for what each file does.
- **Bare-metal**: [`core/userconfig/`](core/userconfig) + [`services/telegram_bot/menus.yaml`](services/telegram_bot/menus.yaml). Override paths via `USERCONFIG_DIR` / `TELEGRAM_MENUS_PATH`.
