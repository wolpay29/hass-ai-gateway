#!/usr/bin/env bash
# install.sh — Raspberry Pi Voice Client installer
#
# Run this on the Pi:
#   bash install.sh
#
# The script:
#   1. Installs system packages
#   2. Sets up ~/voice with the Python venv + dependencies
#   3. Prompts interactively for all config values → writes .env
#   4. Optionally downloads the Piper TTS model (de_DE-thorsten-low)
#   5. Installs and starts the voice-client systemd service

set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
section() { echo -e "\n${CYAN}=== $* ===${NC}"; }

ask() {
    # ask <var> <prompt> [default]
    local var=$1 prompt=$2 default=${3:-}
    local display_default=""
    [[ -n $default ]] && display_default=" [${default}]"
    read -rp "  ${prompt}${display_default}: " value
    [[ -z $value ]] && value="$default"
    printf -v "$var" '%s' "$value"
}

ask_secret() {
    local var=$1 prompt=$2
    read -rsp "  ${prompt}: " value
    echo
    printf -v "$var" '%s' "$value"
}

confirm() {
    # confirm <prompt> → returns 0 for yes, 1 for no
    local answer
    read -rp "  $* [y/N]: " answer
    [[ ${answer,,} == "y" || ${answer,,} == "yes" ]]
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/voice"
SERVICE_NAME="voice-client"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CURRENT_USER="$(whoami)"

# ---------------------------------------------------------------------------
section "Raspberry Pi Voice Client — Installer"
# ---------------------------------------------------------------------------
echo "  Install directory : $INSTALL_DIR"
echo "  Running as user   : $CURRENT_USER"
echo

if [[ $CURRENT_USER == "root" ]]; then
    warn "Running as root — the service will run as root too."
    warn "Consider running as your normal user instead."
fi

# ---------------------------------------------------------------------------
section "1 — System packages"
# ---------------------------------------------------------------------------
info "Updating package lists…"
sudo apt-get update -qq

info "Installing portaudio19-dev, python3-venv, python3-pip, python3-spidev…"
sudo apt-get install -y -qq portaudio19-dev python3-venv python3-pip python3-spidev

# ---------------------------------------------------------------------------
section "2 — SPI interface (required for ReSpeaker LED HAT)"
# ---------------------------------------------------------------------------
CONFIG_TXT="/boot/firmware/config.txt"
# Fallback for older Raspberry Pi OS versions
[[ ! -f "$CONFIG_TXT" ]] && CONFIG_TXT="/boot/config.txt"

if grep -q "^dtparam=spi=on" "$CONFIG_TXT" 2>/dev/null; then
    info "SPI already enabled in $CONFIG_TXT"
elif grep -q "^#dtparam=spi=on" "$CONFIG_TXT" 2>/dev/null; then
    info "Enabling SPI in $CONFIG_TXT (uncommenting existing line)…"
    sudo sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' "$CONFIG_TXT"
    warn "SPI enabled — a reboot is required after install for LEDs to work!"
else
    info "Adding dtparam=spi=on to $CONFIG_TXT…"
    echo "dtparam=spi=on" | sudo tee -a "$CONFIG_TXT" > /dev/null
    warn "SPI enabled — a reboot is required after install for LEDs to work!"
fi

# Check if SPI device is already available (no reboot needed)
if ls /dev/spidev* &>/dev/null; then
    info "SPI device found: $(ls /dev/spidev*) — no reboot needed for LEDs."
else
    warn "No /dev/spidev* found yet — reboot after install to activate LEDs."
fi

# ---------------------------------------------------------------------------
section "3 — Copy client files"
# ---------------------------------------------------------------------------
mkdir -p "$INSTALL_DIR/models"

copy_file() {
    local src="$SCRIPT_DIR/$1" dst="$INSTALL_DIR/$1"
    if [[ -f $src ]]; then
        cp "$src" "$dst"
        info "Copied $1"
    else
        error "Could not find $src — make sure you run install.sh from the clients/raspberry_pi directory"
        exit 1
    fi
}

copy_file "voice_client.py"
copy_file "requirements.txt"

# ---------------------------------------------------------------------------
section "4 — Python virtual environment"
# ---------------------------------------------------------------------------
if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    info "Creating virtual environment…"
    python3 -m venv "$INSTALL_DIR/venv"
else
    info "Virtual environment already exists — skipping creation"
fi

info "Installing openwakeword (no-deps, avoids tflite conflict)…"
"$INSTALL_DIR/venv/bin/pip" install --quiet openwakeword --no-deps

info "Installing remaining requirements (incl. spidev for LEDs)…"
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

info "Python dependencies installed successfully."

# ---------------------------------------------------------------------------
section "5 — Download openwakeword ONNX models"
# ---------------------------------------------------------------------------
info "Downloading built-in openwakeword models (hey_jarvis, alexa, …)…"
"$INSTALL_DIR/venv/bin/python3" -c "
from openwakeword.utils import download_models
download_models()
print('openwakeword models downloaded.')
"
info "Wake word models ready."

# ---------------------------------------------------------------------------
section "6 — Configuration"
# ---------------------------------------------------------------------------
RECONFIGURE=true
ENV_FILE="$INSTALL_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    warn ".env already exists at $ENV_FILE"
    if confirm "Keep existing .env and skip configuration prompts?"; then
        RECONFIGURE=false
        info "Keeping existing .env — skipping configuration step."
        # Source existing values so ALSA_CARD and TTS_MODEL_PATH are available later.
        set -a; source "$ENV_FILE"; set +a
        TTS_MODEL_PATH="${TTS_MODEL:-}"
    fi
fi

if $RECONFIGURE; then
    echo "  Answer each question. Press Enter to accept the default."
    echo

    ask GATEWAY_URL    "Voice Gateway URL"           "http://10.1.10.78:8765"
    ask_secret GATEWAY_API_KEY "Gateway API key (leave empty if none)"
    ask DEVICE_ID      "Device ID (e.g. rpi-wohnzimmer)" "rpi-wohnzimmer"
    ask WAKE_WORD      "Wake word"                   "hey_jarvis"
    ask WAKE_THRESHOLD "Wake threshold (0.0–1.0)"    "0.5"

    echo
    info "Finding ALSA audio devices…"
    echo "  --- arecord -l ---"
    arecord -l 2>/dev/null | grep "^card" || echo "  (none found)"
    echo "  --- aplay -l ---"
    aplay -l 2>/dev/null | grep "^card" || echo "  (none found)"
    echo

    ask ALSA_INPUT_DEVICE  "ALSA input device (mic)"    "plughw:1,0"
    ask ALSA_OUTPUT_DEVICE "ALSA output device (speaker)" "plughw:1,0"
    ask SPEAKER_VOLUME     "Speaker volume"              "100%"

    echo
    ask VAD_SILENCE_THRESHOLD "VAD silence threshold (int16 RMS, raise in noisy rooms)" "500"
    ask VAD_SILENCE_DURATION  "VAD silence duration (seconds)"                           "1.0"
    ask VAD_MAX_DURATION      "Max recording duration (seconds)"                         "10.0"
    ask VAD_INITIAL_TIMEOUT   "Seconds to wait for speech after wake word"               "5.0"

    echo
    info "Follow-up mode: after the reply the Pi listens again without the wake word."
    ask FOLLOWUP_ENABLED          "Enable follow-up mode (true/false)"        "true"
    ask FOLLOWUP_INITIAL_TIMEOUT  "Follow-up silence timeout (seconds)"       "1.5"
    ask FOLLOWUP_ONSET_CHUNKS     "Follow-up onset chunks (raise to filter TTS echo)" "3"
    ask FOLLOWUP_DRAIN_SECONDS    "Drain seconds after playback (absorbs TTS echo)"   "0.5"
fi

# ---------------------------------------------------------------------------
section "7 — Piper TTS model (optional local fallback)"
# ---------------------------------------------------------------------------
echo
info "Piper is used as a local TTS fallback if the external TTS server is unavailable."
warn "If you have an external TTS server (recommended), you can skip this step."
echo

if [[ -z "${TTS_MODEL_PATH:-}" ]]; then TTS_MODEL_PATH=""; fi
if confirm "Download de_DE-thorsten-low Piper model (~16 MB)?"; then
    MODEL_DIR="$INSTALL_DIR/models"
    MODEL_BASE="de_DE-thorsten-low"
    MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/low"

    info "Downloading ${MODEL_BASE}.onnx …"
    wget -q --show-progress -P "$MODEL_DIR" "${MODEL_URL}/${MODEL_BASE}.onnx"

    info "Downloading ${MODEL_BASE}.onnx.json …"
    wget -q --show-progress -P "$MODEL_DIR" "${MODEL_URL}/${MODEL_BASE}.onnx.json"

    TTS_MODEL_PATH="$MODEL_DIR/${MODEL_BASE}.onnx"
    info "Piper model saved to $TTS_MODEL_PATH"
fi

# ---------------------------------------------------------------------------
section "8 — Write .env"
# ---------------------------------------------------------------------------
if ! $RECONFIGURE; then
    info "Skipping .env write — using existing file."
else

cat > "$ENV_FILE" << EOF
GATEWAY_URL=${GATEWAY_URL}
GATEWAY_API_KEY=${GATEWAY_API_KEY}
DEVICE_ID=${DEVICE_ID}
WAKE_WORD=${WAKE_WORD}
WAKE_THRESHOLD=${WAKE_THRESHOLD}
ALSA_INPUT_DEVICE=${ALSA_INPUT_DEVICE}
ALSA_OUTPUT_DEVICE=${ALSA_OUTPUT_DEVICE}
SPEAKER_VOLUME=${SPEAKER_VOLUME}
TTS_MODEL=${TTS_MODEL_PATH}
VAD_SILENCE_THRESHOLD=${VAD_SILENCE_THRESHOLD}
VAD_SILENCE_DURATION=${VAD_SILENCE_DURATION}
VAD_MAX_DURATION=${VAD_MAX_DURATION}
VAD_INITIAL_TIMEOUT=${VAD_INITIAL_TIMEOUT}
FOLLOWUP_ENABLED=${FOLLOWUP_ENABLED}
FOLLOWUP_INITIAL_TIMEOUT=${FOLLOWUP_INITIAL_TIMEOUT}
FOLLOWUP_ONSET_CHUNKS=${FOLLOWUP_ONSET_CHUNKS}
FOLLOWUP_DRAIN_SECONDS=${FOLLOWUP_DRAIN_SECONDS}
EOF

chmod 600 "$ENV_FILE"
info ".env written to $ENV_FILE"

fi  # end RECONFIGURE block

# ---------------------------------------------------------------------------
section "9 — ALSA mixer setup (unmute WM8960)"
# ---------------------------------------------------------------------------
# Extract card number from ALSA_INPUT_DEVICE (e.g. plughw:1,0 → 1)
ALSA_CARD=$(echo "$ALSA_INPUT_DEVICE" | grep -oP '(?<=:)\d+(?=,)' || echo "1")

info "Configuring ALSA mixer for card $ALSA_CARD …"

run_amixer() { amixer -c "$ALSA_CARD" sset "$@" 2>/dev/null || true; }

# Mic inputs
run_amixer 'Capture' '100%'
run_amixer 'Left Boost Mixer LINPUT1' on
run_amixer 'Right Boost Mixer RINPUT1' on
run_amixer 'Left Input Mixer Boost' on
run_amixer 'Right Input Mixer Boost' on
run_amixer 'ADC PCM' '100%'

# Speaker outputs
run_amixer 'Playback' '100%'
run_amixer 'Speaker' '100%'
run_amixer 'Headphone' '100%'
run_amixer 'Left Output Mixer PCM' on
run_amixer 'Right Output Mixer PCM' on

info "Saving ALSA state so it survives reboot…"
sudo alsactl store "$ALSA_CARD" 2>/dev/null || sudo alsactl store || warn "alsactl store failed — run manually after reboot"

# ---------------------------------------------------------------------------
section "10 — systemd service"
# ---------------------------------------------------------------------------
info "Writing $SERVICE_FILE …"

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Smart Home Voice Client
After=network.target sound.target
Wants=network.target

[Service]
User=${CURRENT_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/voice_client.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

info "Reloading systemd daemon…"
sudo systemctl daemon-reload

info "Enabling service to start on boot…"
sudo systemctl enable "$SERVICE_NAME"

info "Starting (or restarting) service…"
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    sudo systemctl restart "$SERVICE_NAME"
else
    sudo systemctl start "$SERVICE_NAME"
fi

# ---------------------------------------------------------------------------
section "Done"
# ---------------------------------------------------------------------------
echo
STATUS=$(sudo systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")
if [[ $STATUS == "active" ]]; then
    echo -e "  ${GREEN}Service is running.${NC}"
else
    echo -e "  ${YELLOW}Service status: ${STATUS}${NC}"
fi

echo
if ! ls /dev/spidev* &>/dev/null; then
    echo -e "  ${YELLOW}⚠ SPI not yet active — reboot to enable LEDs:${NC}"
    echo "    sudo reboot"
    echo
fi

echo "  Useful commands:"
echo "    sudo systemctl status $SERVICE_NAME     — check status"
echo "    journalctl -u $SERVICE_NAME -f          — live logs"
echo "    sudo systemctl restart $SERVICE_NAME    — restart after .env changes"
echo "    sudo systemctl stop $SERVICE_NAME       — stop the service"
echo
echo "  Config file: $ENV_FILE"
echo "    Edit it with: nano $ENV_FILE"
echo "    Then restart: sudo systemctl restart $SERVICE_NAME"
echo
