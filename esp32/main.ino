
#include <WiFi.h>
#include <PubSubClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include <NocShield.h>

// ============================================================
// NocShield Instance
// ============================================================
NocShield nocShield;

// AES-256 Key & IV untuk enkripsi payload MQTT
// NOTE: Di production, simpan di NVS partition, jangan hardcode
static const uint8_t aesKey[32] = "SmartGateAES256Key!!Nocturnail";
static const uint8_t aesIV[16]  = "NocShieldIV16!!";

// ============================================================
// SHA-256 Hashed UID Whitelist (NocShield)
// Hash dari UID asli menggunakan nocShield.hashSHA256()
// ============================================================
const String authorizedUIDHashes[] = {
  "73579bf6ba9332f51a161448fc0ebad9edd2261d9cc1e897ac11a0e32ad99bdc"  // hash("62C92803")
};
const int numAuthorizedUIDHashes = sizeof(authorizedUIDHashes) / sizeof(authorizedUIDHashes[0]);

// ============================================================
// Deauth Detection State (NocShield)
// ============================================================
static volatile int deauthFrameCount = 0;
static volatile unsigned long deauthWindowStart = 0;
static const int DEAUTH_THRESHOLD = 10;
static const unsigned long DEAUTH_WINDOW_MS = 5000;

// ============================================================
// Config: WiFi
// ============================================================
const char* ssid = "anif";
const char* password = "12345688";

// ============================================================
// Config: MQTT (Shiftr.io)
// ============================================================
const char* mqtt_server = "madrjl-websocket.cloud.shiftr.io";
const int mqtt_port = 1883;
const char* mqtt_user = "madrjl-websocket";
const char* mqtt_password = "R5vzRevrusL8y35I";
const char* mqtt_client_id = "ESP32_Gate_Controller";

// ============================================================
// Config: Hardware Pins
// ============================================================
#define SS_PIN 5
#define RST_PIN 22
#define SERVO_PIN 27

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
const unsigned long gateOpenDuration = 5000;
unsigned long lastHeartbeat = 0;

// ============================================================
// FreeRTOS Primitives
// ============================================================
SemaphoreHandle_t xSpiMutex;
SemaphoreHandle_t xGateMutex;
QueueHandle_t xGateCommandQueue;
QueueHandle_t xMqttPublishQueue;

typedef enum {
  GATE_CMD_OPEN,
  GATE_CMD_CLOSE
} GateCommand;

typedef struct {
  char topic[64];
  char payload[256];
} MqttMessage;

// ============================================================
// Helper: enqueue MQTT publish
// ============================================================
void enqueueMqttPublish(const char* topic, const char* payload) {
  MqttMessage msg;
  strlcpy(msg.topic, topic, sizeof(msg.topic));
  strlcpy(msg.payload, payload, sizeof(msg.payload));
  xQueueSend(xMqttPublishQueue, &msg, pdMS_TO_TICKS(100));
}

// ============================================================
// Helper: enqueue MQTT dengan payload AES terenkripsi (NocShield)
// ============================================================
void enqueueMqttPublishEncrypted(const char* topic, const char* plaintext) {
  String encrypted = nocShield.encryptAES(plaintext, aesKey, aesIV);
  MqttMessage msg;
  strlcpy(msg.topic, topic, sizeof(msg.topic));
  strlcpy(msg.payload, encrypted.c_str(), sizeof(msg.payload));
  xQueueSend(xMqttPublishQueue, &msg, pdMS_TO_TICKS(100));
}

// ============================================================
// Helper: cek hash UID di whitelist (NocShield SHA-256)
// ============================================================
bool isAuthorizedHash(const String& uidHash) {
  for (int i = 0; i < numAuthorizedUIDHashes; i++) {
    if (authorizedUIDHashes[i] == uidHash) return true;
  }
  return false;
}

// ============================================================
// publishStatus & publishHeartbeat
// ============================================================
void publishStatus(String status) {
  String payload = "{\"status\":\"" + status + "\"}";
  enqueueMqttPublish("gate/status", payload.c_str());
}

void publishHeartbeat() {
  enqueueMqttPublish("device/heartbeat", "{\"device\":\"esp32\",\"status\":\"online\"}");
}

// ============================================================
// openGate / closeGate
// ============================================================
void openGate() {
  xSemaphoreTake(xGateMutex, portMAX_DELAY);
  if (!isGateOpen) {
    Serial.println("Opening Gate...");
    gateServo.write(gateOpenAngle);
    isGateOpen = true;
    gateOpenedAt = millis();
    xSemaphoreGive(xGateMutex);
    publishStatus("OPEN");
  } else {
    gateOpenedAt = millis();
    xSemaphoreGive(xGateMutex);
    Serial.println("Gate already open, timer reset.");
    publishStatus("OPEN");
  }
}

