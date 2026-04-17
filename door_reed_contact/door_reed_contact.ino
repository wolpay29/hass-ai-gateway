#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoOTA.h>

// --- WLAN ---
const char* ssid = "WLAN_SSID";
const char* password = "WLAN_PASSWORD";

// --- MQTT ---
const char* mqtt_server = "MQTT_SERVER_IP";
const uint16_t mqtt_port = 1883;
const char* mqtt_user = "MQTT_USER";
const char* mqtt_pass = "MQTT_PASSWORD";

// --- Topics & Payloads ---
const char* mqtt_topic_door = "storage/door/status";
const char* mqtt_topic_availability = "storage/door/availability";
const char* payload_online = "online";
const char* payload_offline = "offline";

// --- Hardware ---
// Magnetic Reed Contact Setup
#define REED_PIN 4   // NO (white) -> Pin 4, COM (blue) -> GND
#define PARK_PIN 5   // NC (black) -> Pin 5 (parked/unused)

// --- Globals ---
WiFiClient espClient;
PubSubClient mqtt(espClient);

unsigned long lastReconnectAttempt = 0;
const unsigned long reconnectInterval = 5000;

// --- Debounce & State ---
const unsigned long debounceMs = 50;
int lastStableState = HIGH;       // INPUT_PULLUP: HIGH = open
int lastPublishedState = HIGH;
int lastRead = HIGH;
unsigned long lastEdgeMs = 0;
unsigned long lastHeartbeatLog = 0;

void logDoorState(const char* context, int rawState) {
  const char* interpreted = (rawState == HIGH) ? "open" : "closed";
  Serial.printf("[%s] raw=%d interpreted=%s (debounce=%lums)\n", context, rawState, interpreted, debounceMs);
}

void publishDoorState(int state) {
  const char* payload = (state == HIGH) ? "open" : "closed";
  bool retained = true; // Retained so HA knows the state after a restart
  
  bool ok = mqtt.publish(mqtt_topic_door, payload, retained);
  Serial.printf("MQTT publish -> %s : %s (retained) %s\n", mqtt_topic_door, payload, ok ? "OK" : "FAIL");
  
  lastPublishedState = state;
}

void setup_wifi() {
  Serial.println();
  Serial.printf("Connecting to WLAN: %s\n", ssid);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  uint8_t attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 60) { 
    delay(500); 
    Serial.print("."); 
    attempts++;
  }
  Serial.println();
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WLAN connected, IP=%s RSSI=%d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("WLAN connection failed");
  }
}

void setupOTA() {
  ArduinoOTA.setHostname("ESP32C3-Door");
  ArduinoOTA.onStart([]() { Serial.println("OTA Start..."); });
  ArduinoOTA.onEnd([]() { Serial.println("\nOTA finished!"); });
  ArduinoOTA.onError([](ota_error_t error) { Serial.printf("OTA Error: %u\n", error); });
  ArduinoOTA.begin();
  Serial.println("OTA ready");
}

bool mqttReconnect() {
  String clientId = String("ESP32C3-Door-") + String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.printf("Connecting to MQTT as %s... ", clientId.c_str());
  
  // Last Will and Testament (LWT)
  int willQos = 1;
  bool willRetain = true;
  
  bool ok = mqtt.connect(clientId.c_str(), mqtt_user, mqtt_pass, mqtt_topic_availability, willQos, willRetain, payload_offline);
  
  if (ok) {
    Serial.println("Connected");
    // Publish online status
    mqtt.publish(mqtt_topic_availability, payload_online, true);
    // Publish current door state immediately after reconnect
    publishDoorState(lastStableState);
  } else {
    Serial.printf("Failed, rc=%d\n", mqtt.state());
  }
  return ok;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nBooting ESP32-C3 Storage Door Sensor...");

  pinMode(REED_PIN, INPUT_PULLUP);
  pinMode(PARK_PIN, INPUT_PULLUP); // Reserve/Park

  lastRead = digitalRead(REED_PIN);
  lastStableState = lastRead;
  lastPublishedState = lastStableState;
  logDoorState("INIT", lastStableState);

  setup_wifi();
  setupOTA();
  
  mqtt.setServer(mqtt_server, mqtt_port);
  lastHeartbeatLog = millis();
}

void loop() {
  ArduinoOTA.handle();

  // WiFi reconnect
  if (WiFi.status() != WL_CONNECTED) {
    setup_wifi();
  }

  // MQTT reconnect (non-blocking)
  if (!mqtt.connected()) {
    unsigned long now = millis();
    if (now - lastReconnectAttempt > reconnectInterval) {
      lastReconnectAttempt = now;
      if (mqttReconnect()) {
        lastReconnectAttempt = 0;
      }
    }
  } else {
    mqtt.loop();
  }

  int currentRead = digitalRead(REED_PIN);
  unsigned long now = millis();

  // Detect edge
  if (currentRead != lastRead) {
    lastRead = currentRead;
    lastEdgeMs = now;
  }

  // Debounce logic
  if ((now - lastEdgeMs) >= debounceMs && lastStableState != lastRead) {
    lastStableState = lastRead;
    logDoorState("STABLE", lastStableState);
    
    if (lastStableState != lastPublishedState && mqtt.connected()) {
      publishDoorState(lastStableState);
    }
  }

  // Heartbeat Log to Serial
  if (now - lastHeartbeatLog >= 30000) {
    lastHeartbeatLog = now;
    Serial.printf("Heartbeat: WiFi=%s RSSI=%d MQTT=%s State=%s\n",
                  (WiFi.status() == WL_CONNECTED ? "OK" : "DOWN"),
                  WiFi.RSSI(),
                  (mqtt.connected() ? "OK" : "DOWN"),
                  (lastStableState == HIGH ? "open" : "closed"));
  }
}