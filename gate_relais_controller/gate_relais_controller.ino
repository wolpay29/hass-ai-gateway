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
#define RELAY_CH1 6  // GPIO6 Walk-Position
#define RELAY_CH2 7  // GPIO7 Car-Position

// Relay Timing
const uint16_t PULSE_MS = 500;           // 500ms pulse
const uint16_t DELAY_MS_WALK_FIX = 13000; // 13s for Walk-Position fix
const uint16_t DELAY_MS_CAR_FIX = 38000;  // 38s for Car-Position fix

// Relay Logic
#define RELAY_ON LOW
#define RELAY_OFF HIGH

// --- Globals ---
WiFiClient espClient;
PubSubClient mqtt(espClient);

unsigned long lastReconnectAttempt = 0;
const unsigned long reconnectInterval = 5000;
bool statusPublishedOnline = false;

// State Machine
enum RelayState {
  IDLE,
  CH1_WAIT_FIX,
  CH2_WAIT_FIX
};

RelayState relayState = IDLE;
unsigned long stateStartTime = 0;
uint16_t currentDelayMs = 0;

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to WLAN: ");
  Serial.println(ssid);

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
    Serial.print("WLAN connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WLAN connection failed");
  }
}

void setupOTA() {
  ArduinoOTA.setHostname("tor-relais-esp32c3");
  ArduinoOTA.onStart([]() {
    Serial.println("Starting OTA Update...");
    TelnetStream.println("Starting OTA Update...");
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\nOTA Update finished!");
    TelnetStream.println("OTA Update finished!");
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    char buf[64];
    snprintf(buf, sizeof(buf), "OTA Progress: %u%%", (progress / (total / 100)));
    Serial.println(buf);
    TelnetStream.println(buf);
  });
  ArduinoOTA.onError([](ota_error_t error) {
    char buf[64];
    snprintf(buf, sizeof(buf), "OTA Error: %u", error);
    Serial.println(buf);
    TelnetStream.println(buf);
  });
  ArduinoOTA.begin();
}

void pulseRelay(uint8_t pin, const char* channelName) {
  char log[80];
  snprintf(log, sizeof(log), "Switching %s for %dms", channelName, PULSE_MS);
  Serial.println(log);
  TelnetStream.println(log);

  digitalWrite(pin, RELAY_ON);
  delay(PULSE_MS); // Blocking delay!
  digitalWrite(pin, RELAY_OFF);
}

void cancelPendingOperation() {
  if (relayState != IDLE) {
    char log[100];
    snprintf(log, sizeof(log), "Wait operation cancelled, was in state %d", relayState);
    Serial.println(log);
    TelnetStream.println(log);
    mqtt.publish(TLASTACTION, "Wait operation cancelled", true);
    relayState = IDLE;
  }
}

void executeCommand(const char* cmd) {
  char logMsg[100];
  
  cancelPendingOperation();

  if (strcmp(cmd, "ch1single") == 0) {
    pulseRelay(RELAY_CH1, "Walk-Position");
    snprintf(logMsg, sizeof(logMsg), "Walk-Position triggered");
    relayState = IDLE;
  } 
  else if (strcmp(cmd, "ch2single") == 0) {
    pulseRelay(RELAY_CH2, "Car-Position");
    snprintf(logMsg, sizeof(logMsg), "Car-Position triggered");
    relayState = IDLE;
  } 
  else if (strcmp(cmd, "ch1double") == 0) {
    pulseRelay(RELAY_CH1, "Walk-Position (Wait for fix)");
    relayState = CH1_WAIT_FIX;
    stateStartTime = millis();
    currentDelayMs = DELAY_MS_WALK_FIX;
    snprintf(logMsg, sizeof(logMsg), "Walk-Position triggered, waiting %ds for fix", DELAY_MS_WALK_FIX / 1000);
  } 
  else if (strcmp(cmd, "ch2double") == 0) {
    pulseRelay(RELAY_CH2, "Car-Position (Wait for fix)");
    relayState = CH2_WAIT_FIX;
    stateStartTime = millis();
    currentDelayMs = DELAY_MS_CAR_FIX;
    snprintf(logMsg, sizeof(logMsg), "Car-Position triggered, waiting %ds for fix", DELAY_MS_CAR_FIX / 1000);
  } 
  else {
    snprintf(logMsg, sizeof(logMsg), "Unknown command: %s", cmd);
    Serial.println(logMsg);
    TelnetStream.println(logMsg);
    return;
  }

  mqtt.publish(TLASTACTION, logMsg, true);
  Serial.println(logMsg);
  TelnetStream.println(logMsg);
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

  const char* willTopic = TSTATUS;
  const char* willMessage = "offline";
  int willQos = 1;
  bool willRetain = true;

  bool ok = mqtt.connect(clientId.c_str(), mqtt_user, mqtt_pass, willTopic, willQos, willRetain, willMessage);
  
  if (ok) {
    Serial.println("Connected");
    TelnetStream.println("Connected");
    mqtt.publish(TSTATUS, "online", true);
    statusPublishedOnline = true;
    mqtt.subscribe(TCMD);
    Serial.print("Subscribed to ");
    Serial.println(TCMD);
  } else {
    Serial.print("Error, rc=");
    Serial.println(mqtt.state());
  }
  return ok;
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
  TelnetStream.println("Telnet ready on port 2323");
  TelnetStream.println("Commands:");
  TelnetStream.println("1: Walk-Position single");
  TelnetStream.println("2: Car-Position single");
  TelnetStream.println("3: Walk-Position fix (13s)");
  TelnetStream.println("4: Car-Position fix (38s)");

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

  if (relayState != IDLE) {
    unsigned long elapsed = millis() - stateStartTime;
    
    if (relayState == CH1_WAIT_FIX && elapsed >= DELAY_MS_WALK_FIX) {
      pulseRelay(RELAY_CH1, "Walk-Position Fix");
      mqtt.publish(TLASTACTION, "Walk-Position fixed", true);
      Serial.println("Walk-Position fixed");
      TelnetStream.println("Walk-Position fixed");
      relayState = IDLE;
    } 
    else if (relayState == CH2_WAIT_FIX && elapsed >= DELAY_MS_CAR_FIX) {
      pulseRelay(RELAY_CH2, "Car-Position Fix");
      mqtt.publish(TLASTACTION, "Car-Position fixed", true);
      Serial.println("Car-Position fixed");
      TelnetStream.println("Car-Position fixed");
      relayState = IDLE;
    }
  }

  ArduinoOTA.handle();
  TelnetStream.flush();
}