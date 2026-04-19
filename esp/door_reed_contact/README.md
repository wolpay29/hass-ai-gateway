# Storage Room Door Sensor

An ESP32-C3 based door sensor utilizing a magnetic reed switch. It is designed for windowless rooms (like a storage room or pantry) where immediate light is needed upon entry.

Motion sensors often suffer from delayed reaction times or turn off the lights when there is no movement. This door sensor provides instant, reliable state changes (open/closed) via MQTT to trigger Home Assistant automations without delay.

## Hardware
- Board: ESP32-C3
- Sensor: Magnetic Reed Contact
- Wiring:
  - `NO` (Normally Open, White wire) -> GPIO4
  - `COM` (Common, Blue wire) -> GND
  - `NC` (Normally Closed, Black wire) -> Parked on GPIO5 (unused)

## Features
- Real-time door state detection.
- 50ms software debounce to prevent ghost triggers.
- Non-blocking MQTT and Wi-Fi reconnect logic.
- Retained MQTT messages so Home Assistant knows the state immediately after restarting.
- Last Will and Testament (LWT) for online/offline status tracking.
- OTA update support.

## MQTT Topics
- `storage/door/status` : `open` or `closed`
- `storage/door/availability` : `online` or `offline` (via LWT)

## Home Assistant
This configuration sets up the sensor as a proper binary sensor in Home Assistant with the `door` device class, so it appears correctly as open/closed in the dashboard.

```yaml
mqtt:
  binary_sensor:
    - name: "Storage Room Door"
      state_topic: "storage/door/status"
      availability_topic: "storage/door/availability"
      payload_on: "open"
      payload_off: "closed"
      device_class: door
```

### Automation Example
A simple Home Assistant automation to toggle the light instantly:

```yaml
alias: "Storage Room Light Auto Toggle"
mode: restart
trigger:
  - platform: state
    entity_id: binary_sensor.storage_room_door
action:
  - if:
      - condition: state
        entity_id: binary_sensor.storage_room_door
        state: "on"
    then:
      - service: light.turn_on
        target:
          entity_id: light.storage_room
    else:
      - service: light.turn_off
        target:
          entity_id: light.storage_room
```

## Requirements
- ESP32 board package
- `PubSubClient`
- `ArduinoOTA`

## Setup
Update Wi-Fi and MQTT credentials in the source code before flashing.

## Changelog
- **v1.0**: Initial version. Implemented 50ms debounce and non-blocking reconnects.