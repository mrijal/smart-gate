
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

// --- Config: WiFi ---
const char* ssid = "anif";
const char* password = "12345688";

// --- Config: MQTT (Shiftr.io) ---
const char* mqtt_server = "madrjl-websocket.cloud.shiftr.io";
const int mqtt_port = 1883;
const char* mqtt_user = "madrjl-websocket";
const char* mqtt_password = "R5vzRevrusL8y35I";
const char* mqtt_client_id = "ESP32_Gate_Controller";

// --- Config: Hardware Pins ---
#define SS_PIN 5
#define RST_PIN 22
#define SERVO_PIN 27

// --- Config: Authorized RFID UIDs (hardcoded whitelist, local) ---
const String authorizedUIDs[] = {
  "62C92803",   // UID kartu 1
};
const int numAuthorizedUIDs = sizeof(authorizedUIDs) / sizeof(authorizedUIDs[0]);

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

// ============================================================
// FreeRTOS Primitives
// ============================================================
SemaphoreHandle_t xSpiMutex;      // Mutex: proteksi akses SPI (RFID)
SemaphoreHandle_t xGateMutex;     // Mutex: proteksi state isGateOpen
QueueHandle_t xGateCommandQueue;  // Queue: perintah buka/tutup gate
QueueHandle_t xMqttPublishQueue;  // Queue: pesan MQTT yang mau dipublish

// Enum gate command
typedef enum {
  GATE_CMD_OPEN,
  GATE_CMD_CLOSE
} GateCommand;

// Struct MQTT message
typedef struct {
  char topic[64];
  char payload[256];
} MqttMessage;

// ============================================================
// Helper: enqueue MQTT publish (aman dipanggil dari task manapun)
// ============================================================
void enqueueMqttPublish(const char* topic, const char* payload) {
  MqttMessage msg;
  strlcpy(msg.topic, topic, sizeof(msg.topic));
  strlcpy(msg.payload, payload, sizeof(msg.payload));
  xQueueSend(xMqttPublishQueue, &msg, pdMS_TO_TICKS(100));
}

// ============================================================
// Helper: cek UID di whitelist
// ============================================================
bool isAuthorized(String uid) {
  for (int i = 0; i < numAuthorizedUIDs; i++) {
    if (authorizedUIDs[i] == uid) return true;
  }
  return false;
}

// ============================================================
// publishStatus & publishHeartbeat: enqueue, bukan publish langsung
// ============================================================
void publishStatus(String status) {
  String payload = "{\"status\":\"" + status + "\"}";
  enqueueMqttPublish("gate/status", payload.c_str());
}

void publishHeartbeat() {
  enqueueMqttPublish("device/heartbeat", "{\"device\":\"esp32\",\"status\":\"online\"}");
}

