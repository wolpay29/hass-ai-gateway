# Raspberry Pi Configuration

This is a configuration guide for the raspberry pi hardware which I already tested:

---

## First Setup - Raspberry + Mic HAT

### Hardware
- RaspberryPi 3b+ with Raspberry Pi OS Lite (64-bit) (Debian Trixie with no Desktop environment)(Kernel 6.12+)
- ReSpeaker 2Mic HAT v1
- 4Ohm 3W Speaker connected to the HAT

### Installation

#### 1. Driver Installation (The Modern Way)
We avoid old installation scripts because they often fail on new kernels. Instead, we use the modern Device Tree Overlay method.

```Bash
# Clone the repository containing the modern overlay files
git clone https://github.com/Seeed-Studio/seeed-linux-dtoverlays.git
cd seeed-linux-dtoverlays

# Compile the overlay into machine code
make overlays/rpi/respeaker-2mic-v1_0-overlay.dtbo

# Copy it to the system boot folder
sudo cp overlays/rpi/respeaker-2mic-v1_0-overlay.dtbo /boot/firmware/overlays/respeaker-2mic-v1_0.dtbo
```

Why? The overlay tells the Pi’s CPU exactly which pins are connected to the WM8960 audio chip. Without it, the system cannot "see" the hardware.

#### 2. Enabling the Hardware
You must tell the Pi to load this overlay every time it starts up.

```Bash
# Add the instruction to your boot configuration
echo "dtoverlay=respeaker-2mic-v1_0" | sudo tee -a /boot/firmware/config.txt

# Reboot to activate the driver
sudo reboot
```

#### 3. Identifying Device IDs (The "Card Number")
Linux assigns numbers to audio devices. You need to know these numbers for your commands.

Find Recording ID:
```Bash
arecord -l
```
Find Playback ID:
```Bash
aplay -l
```

How to read it: Look for card X: seeed2micvoicec. Usually, it is Card 1.
In commands, we address this as plughw:1,0 (where 1 is the card and 0 is the device).

#### 4. Unmuting the Mixer (Crucial Step)
The WM8960 chip starts in a "muted" state to save power. You must manually open the internal routes.
If amixer says "Control not found", run that command to see the exact names your specific kernel uses for the switches.

```Bash
run amixer -c 1
```

Microphone (Input) Settings:
```Bash
# Enable the capture switch
amixer -c 1 sset 'Capture' 100%

# Connect the physical microphones (LINPUT1/RINPUT1) to the mixer
amixer -c 1 sset 'Left Boost Mixer LINPUT1' on
amixer -c 1 sset 'Right Boost Mixer RINPUT1' on

# Turn on the internal amplifiers (Boost)
amixer -c 1 sset 'Left Input Mixer Boost' on
amixer -c 1 sset 'Right Input Mixer Boost' on

# Set the digital volume to maximum
amixer -c 1 sset 'ADC PCM' 100%
```

Speaker (Output) Settings:
```Bash
# Set all output volumes to 100%
amixer -c 1 sset 'Playback' 100%
amixer -c 1 sset 'Speaker' 100%
amixer -c 1 sset 'Headphone' 100%

# Route the digital audio (PCM) to the physical outputs
amixer -c 1 sset 'Left Output Mixer PCM' on
amixer -c 1 sset 'Right Output Mixer PCM' on
```

#### 5. Saving Settings Permanently
Standard Linux resets these volumes on every reboot. Save them now:

```Bash
sudo alsactl store
```

#### 6. Usage & Testing
Now you can record and play back using the specific device address.

Record 5 seconds:

```Bash
arecord -D "plughw:1,0" -f S16_LE -r 16000 -d 5 -t wav test_mic.wav
```

THe file should has a size of ~157kB. To verify that run:
```Bash
ls -lh test_final.wav
```

Play back (on HAT speakers):

```Bash
aplay -D "plughw:1,0" test_mic.wav
```

Play back (on Raspberry Pi 3.5mm jack):