void closeGate() {
  xSemaphoreTake(xGateMutex, portMAX_DELAY);
  if (isGateOpen) {
    Serial.println("Closing Gate...");
    gateServo.write(gateClosedAngle);
    isGateOpen = false;
    xSemaphoreGive(xGateMutex);
    publishStatus("CLOSED");
  } else {
    xSemaphoreGive(xGateMutex);
  }
}

// ============================================================
// MQTT Callback
// ============================================================
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
        GateCommand cmd = GATE_CMD_OPEN;
        xQueueSendFromISR(xGateCommandQueue, &cmd, NULL);
      }
    }
  } else if (String(topic) == "gate/close") {
    GateCommand cmd = GATE_CMD_CLOSE;
    xQueueSendFromISR(xGateCommandQueue, &cmd, NULL);
  }
}

// ============================================================
// WiFi Setup
// ============================================================
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

// ============================================================
// Promiscuous Callback untuk Deauth Detection (NocShield)
// ============================================================
void deauthPacketCallback(void* buf, wifi_promiscuous_pkt_type_t type) {
  if (type != WIFI_PKT_MGMT) return;

  wifi_promiscuous_pkt_t *pkt = (wifi_promiscuous_pkt_t*)buf;
  if (pkt->payload == NULL || pkt->len < 1) return;

  // Frame Control byte: 0xC0 = Deauthentication
  // Bit 4-7: subtype (0xC = deauth), Bit 2-3: type (0 = mgmt)
  if ((pkt->payload[0] & 0xFC) == 0xC0) {
    deauthFrameCount++;
  }
}

