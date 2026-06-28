#include <WiFi.h>
#include <PubSubClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// --- Config: WiFi ---
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// --- Config: MQTT (Shiftr.io) ---
const char* mqtt_server = "madrjl-websocket.cloud.shiftr.io";
const int mqtt_port = 1883;
const char* mqtt_user = "madrjl-websocket";
const char* mqtt_password = "R5vzRevrusL8y35I";
const char* mqtt_client_id = "ESP32_Gate_Controller";

// --- Config: Hardware Pins ---
#define SS_PIN 5
#define RST_PIN 22
#define SERVO_PIN 18

// --- Objects ---
WiFiClient espClient;
PubSubClient client(espClient);
MFRC522 mfrc522(SS_PIN, RST_PIN);
Servo gateServo;

// --- State Variables ---
int gateClosedAngle = 0;
int gateOpenAngle = 90;
bool isGateOpen = false;
unsigned long gateOpenedAt = 0;
const unsigned long gateOpenDuration = 5000; // 5 seconds
unsigned long lastHeartbeat = 0;

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");
  
  String message;
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.println(message);

  if (String(topic) == "gate/open") {
    DynamicJsonDocument doc(256);
    DeserializationError error = deserializeJson(doc, message);
    if (!error) {
      String action = doc["action"];
      if (action == "open") {
        openGate();
      }
    }
  } else if (String(topic) == "gate/close") {
    closeGate();
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Attempt to connect
    if (client.connect(mqtt_client_id, mqtt_user, mqtt_password)) {
      Serial.println("connected");
      // Subscribe to topics
      client.subscribe("gate/open");
      client.subscribe("gate/close");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void openGate() {
  if (!isGateOpen) {
    Serial.println("Opening Gate...");
    gateServo.write(gateOpenAngle);
    isGateOpen = true;
    gateOpenedAt = millis();
    publishStatus("OPEN");
  }
}

void closeGate() {
  if (isGateOpen) {
    Serial.println("Closing Gate...");
    gateServo.write(gateClosedAngle);
    isGateOpen = false;
    publishStatus("CLOSED");
  }
}

void publishStatus(String status) {
  String topic = "gate/status";
  String payload = "{\"status\":\"" + status + "\"}";
  client.publish(topic.c_str(), payload.c_str());
}

void publishHeartbeat() {
  String topic = "device/heartbeat";
  String payload = "{\"device\":\"esp32\",\"status\":\"online\"}";
  client.publish(topic.c_str(), payload.c_str());
}

void setup() {
  Serial.begin(115200);
  
  // Setup WiFi
  setup_wifi();
  
  // Setup MQTT
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  
  // Setup RFID
  SPI.begin();
  mfrc522.PCD_Init();
  
  // Setup Servo
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
  gateServo.setPeriodHertz(50);
  gateServo.attach(SERVO_PIN, 500, 2400);
  
  // Make sure gate is closed initially
  gateServo.write(gateClosedAngle);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long currentMillis = millis();

  // Auto-close gate
  if (isGateOpen && (currentMillis - gateOpenedAt >= gateOpenDuration)) {
    closeGate();
  }

  // Heartbeat every 30 seconds
  if (currentMillis - lastHeartbeat >= 30000) {
    publishHeartbeat();
    lastHeartbeat = currentMillis;
  }

  // Handle RFID
  if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
    String uidString = "";
    for (byte i = 0; i < mfrc522.uid.size; i++) {
      uidString += String(mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
      uidString += String(mfrc522.uid.uidByte[i], HEX);
    }
    uidString.toUpperCase();
    
    Serial.print("RFID Read: ");
    Serial.println(uidString);
    
    // Publish RFID scan
    DynamicJsonDocument doc(256);
    doc["method"] = "rfid";
    doc["uid"] = uidString;
    String payload;
    serializeJson(doc, payload);
    client.publish("gate/auth/request", payload.c_str());
    
    // We open the gate immediately for known local tags or wait for backend?
    // Since backend handles face recognition, RFID verification can also be done via backend
    // Or locally for offline support. Here we just publish the request.
    
    delay(1000); // Debounce
  }
}
