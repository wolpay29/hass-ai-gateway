#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoOTA.h>

//wlan data
const char* ssid = "WLAN_SSID";
const char* password = "WLAN_PASSWORD";

//mqtt data
const char* mqtt_server = "MQTT_SERVER_IP";
const char* mqtt_user = "MQTT_USER";
const char* mqtt_pass = "MQTT_PASSWORD";

//topics
const char* mqtt_topic_avg = "pool/flow/avg";
const char* mqtt_topic_stddev = "pool/flow/stddev";
const char* mqtt_topic_stddev_10s = "pool/flow/stddev_10s";
//new topics for trend values
const char* mqtt_topic_avg_trend = "pool/flow/avg_trend";
const char* mqtt_topic_stddev_trend = "pool/flow/stddev_trend";

//GPIO
#define FLOW_PIN 4  // D2 on NodeMCU

volatile unsigned long pulseCount = 0;

WiFiClient espClient;
PubSubClient client(espClient);

//Interrupt service routine: Pulse count
void ICACHE_RAM_ATTR countPulse() {
  pulseCount++;
}

//wlan connect
void setup_wifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n WLAN connected. IP: " + WiFi.localIP().toString());
}

//MQTT reconnect
void reconnect() {
  while (!client.connected()) {
    Serial.print("Connecting to MQTT...");
    if (client.connect("ESP8266_Flow", mqtt_user, mqtt_pass)) {
      Serial.println("Connected!");
    } else {
      Serial.print("Error, rc=");
      Serial.print(client.state());
      Serial.println(" - try again in 5s");
      delay(5000);
    }
  }
}

//circlebuffer
#define BUFFER_SIZE 90                              //buffersize (90s)
float pulseBuffer[BUFFER_SIZE];                     //array for measurement values
int bufferIndex = 0;                                //act pos in buffer
bool bufferFilled = false;                          //buffer filled flag

//timecontrol
unsigned long lastMeasurement = 0;                  //time of the last 1s intervall measurment
unsigned long lastPublish = 0;                      //time of the last 10s intervall publish

//trend calculation variables
float lastAvg = 0;
float lastStdDev = 0;
float avgTrend = 0;                                 //filtered change rate of the flow
float stdDevTrend = 0;                              //filtered change rate of the standard deviation
const float trendAlpha = 0.4;                       //smoothing factor (0.1-0.3)

void setup() {
  Serial.begin(115200);

  pinMode(FLOW_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(FLOW_PIN), countPulse, FALLING);

  setup_wifi();
  client.setServer(mqtt_server, 1883);

  // OTA-Setup
  ArduinoOTA.setHostname("ESP8266-Flow");
  ArduinoOTA.begin();
  Serial.println("OTA ready");

  // All buffervalues initial to 0
  for (int i = 0; i < BUFFER_SIZE; i++) pulseBuffer[i] = 0;
}

void loop() {
  ArduinoOTA.handle();

  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();                     //act time

  //count every 1s detected pulses
  if (now - lastMeasurement >= 1000) {              //if 1s intervall reached
    lastMeasurement = now;                          //save time

    //count pulses, deactive interrupts in that time
    noInterrupts();
    unsigned long pulses = pulseCount;              //save
    pulseCount = 0;                                 //reset counter
    interrupts();

    float pulses_per_s = (float)pulses;             //to float

    //save values in circle buffer (rolling)
    pulseBuffer[bufferIndex] = pulses_per_s;        //save measurement
    bufferIndex = (bufferIndex + 1) % BUFFER_SIZE;  //shift index
    if (bufferIndex == 0) bufferFilled = true;      //buffer filled
  }

  //publish all 10s
  if (now - lastPublish >= 10000) {                 
    lastPublish = now;                              

    int count = bufferFilled ? BUFFER_SIZE : bufferIndex; //check
    if (count == 0) return;                         //no data -> no publish

    // 1. calc Moving Average
    float sum = 0;
    for (int i = 0; i < count; i++) sum += pulseBuffer[i];
    float avg = sum / count;                        //average

    // 2. calc standard deviation
    float variance = 0;
    for (int i = 0; i < count; i++)
      variance += pow(pulseBuffer[i] - avg, 2);     //square deviation of the average
    variance /= count;                              //average
    float stddev = sqrt(variance);                  //root = standard deviation

    // 3. calc standard deviation over 10s
    // --- calc 10s average and variance (last 10 values in buffer) ---
    int shortCount = min(count, 10);  // Max. 10 values
    //index of last saved value
    int startIndex = (bufferIndex - shortCount + BUFFER_SIZE) % BUFFER_SIZE;
    
    //average
    float shortSum = 0;
    for (int i = 0; i < shortCount; i++) {
      int idx = (startIndex + i) % BUFFER_SIZE;
      shortSum += pulseBuffer[idx];
    }
    float shortAvg = shortSum / shortCount;

    float shortVariance = 0;
    for (int i = 0; i < shortCount; i++) {
      int idx = (startIndex + i) % BUFFER_SIZE;
      shortVariance += pow(pulseBuffer[idx] - shortAvg, 2);
    }
    shortVariance /= shortCount;
    float shortStdDev = sqrt(shortVariance);

    // 4. calc trend (smoothed change rates)
    if (lastAvg > 0) { // avoid division by zero on first run
      // calc raw change (percentage change since last measurement)
      float rawAvgTrend = (avg - lastAvg) / lastAvg;
      float rawStdDevTrend = (stddev - lastStdDev) / lastStdDev;

      // apply exponential smoothing
      avgTrend = trendAlpha * rawAvgTrend + (1 - trendAlpha) * avgTrend;
      stdDevTrend = trendAlpha * rawStdDevTrend + (1 - trendAlpha) * stdDevTrend;
    } else {
      // set to 0 on first run
      avgTrend = 0;
      stdDevTrend = 0;
    }
    // save current values for next run
    lastAvg = avg;
    lastStdDev = stddev;

    //debug
    Serial.print("Avg: ");
    Serial.print(avg);
    Serial.print(" | StdDev: ");
    Serial.print(stddev);
    Serial.print(" | AvgTrend: ");
    Serial.print(avgTrend * 100); // in percent
    Serial.print("% | StdDevTrend: ");
    Serial.print(stdDevTrend * 100); // in percent
    Serial.println("%");

    // MQTT: publish data
    char msgBuffer[16];
    
    dtostrf(avg, 4, 2, msgBuffer);
    client.publish(mqtt_topic_avg, msgBuffer);

    dtostrf(stddev, 4, 2, msgBuffer);
    client.publish(mqtt_topic_stddev, msgBuffer);

    dtostrf(shortStdDev, 4, 2, msgBuffer);
    client.publish(mqtt_topic_stddev_10s, msgBuffer);

    // MQTT: publish trend values (in percent)
    dtostrf(avgTrend * 100, 4, 1, msgBuffer); 
    client.publish(mqtt_topic_avg_trend, msgBuffer);

    dtostrf(stdDevTrend * 100, 4, 1, msgBuffer);
    client.publish(mqtt_topic_stddev_trend, msgBuffer);
  }
}