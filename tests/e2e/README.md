# End-to-End Test Pipeline

Local roundtrip test for the voice gateway stack: audio in - Whisper -
Rewriter - RAG - Parser - Home Assistant - TTS - audio out. Across all
relevant settings combinations, with history sequences, without touching
your production configuration.

The production addon keeps running on port `8765`; the test subprocess runs on
`8799` with its own `.env` and its own RAG database — no collision.

## Quick start

```bash
# 1. one-time setup — only needed if you don't have a root .env yet
cp .env.example .env
nano .env

# 2. record audio files (see fixtures/AUDIO_RECORDING_LIST.md)
#    place them in tests/e2e/fixtures/audio/ (.wav or .m4a)

# 3. run a single test
./tests/e2e/run.sh --only "rag-on-prellm-on-fb0" --case status_pv

# 4. run all tests - all setting variants, all cases
./tests/e2e/run.sh
```

## Running a single test

```bash
./tests/e2e/run.sh --only "<run-name>" --case <case-id>
```

- `--only` filters the settings variant (from `matrix.yaml`, e.g. `rag-on-prellm-on-fb0`)
- `--case` filters the case (from `cases.yaml`, e.g. `status_pv`) — fnmatch patterns supported

Examples:

```bash
# one case in one variant
./tests/e2e/run.sh --only "rag-on-prellm-on-fb0" --case status_pv

# all cases in one variant
./tests/e2e/run.sh --only "rag-on-prellm-on-fb0"

# all variants for one case
./tests/e2e/run.sh --case status_pv
```

## Running all tests

```bash
# all variants, all cases
./tests/e2e/run.sh

# open the HTML report in a browser when done (if a browser is available on the server)
./tests/e2e/run.sh --open
```

The HTML report is written to `tests/e2e/reports/<timestamp>/results.html`.
**Important:** download the entire report folder, not just the HTML file — the audio
players reference WAV files at `audio/<variant>/<case>.wav` relative to the report.

## Prerequisites

- Python 3.11+, `requirements.txt` installed (uvicorn, fastapi, python-telegram-bot,
  requests, pyyaml, sqlite-vec, ...). A bare-metal `pip install -e .[dev]` is enough.
- A root `.env` with the service URLs filled in (same file the production addon uses).
  The test runner reads it directly — no separate test env file needed.
- LM Studio + Whisper server + embed server + Home Assistant reachable.
- Audio files under `fixtures/audio/` (see `fixtures/AUDIO_RECORDING_LIST.md`).
  Supported formats: `.wav`, `.m4a`, `.mp3`, `.ogg`.

## CLI flags

```
./tests/e2e/run.sh [options]

  --only PATTERN     Run only the settings variant matching PATTERN (fnmatch)
  --case ID          Run only the case matching ID (fnmatch)
  --live             Disable HA_DRY_RUN — real service calls!
  --open             Open the report in a browser when done
  --rebuild-rag      Force a fresh RAG index build (default: only if missing)
  --keep             Do not clean up _runs/ after the run
  --port N           Override the gateway port (default 8799)
```

## What the pipeline does

1. **Per settings variant** (`matrix.yaml`):
   - Build an effective `.env` at `_runs/<variant>/.env` (your `.env.local` +
     global defaults from `common_env` + variant-specific overrides).
   - If `RAG_ENABLED=true`: run `core.rag.index.build()` once against the test
     `entities.yaml`. Index is stored at `_runs/<variant>/rag.sqlite`.
   - Start the voice gateway subprocess: `python -m uvicorn services.voice_gateway.main:app --port 8799`.
     Stdout/stderr are mirrored to `_runs/<variant>/log.txt`.
   - Per case in `cases.yaml`:
     - Send audio via `POST /audio` (or text via `POST /text`).
     - Save the WAV reply to `reports/<ts>/audio/<variant>/<case>.wav`.
     - Slice the captured log between request start and +2 s after response,
       then parse it into steps (Whisper, Rewriter, RAG top-k, LLM raw,
       LLM parsed, HA calls, reply).
     - Evaluate `expect` / `expect_per_run` from `cases.yaml`.
   - Stop the subprocess cleanly.
2. At the end: `reports/<ts>/results.json` + `results.html`. The HTML contains a
   matrix (cases x variants), clickable detail panels with all intermediate steps,
   an audio player for each reply, and a "failures only" filter.

## Safety

`HA_DRY_RUN=true` is the default — `core/ha.py:call_service` sends no real HTTP
calls to HA and only logs `[HA DRY-RUN] domain.action eid`. State reads
(`get_state`, `get_states_bulk`) stay active so status queries work with real values.

Real service calls only happen with `--live` — **use with care**: a full suite run
triggers ~25 actions per variant.

## Adding cases

Add a new entry under `single_cases:` or as a step in a `sequence_cases:` entry
in `cases.yaml`. Place the corresponding audio file under `fixtures/audio/`.

`expect` keys:
- `reply_regex` — regex (DOTALL + IGNORECASE)
- `reply_min_chars` — minimum reply length
- `actions_executed` / `action_includes` / `actions_count_min` / `actions_count_max` / `no_actions`
- `error` / `no_error` / `fallback_used` (`rest` / `mcp` / `null`)
- `transcript_contains`

Per-run overrides via `expect_per_run` with fnmatch patterns on the run name.

## Adding settings variants

Add a new entry under `runs:` in `matrix.yaml`. `common_env:` holds defaults that
apply to all runs (port, history setup, etc.); per-run `env:` overrides those.

The new variant is automatically included in all cases on the next run.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `RAG_BUILD_OK count=0` | HA returns empty or is unreachable | Check `HA_URL` / `HA_TOKEN` in `.env.local` |
| Subprocess does not start | Port already in use | Use `--port 8800` or check if the production addon is using the port |
| Whisper returns empty transcript | Audio too short / VAD triggered / wrong sample rate | Export WAV as 16 kHz mono 16-bit PCM |
| All cases fail with "request failed" | Subprocess crashed — check `log.txt` in the run folder | Read the stacktrace there, usually a missing env var |
| Cells empty / "skip" | Case was not executed (`--case` filter, `skip_runs`) | Check your filters |

## Architecture

```
matrix.yaml       Settings combinations (RAG / pre-LLM / fallback x distance threshold)
cases.yaml        Test cases (single + sequence)
fixtures/         Test data (entities.yaml, audio/, memory.md, whisper vocab)
runner.py         Orchestrator (subprocess, HTTP, expect engine)
log_parser.py     Regex extractor for Whisper/RAG/LLM/HA from the subprocess log
report.py         Single-page HTML report (no JS framework)
templates/        (reserved)
_runs/            (gitignored) — temporary output per settings variant
reports/          (gitignored) — HTML reports including playable TTS WAVs
```

The test does not touch any production code — it calls `services/voice_gateway/main.py`
and `core/*` directly. Refactoring those files is immediately reflected on the next run.