// ============================================================
// openGate / closeGate: aman dipanggil dari task manapun via queue
// Hanya dieksekusi di taskGateControl
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
    // Gate sudah terbuka (mungkin dibuka via face recog/palm):
    // reset timer supaya tidak langsung menutup, dan RFID tetap bisa re-trigger
    gateOpenedAt = millis();
    xSemaphoreGive(xGateMutex);
    Serial.println("Gate sudah terbuka, timer direset.");
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
// MQTT Callback: dipanggil di task MQTT saat ada pesan masuk
// Tidak langsung panggil openGate/closeGate — kirim ke queue
// supaya tidak race condition dengan RFID task
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
// TASK 1: MQTT — Core 0
// Handles: reconnect non-blocking, client.loop(), publish queue, heartbeat
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
          // Publish online status setiap kali berhasil (re)connect
          enqueueMqttPublish("device/heartbeat", "{\"device\":\"esp32\",\"status\":\"online\"}");
        } else {
          Serial.print("failed, rc=");
          Serial.print(client.state());
          Serial.println(" - akan coba lagi nanti, RFID tetap aktif");
        }
      }
    } else {
      client.loop();

      // Heartbeat setiap 30 detik
      unsigned long now = millis();
      if (now - lastHeartbeat >= 30000) {
        publishHeartbeat();
        lastHeartbeat = now;
      }

      // Proses antrian MQTT publish
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
// Handles: polling kartu, cek whitelist, kirim perintah ke gate queue
// FIX BUG: PICC_HaltA + PCD_StopCrypto1 setelah setiap baca
// supaya scan berikutnya tidak stuck
// ============================================================
void taskRFID(void* pvParameters) {
  for (;;) {
    // Ambil mutex SPI sebelum akses RFID reader
    if (xSemaphoreTake(xSpiMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
      if (mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
        String uidString = "";
        for (byte i = 0; i < mfrc522.uid.size; i++) {
          uidString += String(mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
          uidString += String(mfrc522.uid.uidByte[i], HEX);
        }
        uidString.toUpperCase();

        // *** FIX UTAMA: Halt PICC dan stop crypto ***
        // Tanpa ini, kartu tetap "active" di reader → scan berikutnya SELALU gagal
        // Ini adalah root cause RFID tidak bisa setelah gate dibuka via face recog/palm
        mfrc522.PICC_HaltA();
        mfrc522.PCD_StopCrypto1();

        // Lepas mutex SPI sebelum proses lebih lanjut
        xSemaphoreGive(xSpiMutex);

        Serial.print("RFID Read: ");
        Serial.println(uidString);

        bool granted = isAuthorized(uidString);

        // Publish ke backend untuk logging (kalau MQTT konek)
        if (client.connected()) {
          DynamicJsonDocument doc(256);
          doc["method"] = "rfid";
          doc["uid"] = uidString;
          doc["granted"] = granted;
          String mqttPayload;
          serializeJson(doc, mqttPayload);
          enqueueMqttPublish("gate/auth/request", mqttPayload.c_str());
        } else {
          Serial.println("MQTT belum connected - skip publish, tetap proses whitelist lokal");
        }

        if (granted) {
          Serial.println("Access granted (local whitelist)");
          GateCommand cmd = GATE_CMD_OPEN;
          xQueueSend(xGateCommandQueue, &cmd, pdMS_TO_TICKS(100));
        } else {
          Serial.println("Access denied - UID not in whitelist");
        }

        vTaskDelay(pdMS_TO_TICKS(1000)); // Debounce 1 detik
      } else {
        xSemaphoreGive(xSpiMutex);
        vTaskDelay(pdMS_TO_TICKS(50)); // Poll tiap 50ms kalau tidak ada kartu
      }
    } else {
      vTaskDelay(pdMS_TO_TICKS(10));
    }
  }
}

// ============================================================
// TASK 3: GATE CONTROL — Core 1
// Handles: eksekusi perintah buka/tutup, auto-close timer
// Satu-satunya task yang boleh gerakkan servo
// ============================================================
void taskGateControl(void* pvParameters) {
  for (;;) {
    // Terima perintah dari queue (dari RFID task atau MQTT callback)
    GateCommand cmd;
    if (xQueueReceive(xGateCommandQueue, &cmd, pdMS_TO_TICKS(10)) == pdTRUE) {
      if (cmd == GATE_CMD_OPEN) {
        openGate();
      } else if (cmd == GATE_CMD_CLOSE) {
        closeGate();
      }
    }

    // Cek auto-close dengan mutex
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
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  // Setup WiFi
  setup_wifi();

  // Setup MQTT
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);

  // Setup RFID
  SPI.begin();
  mfrc522.PCD_Init();
  delay(50);

  // Self-test RC522
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

  // Buat tasks dan pin ke core
  xTaskCreatePinnedToCore(taskMQTT,        "MQTT Task",         4096, NULL, 1, NULL, 0); // Core 0, priority 1
  xTaskCreatePinnedToCore(taskRFID,        "RFID Task",         4096, NULL, 2, NULL, 1); // Core 1, priority 2
  xTaskCreatePinnedToCore(taskGateControl, "Gate Control Task", 2048, NULL, 2, NULL, 1); // Core 1, priority 2

  Serial.println("All tasks started. System ready.");
}

// ============================================================
// LOOP: kosong — semua dihandle FreeRTOS tasks
// ============================================================
void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}
