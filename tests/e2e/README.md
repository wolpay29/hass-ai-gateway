# End-to-End-Test-Pipeline

Lokaler Roundtrip-Test fuer den Voice-Gateway-Stack: Audio rein - Whisper -
Rewriter - RAG - Parser - Home Assistant - TTS - Audio raus. Ueber alle
sinnvollen Settings-Kombinationen, mit History-Sequenzen, ohne deine
produktive Konfiguration anzufassen.

Das Production-Addon laueft auf Port `8765` weiter, der Test-Subprocess auf
`8799` mit eigener `.env` und eigener RAG-DB - keine Kollision.

## Schnellstart

```bash
# 1. einmaliges Setup
cp tests/e2e/.env.local.example tests/e2e/.env.local
nano tests/e2e/.env.local

# 2. WAV-Dateien aufnehmen (siehe fixtures/AUDIO_RECORDING_LIST.md)
#    in tests/e2e/fixtures/audio/ ablegen

# 3. Smoke-Test
python -m tests.e2e.runner --only "rag-on-prellm-on-fb0" --case status_pv

# 4. Voller Lauf - alle Settings, alle Cases, Report im Browser
python -m tests.e2e.runner --open
```

## Voraussetzungen

- Python 3.11+, `requirements.txt` aus dem Projekt installiert (uvicorn, fastapi,
  python-telegram-bot, requests, pyyaml, sqlite-vec, ...). Bare-Metal-Installation
  oder `pip install -e .[dev]` reicht.
- LM Studio + Whisper-Server + Embed-Server + Home Assistant erreichbar (also
  dieselben externen Services wie das produktive Addon).
- Audio-Dateien unter `fixtures/audio/` (siehe `fixtures/AUDIO_RECORDING_LIST.md`).
- Optional fuer fb-2 (MCP-Fallback): LM Studio Server-Auth aktiv,
  HA-MCP-Server laueft, `LMSTUDIO_API_KEY` gesetzt.

## CLI-Schalter

```
python -m tests.e2e.runner [Optionen]

  --only PATTERN     Nur Settings-Variante PATTERN (fnmatch) ausfuehren
  --case ID          Nur Case ID (fnmatch) ausfuehren
  --live             HA_DRY_RUN abschalten - echte Service-Calls!
  --open             Report im Browser oeffnen
  --rebuild-rag      RAG-Index zwingend neu bauen (default: nur wenn fehlt)
  --keep             _runs/ nicht aufraeumen
  --port N           Gateway-Port ueberschreiben (default 8799)
```

## Was die Pipeline tut

1. **Pro Settings-Variante** (`matrix.yaml`):
   - effektive `.env` zusammenbauen unter `_runs/<variant>/.env` (deine
     `.env.local` + globale Defaults aus `common_env` + variante-spezifische Overrides).
   - Bei `RAG_ENABLED=true`: einmalig `core.rag.index.build()` gegen die test-
     `entities.yaml` ausfuehren. Index landet unter `_runs/<variant>/rag.sqlite`.
   - Voice-Gateway-Subprocess starten: `python -m uvicorn services.voice_gateway.main:app --port 8799`.
     Stdout/Stderr werden in `_runs/<variant>/log.txt` gespiegelt.
   - Pro Case in `cases.yaml`:
     - Audio per `POST /audio` (oder Text per `POST /text`) reinschicken.
     - WAV-Reply unter `reports/<ts>/audio/<variant>/<case>.wav` ablegen.
     - Logzeilen zwischen Request-Start und +2s nach Response abgreifen und in
       Schritte zerlegen (Whisper, Rewriter, RAG-Top-K, LLM-Raw, LLM-Parsed,
       HA-Calls, Reply).
     - `expect`/`expect_per_run` aus `cases.yaml` auswerten.
   - Subprocess sauber stoppen.
2. Am Ende: `reports/<ts>/results.json` + `results.html`. HTML enthaelt Matrix
   (Cases x Variants), klickbare Detail-Panels mit allen Zwischenschritten,
   Audio-Player fuer jeden Reply, Filter ("nur Fails").

## Sicherheit

`HA_DRY_RUN=true` ist Default - `core/ha.py:call_service` schickt dann KEINE
echten HTTP-Calls an HA, sondern loggt nur `[HA DRY-RUN] domain.action eid`.
State-Reads (`get_state`, `get_states_bulk`) bleiben aktiv, damit Statusabfragen
mit echten Werten arbeiten.

Erst mit `--live` werden echte Schaltvorgaenge ausgefuehrt - **dann mit Bedacht**:
ein voller Lauf der Suite triggert pro Variant ~25 Aktionen.

## Cases erweitern

In `cases.yaml` einen neuen Eintrag unter `single_cases:` oder als Step in einem
`sequence_cases:`-Eintrag anhaengen. Audio-Datei dazu unter `fixtures/audio/`
ablegen.

`expect`-Schluessel:
- `reply_regex` - Regex (DOTALL+IGNORECASE)
- `reply_min_chars` - Mindestlaenge
- `actions_executed` / `action_includes` / `actions_count_min` / `actions_count_max` / `no_actions`
- `error` / `no_error` / `fallback_used` (`rest`/`mcp`/`null`)
- `transcript_contains`

Pro-Run-Overrides via `expect_per_run` mit fnmatch-Pattern auf den Run-Namen.

## Settings erweitern

In `matrix.yaml` einen neuen Eintrag unter `runs:` anhaengen. `common_env:` ist
fuer Defaults die fuer ALLE Runs gelten (Port, History-Setup, etc.). Pro-Run
`env:` ueberschreibt diese.

Beim naechsten Lauf wird der neue Run automatisch durch alle Cases gespielt.

## Troubleshooting

| Symptom | Wahrscheinliche Ursache | Fix |
|---|---|---|
| `RAG_BUILD_OK count=0` | HA antwortet leer oder nicht erreichbar | `HA_URL`/`HA_TOKEN` in `.env.local` pruefen |
| Subprocess kommt nicht hoch | Port belegt | `--port 8800` oder pruefen ob Production-Addon den Port nutzt |
| Whisper liefert leeres Transkript | Audio zu kurz / VAD greift / falsche Samplerate | WAV in 16 kHz mono 16-bit pcm exportieren |
| Alle Cases fail mit "request failed" | Subprocess ist aus: log.txt im Run-Ordner anschauen | Stacktrace dort lesen, meist fehlende Env-Var |
| Cells leer / "skip" | Case wurde nicht gespielt (`--case` Filter, `skip_runs`) | Filter pruefen |

## Architektur

```
matrix.yaml       Setting-Kombinationen (RAG/Pre-LLM/Fallback x DistanceThreshold)
cases.yaml        Test-Cases (single + sequence)
fixtures/         Test-Daten (entities.yaml, audio/, memory.md, whisper-vocab)
runner.py         Orchestrator (Subprocess, HTTP, expect-Engine)
log_parser.py     Regex-Extraktor fuer Whisper/RAG/LLM/HA aus dem Subprocess-Log
report.py         Single-Page-HTML-Report (kein JS-Framework)
templates/        (reserviert)
_runs/            (gitignored) - tempaerer Output pro Run-Variante
reports/          (gitignored) - HTML-Reports inkl. abspielbarer TTS-WAVs
```

Der Test fasst keinen Production-Code an - er ruft `services/voice_gateway/main.py`
und `core/*` direkt auf. Wenn du diese Files refaktorierst, sieht der Test das
beim naechsten `git pull` automatisch.
