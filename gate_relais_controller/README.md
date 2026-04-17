# Driveway Gate Controller

ESP32-C3 based 2-channel relay controller for a driveway gate. It supports two positions (walk and car) and can trigger a secondary pulse to "fix/stop" the gate automatically after a calculated delay.

## Hardware
- Board: ESP32-C3
- Relays: 
  - CH1 (Walk-Position) on GPIO6
  - CH2 (Car-Position) on GPIO7
- Relay Logic: Active LOW (LOW = ON, HIGH = OFF)

## Features
- Non-blocking architecture (no `delay()` used during normal loop).
- MQTT command control and status feedback.
- Configurable delay for automatic gate stopping (13s for walk, 38s for car).
- Telnet control (Port 2323) for remote debugging.
- OTA Updates.
- Last Will and Testament (LWT) for online status.

## MQTT Topics
- `tor/relais/cmd` : Send commands here (`ch1single`, `ch2single`, `ch1double`, `ch2double`)
- `tor/relais/status` : LWT status (`online`/`offline`)
- `tor/relais/lastaction` : Retained string of the last performed action

## Home Assistant
```yaml
mqtt:
  sensor:
    - name: "Driveway Gate Status"
      state_topic: "tor/relais/lastaction"
      availability_topic: "tor/relais/status"
      icon: "mdi:gate"
      
  button:
    - name: "Gate Walk Position"
      command_topic: "tor/relais/cmd"
      payload_press: "ch1single"
      availability_topic: "tor/relais/status"
      icon: "mdi:walk"
      
    - name: "Gate Car Position"
      command_topic: "tor/relais/cmd"
      payload_press: "ch2single"
      availability_topic: "tor/relais/status"
      icon: "mdi:car"
      
    - name: "Gate Walk Position (Fix)"
      command_topic: "tor/relais/cmd"
      payload_press: "ch1double"
      availability_topic: "tor/relais/status"
      icon: "mdi:walk"
      
    - name: "Gate Car Position (Fix)"
      command_topic: "tor/relais/cmd"
      payload_press: "ch2double"
      availability_topic: "tor/relais/status"
      icon: "mdi:car"
```

## Requirements
- ESP32 board package
- `PubSubClient`
- `TelnetStream`

## Setup
Update Wi-Fi and MQTT credentials in the source code before flashing.

## Changelog
- **v1.2**: Replaced blocking `delay()` with millis-based pulse struct to prevent unwanted behaviour with OTA,MQTT,other controls,... , enabled `WiFi.setSleep(false)` to fix unexpected disconnects, cleaned up serial logging.
- **v1.1**: Initial version.