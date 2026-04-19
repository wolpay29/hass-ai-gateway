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
#define DHTPIN D2 // GPIO4 for better stability
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

// Timing
const uint32_t MEASURE_INTERVAL_MS = 30000;
const uint32_t DHT_MIN_INTERVAL_MS = 2500;
const uint32_t MQTT_RECONNECT_MS = 5000;

// Globals
WiFiClient espClient;
PubSubClient mqtt(espClient);

unsigned long lastMeasure = 0;
unsigned long lastDhtRead = 0;
unsigned long lastMqttReconnect = 0;

// Calibration offsets
float offsetC = -5.7f;
float offsetH = 18.3f;

// WLAN connect
void setup_wifi() {
  Serial.print("Connecting WLAN: ");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  uint8_t tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 60) {
    delay(500);
    Serial.print(".");
    tries++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WLAN OK, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WLAN ERROR");
  }
}

// OTA Setup
void setupOTA() {
  ArduinoOTA.setHostname("pool-technikraum-sensor");
  ArduinoOTA.onStart([]() {
    Serial.println("OTA Start");
    TelnetStream.println("OTA Start");
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\nOTA End");
    TelnetStream.println("OTA End");
  });
  ArduinoOTA.onError([](ota_error_t e) {
    TelnetStream.printf("OTA Error: %u\n", e);
  });
  ArduinoOTA.begin();
}

// MQTT reconnect
bool mqttReconnect() {
  Serial.print("MQTT connect... ");
  TelnetStream.print("MQTT connect... ");

  String cid = String("ESP8266-pool-") + String(ESP.getChipId(), HEX);

  bool ok = mqtt.connect(cid.c_str(), mqtt_user, mqtt_pass, TSTATUS, 1, true, "offline");
  if (ok) {
    Serial.println("OK");
    TelnetStream.println("OK");
    mqtt.publish(TSTATUS, "online", true);
  } else {
    Serial.print("FAIL rc=");
    Serial.println(mqtt.state());
    TelnetStream.printf("FAIL rc=%d\n", mqtt.state());
  }
  return ok;
}

// DHT Recovery
void recoverDHT() {
  TelnetStream.println("DHT recover...");
  dht.begin();
  delay(2000);
}

// DHT Read
bool readDHT(float &t, float &h) {
  if (millis() - lastDhtRead < DHT_MIN_INTERVAL_MS) return false;
  lastDhtRead = millis();

  h = dht.readHumidity();
  t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    TelnetStream.println("DHT NaN -> recover");
    recoverDHT();
    return false;
  }

  t += offsetC;
  h += offsetH;

  if (h < 0) h = 0;
  if (h > 100) h = 100;

  return true;
}

// Publish states
void publishStates(float t, float h) {
  char tb[8], hb[8];
  dtostrf(t, 4, 1, tb);
  dtostrf(h, 4, 1, hb);

  mqtt.publish(TSTATE_TEMP, tb, true);
  mqtt.publish(TSTATE_HUM, hb, true);

  TelnetStream.printf("PUB: %sC, %s%%\n", tb, hb);
  Serial.printf("PUB: %sC, %s%%\n", tb, hb);
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nPool Technikraum Sensor");

  setup_wifi();

  TelnetStream.begin(2323);
  TelnetStream.println("Telnet ready");

  dht.begin();
  delay(2000);

  mqtt.setServer(mqtt_server, mqtt_port);
  setupOTA();

  lastMeasure = millis();
}

void loop() {
  // Telnet commands
  while (TelnetStream.available()) {
    char c = TelnetStream.read();
    if (c == 'r') {
      TelnetStream.println("Manual read");
      float t, h;
      if (mqtt.connected() && readDHT(t, h)) {
        publishStates(t, h);
      }
    }
  }

  // MQTT maintain
  if (!mqtt.connected()) {
    if (millis() - lastMqttReconnect > MQTT_RECONNECT_MS) {
      lastMqttReconnect = millis();
      mqttReconnect();
    }
  } else {
    mqtt.loop();
  }

  // Periodic measurement
  if (millis() - lastMeasure > MEASURE_INTERVAL_MS) {
    lastMeasure = millis();
    float t, h;
    if (mqtt.connected() && readDHT(t, h)) {
      publishStates(t, h);
    }
  }

  ArduinoOTA.handle();
  TelnetStream.flush();
}