```Bash
aplay -D "plughw:0,0" test_mic.wav
```

Troubleshooting Tips
- Silent Recording: Re-run the amixer commands from Step 4. Usually, the "Boost" or "Capture" switches are the cause.
- Audio Open Error: The driver isn't loaded. Check if dtoverlay=respeaker-2mic-v1_0 is correctly spelled in /boot/firmware/config.txt.

---

## Python Voice Client Setup

This connects the Pi to the smart home assistant running on your PC.
The script (`voice_client.py`) listens for a wake word, records your command, sends it to the Voice Gateway service, and speaks the reply back.

### Architecture

```
[ReSpeaker HAT] --> voice_client.py --> POST /audio --> [Voice Gateway on PC :8765]
                                                               |
                                                       [Whisper transcription]
                                                               |
                                                        [LLM + Home Assistant]
                                                               |
                                                       JSON reply --> [pyttsx3 TTS on Pi]
```

The Voice Gateway must be running on your PC before starting the client on the Pi.
Start it with: `python assistant/services/voice_gateway/main.py`

### 1. System Packages

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv portaudio19-dev espeak espeak-data libespeak-dev
```

- `portaudio19-dev` — required by sounddevice to talk to ALSA
- `espeak` — only used as a fallback if no Piper model is configured

### 2. Copy Files to the Pi

Run this from your PC inside the smarthome project directory:

```bash
PI_IP=<your-pi-ip>   # e.g. 192.168.1.50
ssh pi@$PI_IP "mkdir -p ~/voice"
scp assistant/devices/raspberry_pi/voice_client.py pi@$PI_IP:~/voice/
scp assistant/devices/raspberry_pi/requirements.txt pi@$PI_IP:~/voice/
```

### 3. Create a Virtual Environment & Install Dependencies

On the Pi:

```bash
cd ~/voice
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

openwakeword will download its ONNX model files (~50 MB) on first run automatically.

### 4. Find the Correct sounddevice Indices

The script uses sounddevice which maps to ALSA device indices — mic (input) and speaker (output) can have **different** index numbers even on the same card.

Run this on the Pi:

```bash
source ~/voice/venv/bin/activate
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

Example output:
```
 0 bcm2835 Headphones: - (hw:0,0), output
 1 seeed2micvoicec: - (hw:1,0), input       <-- mic input index
 2 seeed2micvoicec: - (hw:1,0), output      <-- speaker output index
```

Note the two separate indices for input and output on the HAT (here `1` and `2`).

### 5. Download a Piper Voice Model

Piper is a neural TTS engine that sounds significantly better than espeak. Voice models run fully offline on the Pi.

Recommended German voices:

| Model | Quality | Size | Style |
|---|---|---|---|
| `de_DE-thorsten-high` | High | ~65 MB | Male, natural |
| `de_DE-thorsten_emotional-medium` | Medium | ~30 MB | Male, expressive |
| `de_DE-eva_k-x_low` | Low | ~5 MB | Female, fast |

Download on the Pi (example — thorsten high quality):

```bash
mkdir -p ~/voice/models
cd ~/voice/models

wget https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx.json
```

Test it before running the full client:

```bash
source ~/voice/venv/bin/activate
echo "Hallo, ich bin dein Sprachassistent." | \
  python3 -c "