// ============================================================
// TASK 1: MQTT — Core 0
// ============================================================
void taskMQTT(void* pvParameters) {
  unsigned long lastReconnectAttempt = 0;
  const unsigned long reconnectInterval = 5000;

  for (;;) {
    if (!client.connected()) {
      unsigned long now = millis();
      if (now - lastReconnectAttempt >= reconnectInterval) {
        lastReconnectAttempt = now;
        Serial.print("Attempting MQTT connection...");
        if (client.connect(mqtt_client_id, mqtt_user, mqtt_password)) {
          Serial.println("connected");
          client.subscribe("gate/open");
          client.subscribe("gate/close");
          enqueueMqttPublish("device/heartbeat", "{\"device\":\"esp32\",\"status\":\"online\"}");
        } else {
          Serial.print("failed, rc=");
          Serial.print(client.state());
          Serial.println(" - akan coba lagi nanti, RFID tetap aktif");
        }
      }
    } else {
      client.loop();

      unsigned long now = millis();
      if (now - lastHeartbeat >= 30000) {
        publishHeartbeat();
        lastHeartbeat = now;
      }

      MqttMessage msg;
      while (xQueueReceive(xMqttPublishQueue, &msg, 0) == pdTRUE) {
        client.publish(msg.topic, msg.payload);
        Serial.print("Published [");
        Serial.print(msg.topic);
        Serial.print("]: ");
        Serial.println(msg.payload);
      }
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

// ============================================================
// TASK 2: RFID — Core 1
// SHA-256 hash UID + AES encrypted MQTT publish
// ============================================================
void taskRFID(void* pvParameters) {
  for (;;) {
    if (xSemaphoreTake(xSpiMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
      if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
        String uidString = "";
        for (byte i = 0; i < mfrc522.uid.size; i++) {
          uidString += String(mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
          uidString += String(mfrc522.uid.uidByte[i], HEX);
        }
        uidString.toUpperCase();

        mfrc522.PICC_HaltA();
        mfrc522.PCD_StopCrypto1();
        xSemaphoreGive(xSpiMutex);

        Serial.print("RFID Read: ");
        Serial.println(uidString);

        // --- NocShield: SHA-256 hash UID ---
        String uidHash = nocShield.hashSHA256(uidString);
        Serial.print("SHA-256: ");
        Serial.println(uidHash);

        // Cek whitelist hash
        bool granted = isAuthorizedHash(uidHash);

        // --- Kirim encrypted UID via MQTT (NocShield AES) ---
        if (client.connected()) {
          DynamicJsonDocument doc(256);
          doc["method"] = "rfid";
          doc["uid_hash"] = uidHash;          // SHA-256 hash for backend logging
          doc["granted"] = granted;
          String mqttPayload;
          serializeJson(doc, mqttPayload);
          // Kirim payload terenkripsi AES
          enqueueMqttPublishEncrypted("gate/auth/request", mqttPayload.c_str());
        }

        if (granted) {
          Serial.println("Access GRANTED");
          GateCommand cmd = GATE_CMD_OPEN;
          xQueueSend(xGateCommandQueue, &cmd, pdMS_TO_TICKS(100));
        } else {
          Serial.println("Access DENIED");
        }

        vTaskDelay(pdMS_TO_TICKS(1000));
      } else {
        xSemaphoreGive(xSpiMutex);
        vTaskDelay(pdMS_TO_TICKS(50));
      }
    } else {
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
}

// ============================================================
// TASK 3: GATE CONTROL — Core 1
// ============================================================
void taskGateControl(void* pvParameters) {
  for (;;) {
    GateCommand cmd;
    if (xQueueReceive(xGateCommandQueue, &cmd, pdMS_TO_TICKS(10)) == pdTRUE) {
      if (cmd == GATE_CMD_OPEN) {
        openGate();
      } else if (cmd == GATE_CMD_CLOSE) {
        closeGate();
      }
    }

    xSemaphoreTake(xGateMutex, portMAX_DELAY);
    bool shouldClose = isGateOpen && ((millis() - gateOpenedAt) >= gateOpenDuration);
    xSemaphoreGive(xGateMutex);

    if (shouldClose) {
      closeGate();
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

// ============================================================
// TASK 4: DEAUTH MONITOR — Core 0 (NocShield)
// ============================================================
void taskDeauthMonitor(void* pvParameters) {
  deauthWindowStart = millis();

  for (;;) {
    unsigned long now = millis();

    // Reset window every DEAUTH_WINDOW_MS
    if (now - deauthWindowStart >= DEAUTH_WINDOW_MS) {
      if (deauthFrameCount > DEAUTH_THRESHOLD) {
        Serial.println("=== DEAUTH ATTACK DETECTED! ===");
        Serial.print("Deauth frame count: ");
        Serial.println(deauthFrameCount);

        // Publish alert via MQTT (plaintext — alert harus segera sampai)
        if (client.connected()) {
          DynamicJsonDocument doc(128);
          doc["type"] = "deauth_attack";
          doc["count"] = deauthFrameCount;
          doc["window_ms"] = DEAUTH_WINDOW_MS;
          String payload;
          serializeJson(doc, payload);
          enqueueMqttPublish("gate/alert", payload.c_str());
        }
      }
      deauthFrameCount = 0;
      deauthWindowStart = now;
    }

    vTaskDelay(pdMS_TO_TICKS(100));
  }
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Initializing NocShield...");
  nocShield.begin();
  Serial.println("NocShield ready.");

  setup_wifi();

  // Setup MQTT
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);

  // Setup RFID
  SPI.begin();
  mfrc522.PCD_Init();
  delay(50);

  byte version = mfrc522.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print("MFRC522 Version Register: 0x");
  Serial.println(version, HEX);
  if (version == 0x00 || version == 0xFF) {
    Serial.println("==================================================");
    Serial.println("WARNING: MFRC522 TIDAK TERDETEKSI!");
    Serial.println("Cek wiring: SDA->GPIO5, SCK->GPIO18, MOSI->GPIO23,");
    Serial.println("MISO->GPIO19, RST->GPIO22, VCC->3.3V (BUKAN 5V), GND->GND");
    Serial.println("==================================================");
  } else {
    Serial.println("MFRC522 terdeteksi dengan baik, versi chip valid.");
  }

  // Setup Servo
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
  gateServo.setPeriodHertz(50);
  gateServo.attach(SERVO_PIN, 500, 2400);
  gateServo.write(gateClosedAngle);

  // Buat FreeRTOS primitives
  xSpiMutex         = xSemaphoreCreateMutex();
  xGateMutex        = xSemaphoreCreateMutex();
  xGateCommandQueue = xQueueCreate(10, sizeof(GateCommand));
  xMqttPublishQueue = xQueueCreate(20, sizeof(MqttMessage));

  // Buat tasks
  xTaskCreatePinnedToCore(taskMQTT,          "MQTT Task",         4096, NULL, 1, NULL, 0);
  xTaskCreatePinnedToCore(taskRFID,          "RFID Task",         4096, NULL, 2, NULL, 1);
  xTaskCreatePinnedToCore(taskGateControl,   "Gate Control Task", 2048, NULL, 2, NULL, 1);
  xTaskCreatePinnedToCore(taskDeauthMonitor, "Deauth Monitor",    2048, NULL, 1, NULL, 0);

  // NocShield: Start packet monitor untuk deauth detection
  nocShield.startPacketMonitor(deauthPacketCallback);

  Serial.println("All tasks started. NocShield active.");
  Serial.println("Deauth monitor active.");
}

// ============================================================
// LOOP: kosong — semua dihandle FreeRTOS tasks
// ============================================================
void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}
