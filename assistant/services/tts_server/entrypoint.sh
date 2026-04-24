#!/bin/sh
set -e

VOICE="${DEFAULT_VOICE:-de_DE-thorsten-low}"
MODELS_DIR="${MODELS_DIR:-/models}"
BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main"

# Derive language path from voice name: de_DE-thorsten-low → de/de_DE/thorsten/low
lang=$(echo "$VOICE" | cut -d- -f1)          # de_DE
lang_short=$(echo "$lang" | cut -d_ -f1)      # de
quality=$(echo "$VOICE" | rev | cut -d- -f1 | rev)   # low
name=$(echo "$VOICE" | sed "s/^${lang}-//" | sed "s/-${quality}$//")  # thorsten

MODEL_PATH="${MODELS_DIR}/${VOICE}.onnx"

if [ ! -f "$MODEL_PATH" ]; then
    echo "[entrypoint] Model not found — downloading ${VOICE} ..."
    mkdir -p "$MODELS_DIR"
    REMOTE="${BASE_URL}/${lang_short}/${lang}/${name}/${quality}/${VOICE}"
    wget -q --show-progress -O "${MODEL_PATH}" "${REMOTE}.onnx"
    wget -q --show-progress -O "${MODEL_PATH}.json" "${REMOTE}.onnx.json"
    echo "[entrypoint] Download complete."
else
    echo "[entrypoint] Model found: ${MODEL_PATH}"
fi

exec python main.py
