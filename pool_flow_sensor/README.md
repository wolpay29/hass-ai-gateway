# Pool Flow Sensor

Monitors water returning from the pool overflow channel using an ESP8266 and a hall effect flow sensor on GPIO4 / D2.

The sensor measures pulses per second. No conversion to mass flow or volume flow is done, as the overflow return is not a continuous stream and a physical conversion would not be accurate. The raw pulse rate is sufficient to detect whether water is flowing and how much activity is happening. This can be used to detect pool usage and trigger the pump automatically.

## Hardware
- Board: ESP8266 (NodeMCU)
- Sensor: Hall effect flow sensor on GPIO4 / D2

## Features
- Pulse counting by interrupt.
- 60-second ring buffer for historical data.
- Calculates moving average (60s).
- Calculates standard deviation (60s) and short-term standard deviation (10s).
- OTA update support.

## MQTT
Measurements are published every 10 seconds.
- `pool/flow/avg` : Moving average (60s)
- `pool/flow/stddev` : Standard deviation (60s)
- `pool/flow/stddev_10s` : Short-term standard deviation (10s)

## Home Assistant
```yaml
mqtt:
  sensor:
    - name: "Pool Flow Average"
      state_topic: "pool/flow/avg"
      unit_of_measurement: "p/s"
      value_template: "{{ value }}"
    - name: "Pool Flow StdDev"
      state_topic: "pool/flow/stddev"
      unit_of_measurement: "p/s"
      value_template: "{{ value }}"
    - name: "Pool Flow StdDev 10s"
      state_topic: "pool/flow/stddev_10s"
      unit_of_measurement: "p/s"
      value_template: "{{ value }}"
```

## Requirements
- `ESP8266WiFi` (included in board package)
- `ArduinoOTA` (included in board package)
- `PubSubClient` (install via Library Manager)

## Setup
Update Wi-Fi and MQTT credentials in the source code before flashing.

## Changelog
- **v1.1**: Switched to 60s ring buffer, added standard deviation over 60s and 10s, split data into multiple MQTT topics.
- **v1.0**: Initial version with basic 5-value moving average.