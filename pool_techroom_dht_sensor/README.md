# Pool Technikraum Sensor

Monitors temperature and humidity in the pool technical room using an ESP8266 (D1 mini) and a DHT22 sensor.

The sensor measures environmental data every 30 seconds and publishes it via MQTT. It supports OTA updates and remote debugging via Telnet. Values are calibrated using fixed offsets.

## Hardware
- Board: ESP8266 (Wemos D1 mini)
- Sensor: DHT22 on GPIO4 / D2 (Moved from D4 for stability)

## Features
- Temperature and humidity measurement.
- Calibration offsets applied before publishing.
- Remote debugging over Wi-Fi using TelnetStream (Port 2323, type 'r' for manual read).
- MQTT Last Will and Testament (LWT) for online/offline tracking.
- Retained MQTT messages so Home Assistant receives the last state immediately.
- Auto-recovery for DHT sensor reads.
- Non-blocking delays and reconnect logic.
- OTA update support.

## MQTT
- `pool/technikraum/status` : Device status (`online` / `offline`) via LWT
- `pool/technikraum/temperature/state` : Temperature in °C
- `pool/technikraum/humidity/state` : Humidity in %

## Home Assistant
```yaml
mqtt:
  sensor:
    - name: "Pool Technikraum Temperature"
      state_topic: "pool/technikraum/temperature/state"
      unit_of_measurement: "°C"
      value_template: "{{ value }}"
      availability_topic: "pool/technikraum/status"
      device_class: temperature
    - name: "Pool Technikraum Humidity"
      state_topic: "pool/technikraum/humidity/state"
      unit_of_measurement: "%"
      value_template: "{{ value }}"
      availability_topic: "pool/technikraum/status"
      device_class: humidity
```

## Requirements
- `ESP8266WiFi`, `ArduinoOTA`
- `PubSubClient`
- `DHT sensor library` by Adafruit
- `TelnetStream`

## Setup
Update Wi-Fi and MQTT credentials in the source code before flashing.

## Changelog
- **v1.2**: Improved stability, moved DHT to D2/GPIO4, added auto-recovery for DHT NaN errors, optimized non-blocking timing.
- **v1.0**: Initial version.