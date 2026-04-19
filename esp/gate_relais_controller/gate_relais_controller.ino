#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoOTA.h>
#include <TelnetStream.h>

// --- WLAN ---
const char* ssid = "WLAN_SSID";
const char* password = "WLAN_PASSWORD";

// --- MQTT ---
const char* mqtt_server = "MQTT_SERVER_IP";
const uint16_t mqtt_port = 1883;
const char* mqtt_user = "MQTT_USER";
const char* mqtt_pass = "MQTT_PASSWORD";

// MQTT Topics
const char* TCMD = "tor/relais/cmd";
const char* TSTATUS = "tor/relais/status";
const char* TLASTACTION = "tor/relais/lastaction";

// --- Hardware ---
#define RELAY_CH1 6
#define RELAY_CH2 7

// Relay Timing
const uint16_t PULSE_MS = 500;
const uint16_t DELAY_MS_WALK_FIX = 13000;
const uint16_t DELAY_MS_CAR_FIX = 38000;

// Relay Logic
#define RELAY_ON LOW
#define RELAY_OFF HIGH

// --- Globals ---
WiFiClient espClient;
PubSubClient mqtt(espClient);

unsigned long lastReconnectAttempt = 0;
const unsigned long reconnectInterval = 5000;
bool statusPublishedOnline = false;

// --- State Machine ---
enum RelayState {
  IDLE,
  CH1_WAIT_FIX,
  CH2_WAIT_FIX
};
RelayState relayState = IDLE;
unsigned long stateStartTime = 0;
uint16_t currentDelayMs = 0;

// --- Non-blocking Pulse struct ---
struct Pulse {
  uint8_t pin = 0;
  unsigned long startTime = 0;
  bool active = false;
} pulse;

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to WLAN: ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  WiFi.setSleep(false); // Fixes disconnects

  uint8_t attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 60) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WLAN connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WLAN connection failed");
  }
}

void setupOTA() {
  ArduinoOTA.setHostname("tor-relais-esp32c3");
  ArduinoOTA.onStart([]() {
    Serial.println("OTA Start...");
    TelnetStream.println("OTA Start...");
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\nOTA finished!");
    TelnetStream.println("OTA finished!");
  });
  ArduinoOTA.onError([](ota_error_t error) {
    char buf[64];
    snprintf(buf, sizeof(buf), "OTA Error: %u", error);
    Serial.println(buf);
    TelnetStream.println(buf);
  });
  ArduinoOTA.begin();
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  char msg[128];
  if (length >= sizeof(msg)) length = sizeof(msg) - 1;
  memcpy(msg, payload, length);
  msg[length] = '\0';

  char log[150];
  snprintf(log, sizeof(log), "MQTT RX: %s %s", topic, msg);
  Serial.println(log);
  TelnetStream.println(log);

  if (strcmp(topic, TCMD) == 0) {
    executeCommand(msg);
  }
}

bool mqttReconnect() {
  Serial.print("Connecting to MQTT...");
  TelnetStream.print("Connecting to MQTT...");

  String clientId = String("ESP32C3-relais-") + String((uint32_t)ESP.getEfuseMac(), HEX);

  bool ok = mqtt.connect(clientId.c_str(), mqtt_user, mqtt_pass, TSTATUS, 1, true, "offline");
  if (ok) {
    Serial.println("Connected");
    TelnetStream.println("Connected");
    mqtt.publish(TSTATUS, "online", true);
    statusPublishedOnline = true;
    mqtt.subscribe(TCMD);
  } else {
    Serial.print("Error, rc=");
    Serial.println(mqtt.state());
  }
  return ok;
}

// --- Pulse Logic ---
void startPulse(uint8_t pin) {
  digitalWrite(pin, RELAY_ON);
  pulse.pin = pin;
  pulse.startTime = millis();
  pulse.active = true;
}

void checkPulse() {
  if (pulse.active && millis() - pulse.startTime >= PULSE_MS) {
    digitalWrite(pulse.pin, RELAY_OFF);
    pulse.active = false;
  }
}

void executeCommand(const char* cmd) {
  relayState = IDLE; // cancel pending

  if (strcmp(cmd, "ch1single") == 0) {
    startPulse(RELAY_CH1);
    mqtt.publish(TLASTACTION, "Walk-Position single", true);
  } 
  else if (strcmp(cmd, "ch2single") == 0) {
    startPulse(RELAY_CH2);
    mqtt.publish(TLASTACTION, "Car-Position single", true);
  } 
  else if (strcmp(cmd, "ch1double") == 0) {
    startPulse(RELAY_CH1);
    relayState = CH1_WAIT_FIX;
    stateStartTime = millis();
    currentDelayMs = DELAY_MS_WALK_FIX;
    mqtt.publish(TLASTACTION, "Walk-Position waiting for fix", true);
  } 
  else if (strcmp(cmd, "ch2double") == 0) {
    startPulse(RELAY_CH2);
    relayState = CH2_WAIT_FIX;
    stateStartTime = millis();
    currentDelayMs = DELAY_MS_CAR_FIX;
    mqtt.publish(TLASTACTION, "Car-Position waiting for fix", true);
  } 
  else {
    mqtt.publish(TLASTACTION, "Unknown command", true);
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nBooting ESP32-C3 Garage Door Controller...");

  pinMode(RELAY_CH1, OUTPUT);
  pinMode(RELAY_CH2, OUTPUT);
  digitalWrite(RELAY_CH1, RELAY_OFF);
  digitalWrite(RELAY_CH2, RELAY_OFF);

  setup_wifi();

  TelnetStream.begin(2323);
  mqtt.setServer(mqtt_server, mqtt_port);
  mqtt.setCallback(mqttCallback);

  setupOTA();
}

void loop() {
  while (TelnetStream.available()) {
    int c = TelnetStream.read();
    if (c == '1') executeCommand("ch1single");
    else if (c == '2') executeCommand("ch2single");
    else if (c == '3') executeCommand("ch1double");
    else if (c == '4') executeCommand("ch2double");
  }

  if (!mqtt.connected()) {
    unsigned long now = millis();
    if (now - lastReconnectAttempt > reconnectInterval) {
      lastReconnectAttempt = now;
      if (mqttReconnect()) lastReconnectAttempt = 0;
    }
  } else {
    mqtt.loop();
  }

  checkPulse();

  if (relayState != IDLE) {
    if (millis() - stateStartTime >= currentDelayMs) {
      if (relayState == CH1_WAIT_FIX) {
        startPulse(RELAY_CH1);
        mqtt.publish(TLASTACTION, "Walk-Position fixed", true);
      } 
      else if (relayState == CH2_WAIT_FIX) {
        startPulse(RELAY_CH2);
        mqtt.publish(TLASTACTION, "Car-Position fixed", true);
      }
      relayState = IDLE;
    }
  }

  ArduinoOTA.handle();
  TelnetStream.flush();
}