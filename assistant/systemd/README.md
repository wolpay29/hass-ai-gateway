# systemd

Unit files for the assistant services and an installer that wires them up.

## Install

```bash
sudo ./install.sh                       # all services: venvs + deps + enable + start
sudo ./install.sh --no-start            # install only, don't enable/start
sudo ./install.sh voice_gateway notify_gateway   # subset
```

For each selected service the script:

1. creates `services/<svc>/<svc>_env/` (if missing)
2. installs `services/<svc>/requirements.txt`
3. copies the matching `.service` file into `/etc/systemd/system/`
4. runs `systemctl daemon-reload` and (unless `--no-start`) `enable` + `restart`

Re-running is safe.

## Units

| Service dir | Unit |
| --- | --- |
| `telegram_bot` | `telegram-bot.service` |
| `voice_gateway` | `voice-gateway.service` |
| `notify_gateway` | `notify-gateway.service` |

## Manual control

```bash
systemctl status notify-gateway
journalctl -u notify-gateway -f
systemctl restart notify-gateway
```