import sys, sounddevice as sd, numpy as np
from piper.voice import PiperVoice
v = PiperVoice.load('models/de_DE-thorsten-high.onnx')
raw = b''.join(v.synthesize_stream_raw(sys.stdin.read()))
audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
sd.play(audio, samplerate=v.config.sample_rate)
sd.wait()
"
```

### 6. Configure Environment Variables

Create a `.env` file in `~/voice/` on the Pi:

```bash
cat > ~/voice/.env << 'EOF'
GATEWAY_URL=http://10.1.10.78:8765
GATEWAY_API_KEY=
DEVICE_ID=rpi-wohnzimmer
WAKE_WORD=hey_jarvis
AUDIO_INPUT_DEVICE=1
AUDIO_OUTPUT_DEVICE=2
TTS_MODEL=/home/pi/voice/models/de_DE-thorsten-high.onnx
WAKE_THRESHOLD=0.5
EOF
```

- `GATEWAY_URL`: IP of your PC where the Voice Gateway runs (port 8765).
- `GATEWAY_API_KEY`: Leave empty if you did not set one in the gateway's `.env`.
- `DEVICE_ID`: A name for this Pi. Use your Telegram chat_id here (numeric) to share conversation history with the Telegram bot.
- `WAKE_WORD`: Built-in choices: `hey_jarvis`, `alexa`, `hey_mycroft`, `hey_rhasspy`.
- `AUDIO_INPUT_DEVICE`: The mic (input) index from Step 4.
- `AUDIO_OUTPUT_DEVICE`: The speaker (output) index from Step 4. Used for both the acknowledgement beep and TTS — the script derives the ALSA device automatically.
- `TTS_MODEL`: Path to your downloaded Piper `.onnx` model file. Leave empty to fall back to espeak.

Load the `.env` when running the script:

```bash
cd ~/voice
source venv/bin/activate
export $(grep -v '^#' .env | xargs)
python3 voice_client.py
```

### 7. Verify the Connection

**Step 1 — Check the gateway is reachable from the Pi:**

```bash
curl http://10.1.10.78:8765/health
# Expected response: {"status":"ok"}
```

If this fails: the Voice Gateway is not running on your PC, or the IP/port is wrong.

**Step 2 — Send a text command to test end-to-end without audio:**

```bash
curl -X POST http://10.1.10.78:8765/text \
  -H "Content-Type: application/json" \
  -d '{"text": "Licht einschalten", "device_id": "rpi-wohnzimmer"}'
```

Expected: a JSON response like `{"reply": "Licht wurde eingeschaltet.", "actions_executed": [...]}`.

**Step 3 — Test audio capture + gateway with a real WAV:**

```bash
# Record 3 seconds
arecord -D "plughw:1,0" -f S16_LE -r 16000 -d 3 -t wav /tmp/cmd.wav

# POST the WAV to the gateway (same as voice_client.py does internally)
curl -X POST http://10.1.10.78:8765/audio \
  -F "file=@/tmp/cmd.wav;type=audio/wav" \
  -F "device_id=rpi-wohnzimmer"
```

If the gateway returns `{"error":"no_speech"}` the WAV was silent — re-run amixer Step 4.

### 8. Autostart with systemd

So the client starts automatically on boot:

```bash
sudo nano /etc/systemd/system/voice-client.service
```

Paste the following (adjust `User` and paths if your user is not `pi`):

```ini
[Unit]
Description=Smart Home Voice Client
After=network.target sound.target
Wants=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/voice
EnvironmentFile=/home/pi/voice/.env
ExecStart=/home/pi/voice/venv/bin/python3 voice_client.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable voice-client
sudo systemctl start voice-client

# Check it is running:
sudo systemctl status voice-client

# Watch live logs:
journalctl -u voice-client -f
```

### 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl /health` times out | Voice Gateway not running on PC | Start `python assistant/services/voice_gateway/main.py` on your PC |
| `{"error":"no_speech"}` from gateway | Mic not capturing audio | Re-run amixer commands from Section 4 above |
| `sounddevice.PortAudioError: Invalid device` | Wrong `AUDIO_INPUT_DEVICE` or `AUDIO_OUTPUT_DEVICE` | Run `python3 -c "import sounddevice; print(sounddevice.query_devices())"` and update `.env` |
| TTS speaks but no sound from HAT speaker | Speaker output not routed | Re-run amixer output commands and `sudo alsactl store` |
| Wake word never fires | Threshold too high or wrong wake word | Lower `WAKE_THRESHOLD` to `0.3`, or check `WAKE_WORD` spelling |
| `pyttsx3` init error | espeak not installed | `sudo apt install espeak espeak-data libespeak-dev` |
