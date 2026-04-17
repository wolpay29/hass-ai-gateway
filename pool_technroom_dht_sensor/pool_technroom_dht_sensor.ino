#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoOTA.h>
#include <DHT.h>
#include <TelnetStream.h>

// WLAN data
const char* ssid = "WLAN_SSID";
const char* password = "WLAN_PASSWORD";

// MQTT data
const char* mqtt_server = "MQTT_SERVER_IP";
const uint16_t mqtt_port = 1883;
const char* mqtt_user = "MQTT_USER";
const char* mqtt_pass = "MQTT_PASSWORD";

// Topics
const char* TSTATE_TEMP = "pool/technikraum/temperature/state";
const char* TSTATE_HUM = "pool/technikraum/humidity/state";
const char* TSTATUS = "pool/technikraum/status";

// DHT Setup
#define DHTPIN D4 // e.g. D4/GPIO2 on shield
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

// Globals
WiFiClient espClient;
PubSubClient mqtt(espClient);

unsigned long lastReconnectAttempt = 0;
const unsigned long reconnectInterval = 5000;
unsigned long lastMeasure = 0;
const uint32_t measureIntervalMs = 30000;
bool statusPublishedOnline = false;

// Calibration offsets
float offsetC = -5.7f;
float offsetH = 18.3f;

// WLAN connect
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
    Serial.println("WLAN connection failed, proceeding with OTA/MQTT retries...");
  }
}

// OTA Setup
void setupOTA() {
  ArduinoOTA.setHostname("pool-technikraum-sensor");
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

// MQTT reconnect
bool mqttReconnect() {
  Serial.print("Connecting to MQTT...");
  TelnetStream.print("Connecting to MQTT...");

  String clientId = String("ESP8266-pooltechnikraum-") + String(ESP.getChipId(), HEX);

  // Last-Will: offline retained
  const char* willTopic = TSTATUS;
  const char* willMessage = "offline";
  int willQos = 1;
  bool willRetain = true;

  bool ok = mqtt.connect(clientId.c_str(), mqtt_user, mqtt_pass, willTopic, willQos, willRetain, willMessage);
  if (ok) {
    Serial.println("Connected!");
    TelnetStream.println("Connected!");
    // publish online status
    mqtt.publish(TSTATUS, "online", true);
    statusPublishedOnline = true;
    // initial measure
    measureAndPublish();
  } else {
    Serial.print("Error, rc=");
    Serial.println(mqtt.state());
    TelnetStream.print("Error, rc=");
    TelnetStream.println(mqtt.state());
  }
  return ok;
}

// Publish states
void publishStates(float t, float h) {
  // clamp humidity
  if (h < 0) h = 0;
  if (h > 100) h = 100;

  char tBuf[8];
  char hBuf[8];

  dtostrf(t, 4, 1, tBuf);
  dtostrf(h, 4, 1, hBuf);

  // retained publish
  mqtt.publish(TSTATE_TEMP, tBuf, true);
  mqtt.publish(TSTATE_HUM, hBuf, true);

  char log[80];
  snprintf(log, sizeof(log), "Published: %sC, %s%%", tBuf, hBuf);
  Serial.println(log);
  TelnetStream.println(log);
}

// Measure and publish
void measureAndPublish() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    TelnetStream.println("First DHT read NaN, retry...");
    delay(5000);
    h = dht.readHumidity();
    t = dht.readTemperature();
  }

  if (!isnan(h) && !isnan(t)) {
    // apply offsets
    t += offsetC;
    h += offsetH;
    publishStates(t, h);
  } else {
    Serial.println("DHT Read Error: NaN");
    TelnetStream.println("DHT Read Error: NaN");
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nBooting Pool Technikraum Sensor...");

  setup_wifi();

  TelnetStream.begin(2323);
  TelnetStream.println("Telnet ready");

  dht.begin();
  delay(2000); // settle time

  mqtt.setServer(mqtt_server, mqtt_port);
  setupOTA();

  lastMeasure = millis();
}

void loop() {
  // Telnet commands
  while (TelnetStream.available()) {
    int c = TelnetStream.read();
    if (c == 'r' || c == 'R') {
      TelnetStream.println("Manual read requested");
      if (mqtt.connected()) {
        measureAndPublish();
      } else {
        TelnetStream.println("MQTT not connected");
      }
    }
  }

  // MQTT reconnect handling
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

  // Periodic measurement
  unsigned long now = millis();
  if (now - lastMeasure > measureIntervalMs) {
    lastMeasure = now;
    if (mqtt.connected()) {
      measureAndPublish();
    }
  }

  ArduinoOTA.handle();
  TelnetStream.flush();
}