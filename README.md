<div align="center">

# 🏢 Smart Gate Access System

**Sistem Kontrol Akses Gerbang Otomatis** berbasis Face Recognition, Gesture Detection, dan RFID

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)](https://mysql.com)
[![Docker](https://img.shields.io/badge/Docker-✓-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![ESP32](https://img.shields.io/badge/ESP32-✓-E7352C?logo=espressif&logoColor=white)](https://espressif.com)
[![CUDA](https://img.shields.io/badge/CUDA-12.x-76B900?logo=nvidia&logoColor=white)](https://nvidia.com)

</div>

---

## 📋 Daftar Isi

- [Arsitektur](#-arsitektur)
- [Fitur](#-fitur)
- [Tech Stack](#-tech-stack)
- [Struktur Project](#-struktur-project)
- [Quick Start](#-quick-start)
- [API Endpoints](#-api-endpoints)
- [Hardware Setup](#-hardware-setup)
- [MQTT Topics](#-mqtt-topics)
- [Environment Variables](#-environment-variables)
- [Performa](#-performa)
- [Troubleshooting](#-troubleshooting)
- [Lisensi](#-lisensi)

---

## 🏗️ Arsitektur

<div align="center">

```
┌─────────────┐       ┌──────────────────────┐       ┌──────────────┐
│  Frontend   │──────▶│      Backend         │◀─────▶│   MySQL DB   │
│  (Next.js)  │       │    (FastAPI)         │       └──────────────┘
└─────────────┘       │                      │
       ▲              │  ┌────────────────┐  │       ┌──────────────┐
       │   WebSocket  │  │  InsightFace   │  │◀─────▶│    ESP32     │
       └──────────────┤  │  (Recognition) │  │ MQTT  │  (Hardware)  │
                      │  ├────────────────┤  │       │ RFID + Servo │
                      │  │  MediaPipe     │  │       └──────────────┘
                      │  │  (Gesture)     │  │
                      │  └────────────────┘  │
                      └──────────────────────┘
```

</div>

**Alur Kerja:**
1. Kamera menangkap video → dikirim ke backend via OpenCV
2. **InsightFace** mendeteksi & mengenali wajah setiap 2 detik
3. Jika wajah dikenali → **MediaPipe** mendeteksi gestur tangan (high-5)
4. Gestur valid → Backend publish `gate/open` via **MQTT**
5. **ESP32** menerima perintah → Servo membuka gerbang (5 detik)
6. Status dikirim kembali ke backend & dashboard via **WebSocket**

---

## ✨ Fitur

<table>
  <tr>
    <td align="center" width="33%">
      <h3>👤 Face Recognition</h3>
      Kenali wajah terdaftar menggunakan InsightFace<br>
      <sub>GPU (CUDA) / CPU — det_size 320×320</sub>
    </td>
    <td align="center" width="33%">
      <h3>✋ Gesture Detection</h3>
      Buka gerbang dengan gestur tangan (high-5)<br>
      <sub>MediaPipe HandLandmarker — 1 FPS</sub>
    </td>
    <td align="center" width="33%">
      <h3>📇 RFID</h3>
      Akses via kartu RFID MFRC522<br>
      <sub>Terintegrasi dengan ESP32</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <h3>📊 Dashboard Real-time</h3>
      Monitoring via Next.js<br>
      <sub>WebSocket + MJPEG Stream</sub>
    </td>
    <td align="center">
      <h3>📡 MQTT</h3>
      Komunikasi backend ↔ ESP32<br>
      <sub>Cloud broker Shiftr.io</sub>
    </td>
    <td align="center">
      <h3>🐳 Docker Support</h3>
      Deploy dengan GPU acceleration<br>
      <sub>NVIDIA CUDA 12.x + RTX 3050</sub>
    </td>
  </tr>
</table>

---

## 🛠️ Tech Stack

| Komponen | Teknologi | Keterangan |
|----------|-----------|------------|
| **Backend** | Python FastAPI | REST API + WebSocket server |
| **Face Recognition** | InsightFace + ONNX Runtime | GPU CUDA / CPU fallback |
| **Gesture Detection** | MediaPipe Hands | CPU (model_complexity=0) |
| **Frontend** | Next.js 16 (TypeScript) | Tailwind CSS, Lucide Icons |
| **Database** | MySQL 8.0 | SQLAlchemy ORM |
| **Hardware** | ESP32 DevKit | RFID MFRC522, Servo SG90 |
| **Komunikasi** | MQTT (Shiftr.io) | + WebSocket real-time |
| **Streaming** | MJPEG via OpenCV | 480×360, 12 FPS |
| **Container** | Docker Compose | NVIDIA GPU passthrough |

---

## 📁 Struktur Project

```
<pre>
smart-gate/
│
├── <b>backend/</b>                 # Python FastAPI backend
│   ├── <b>app/</b>
│   │   ├── main.py              # Entry point FastAPI
│   │   ├── api/                 # REST endpoints
│   │   ├── config/              # Konfigurasi (env vars)
│   │   ├── database/            # SQLAlchemy models & session
│   │   ├── models/              # DB models (User, Log, Device)
│   │   ├── mqtt/                # MQTT client
│   │   ├── recognition/         # Face & gesture recognition
│   │   │   ├── face_service.py  # InsightFace GPU/CPU
│   │   │   └── gesture_service.py # MediaPipe Hands
│   │   ├── services/camera.py   # OpenCV video stream
│   │   ├── websocket/           # Real-time updates
│   │   └── auth/                # Autentikasi
│   ├── dataset/                 # Foto wajah terdaftar (volume mount)
│   ├── requirements.txt
│   └── Dockerfile
│
├── <b>frontend/</b>                # Next.js dashboard
│   ├── src/app/
│   │   ├── page.tsx             # Dashboard utama
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── next.config.ts
│   ├── Dockerfile
│   └── package.json
│
├── <b>esp32/</b>                   # Firmware ESP32
│   └── main.ino                 # WiFi, MQTT, RFID, Servo
│
├── <b>dataset/</b>                 # Dataset wajah (volume mount)
├── <b>docs/</b>
│   └── camera_setup.md
│
├── docker-compose.yml
├── INSTALL.txt
├── RUNNING.txt
└── OPTIMIZATION.txt
</pre>
```

---

## 🚀 Quick Start

### Opsi 1: Docker (Recommended)

Persyaratan: Docker Desktop 4.30+, NVIDIA Driver 525+, WSL2 Ubuntu

```bash
# Build images (first time ~10-15 menit)
docker compose build --no-cache

# Jalankan semua services
docker compose up -d

# Cek status
docker compose ps
docker compose logs -f backend

# Verifikasi GPU
docker compose exec backend nvidia-smi
```

| Service | URL |
|---------|-----|
| **Frontend** | [http://localhost:3000](http://localhost:3000) |
| **Backend API** | [http://localhost:8000](http://localhost:8000) |
| **API Docs (Swagger)** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **MySQL** | `localhost:3306` (user/userpassword) |

```bash
# Stop services
docker compose down

# Stop + hapus volume (reset database)
docker compose down -v
```

### Opsi 2: Manual

<details>
<summary><b>Klik untuk expand</b></summary>

#### Prerequisites
- Python 3.10 – 3.12
- Node.js 18+
- MySQL 8.0
- NVIDIA CUDA 12.x Toolkit (optional, untuk GPU)

#### Backend Setup

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
# source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# Set environment variables (PowerShell)
$env:USE_GPU="true"
$env:CUDA_VISIBLE_DEVICES="0"

# Jalankan backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

#### ESP32 Setup

1. Buka `esp32/main.ino` di Arduino IDE
2. Install libraries: WiFi, PubSubClient, MFRC522, ESP32Servo, ArduinoJson
3. Update WiFi credentials:
   ```cpp
   const char* ssid = "YOUR_WIFI_SSID";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```
4. Upload ke ESP32 DevKit

</details>

---

## 🌐 API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| <kbd>POST</kbd> | `/api/users/register` | Registrasi wajah baru (multipart/form-data) |
| <kbd>GET</kbd> | `/api/users` | Daftar semua user terdaftar |
| <kbd>GET</kbd> | `/api/video_feed` | MJPEG video stream real-time |
| <kbd>GET</kbd> | `/api/logs` | Riwayat log akses |
| <kbd>GET</kbd> | `/api/devices` | Status perangkat terhubung |
| <kbd>POST</kbd> | `/api/gate/open` | Buka gerbang secara manual |
| <kbd>POST</kbd> | `/api/gate/close` | Tutup gerbang secara manual |
| <kbd>WS</kbd> | `ws://host/ws` | WebSocket untuk update real-time |

> Dokumentasi lengkap: [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

---

## 🔌 Hardware Setup

### Wiring ESP32

| Komponen | Pin GPIO |
|----------|----------|
| RFID SDA | GPIO 5 |
| RFID SCK | GPIO 18 |
| RFID MOSI | GPIO 23 |
| RFID MISO | GPIO 19 |
| RFID RST | GPIO 22 |
| Servo Signal | GPIO 18 |

### Komponen yang Dibutuhkan

- ESP32 DevKit (LOQ 15 / Generic)
- RFID Reader MFRC522
- Servo Motor (SG90 atau equivalent)
- Power Supply 5V
- Kamera (webcam USB atau IP camera)

---

## 📡 MQTT Topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `gate/open` | 🖥️ Backend → ESP32 | Perintah buka gerbang |
| `gate/close` | 🖥️ Backend → ESP32 | Perintah tutup gerbang |
| `gate/status` | 🔩 ESP32 → Backend | Status gerbang (`OPEN` / `CLOSED`) |
| `device/heartbeat` | 🔩 ESP32 → Backend | Heartbeat device (30 detik) |
| `gate/auth/request` | 🔩 ESP32 → Backend | Request autentikasi RFID |

> **Broker:** `madrjl-websocket.cloud.shiftr.io:1883` (Shiftr.io cloud)

---

## 🔐 Environment Variables

### Backend (`backend/.env`)

```env
# Database
DATABASE_URL=mysql+pymysql://user:password@localhost/smart_gate

# GPU
USE_GPU=true
CUDA_VISIBLE_DEVICES=0

# MQTT
MQTT_BROKER=your-namespace.cloud.shiftr.io
MQTT_PORT=1883
MQTT_USERNAME=your-key
MQTT_PASSWORD=your-token

# Camera
CAMERA_SOURCE=0
```

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## 📊 Performa

<div align="center">

| Metrik | 🚀 GPU (RTX 3050) | 💻 CPU Only |
|--------|:------------------:|:-----------:|
| **Face Detection** | ~40ms | ~150ms |
| **Gesture Detection** | ~30ms | ~60ms |
| **Total Frame Time** | ~70ms | ~210ms |
| **Effective FPS** | **12–14 FPS** | 5–6 FPS |
| **VRAM Usage** | 2.5–3GB / 4GB | — |

</div>

### Tips Optimasi

- Set `USE_GPU=true` untuk percepatan 3–5×
- `det_size=(320, 320)` di `face_service.py` (vs default 640)
- Resolusi kamera 480×360, JPEG quality 50
- Gesture detection berjalan di 1 FPS hanya saat wajah dikenal

> Lihat [OPTIMIZATION.txt](./OPTIMIZATION.txt) untuk detail lengkap.

---

## ❗ Troubleshooting

| Masalah | Solusi |
|---------|--------|
| **GPU not detected** | Pastikan NVIDIA Driver 525+, CUDA 12.x, `USE_GPU=true` |
| **CUDA out of memory** | Turunkan `det_size` ke `(160, 160)` |
| **Camera not found** | Cek `CAMERA_SOURCE`, test: `python -c "import cv2; cap=cv2.VideoCapture(0); print(cap.read())"` |
| **MediaPipe error** | Download `hand_landmarker.task` dari Google Storage |
| **MQTT connection failed** | Cek broker, port, firewall, kredensial |
| **Database connection error** | Tunggu MySQL healthy (30–60 detik), cek `DATABASE_URL` |
| **Port already in use** | Ganti port di `docker-compose.yml` |

---

## 📄 Lisensi

```
Proprietary — Internal Use
Copyright © 2026 Smart Gate Project
```

---

<div align="center">

**Dibuat dengan** ❤️ **untuk sistem akses gerbang yang cerdas dan aman**

</div>
