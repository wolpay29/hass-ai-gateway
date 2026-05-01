#!/usr/bin/env bash
# tests/e2e/run.sh - Setup + launch the E2E test runner.
#
# First run: creates tests/e2e/venv, installs all required packages.
# Subsequent runs: activates the existing venv and starts the runner directly.
#
# Usage:
#   ./tests/e2e/run.sh [runner args...]
#
# Examples:
#   ./tests/e2e/run.sh --only "rag-on-prellm-on-fb0" --case status_pv
#   ./tests/e2e/run.sh --open
#   ./tests/e2e/run.sh --live --rebuild-rag

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$REPO_ROOT/services/voice_gateway/requirements.txt"

# ---------------------------------------------------------------------------
# 1. Create venv if it doesn't exist yet
# ---------------------------------------------------------------------------
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo ">>> Creating E2E venv at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    echo ">>> Installing dependencies from $REQUIREMENTS ..."
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet
    "$VENV_DIR/bin/pip" install -r "$REQUIREMENTS" --quiet
    echo ">>> Venv ready."
    echo ""
fi

# ---------------------------------------------------------------------------
# 2. Check that .env.local exists
# ---------------------------------------------------------------------------
if [ ! -f "$SCRIPT_DIR/.env.local" ]; then
    echo "ERROR: tests/e2e/.env.local not found."
    echo "       Copy tests/e2e/.env.local.example to tests/e2e/.env.local and fill in your values."
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Run the runner with the venv's Python
# ---------------------------------------------------------------------------
PYTHON="$VENV_DIR/bin/python"

echo ">>> Using Python: $($PYTHON --version 2>&1)"
echo ">>> Repo root:    $REPO_ROOT"
echo ""

exec "$PYTHON" -m tests.e2e.runner "$@"
