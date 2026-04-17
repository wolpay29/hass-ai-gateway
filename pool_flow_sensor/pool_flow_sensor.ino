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

//GPIO
#define FLOW_PIN 4  // D2 auf NodeMCU

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
#define BUFFER_SIZE 60                              //buffersize
float pulseBuffer[BUFFER_SIZE];                     //array for measurement values
int bufferIndex = 0;                                //act pos in buffer
bool bufferFilled = false;                          //buffer filled flag

//timecontrol
unsigned long lastMeasurement = 0;                  //time of the las 1s intervall measurment
unsigned long lastPublish = 0;                      //time of the last 10s intervall publish

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

  //count every 1s detected pusles
  if (now - lastMeasurement >= 1000) {              //if 1s intervall reached
    lastMeasurement = now;                          //save time

    //count pulses, deactive interrupts in that time
    noInterrupts();
    unsigned long pulses = pulseCount;              //save
    pulseCount = 0;                                 //reset counter
    interrupts();

    float pulses_per_s = (float)pulses;             //to float

    //save values in circel buffer (rolling)
    pulseBuffer[bufferIndex] = pulses_per_s;        //save measurement
    bufferIndex = (bufferIndex + 1) % BUFFER_SIZE;  //shift index
    if (bufferIndex == 0) bufferFilled = true;      //buffer filled
  }

  //publish all 10s AVG and standard deviation
  if (now - lastPublish >= 10000) {                 
    lastPublish = now;                       

    int count = bufferFilled ? BUFFER_SIZE : bufferIndex; //chekc
    if (count == 0) return;                         //no data -> no publish

    //(Moving Average)
    float sum = 0;
    for (int i = 0; i < count; i++) sum += pulseBuffer[i];
    float avg = sum / count;                        //avrage


    //standard deviation
    float variance = 0;
    for (int i = 0; i < count; i++)
      variance += pow(pulseBuffer[i] - avg, 2);     //quare deviation of the average
    variance /= count;                              //average
    float stddev = sqrt(variance);                  //root = standard deviation



    //standard deviation over 10s
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


    //debug
    Serial.print("Avg (60s): ");
    Serial.print(avg);
    Serial.print(" | StdDev: ");
    Serial.println(stddev);

    // MQTT: publish avg
    char avgMsg[16];
    dtostrf(avg, 4, 2, avgMsg);                     //float to string
    client.publish(mqtt_topic_avg, avgMsg);         //send to topic

    // MQTT: publish standard deviation
    char stdMsg[16];
    dtostrf(stddev, 4, 2, stdMsg);                  
    client.publish(mqtt_topic_stddev, stdMsg);   

    // MQTT: publish standard deviation 10s
    char shortStdMsg[16];
    dtostrf(shortStdDev, 4, 2, shortStdMsg);             
    client.publish(mqtt_topic_stddev_10s, shortStdMsg);   
  }
}
