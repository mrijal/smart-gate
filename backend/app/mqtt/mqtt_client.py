import paho.mqtt.client as mqtt
import json
import os
import threading
from app.database.database import SessionLocal
from app.models.models import Device, AccessLog, User
from app.websocket.ws_manager import manager

MQTT_BROKER = os.getenv("MQTT_BROKER", "madrjl-websocket.cloud.shiftr.io")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER", "madrjl-websocket")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "R5vzRevrusL8y35I")
MQTT_CLIENT_ID = "backend_service"

client = mqtt.Client(client_id=MQTT_CLIENT_ID)

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with result code {rc}")
    client.subscribe("gate/status")
    client.subscribe("device/heartbeat")
    client.subscribe("gate/auth/request")
    client.subscribe("gate/logs")

def on_message(client, userdata, msg):
    print(f"MQTT Message Received: {msg.topic} {str(msg.payload)}")
    try:
        payload = json.loads(msg.payload.decode())
        db = SessionLocal()
        
        if msg.topic == "device/heartbeat":
            device_name = payload.get("device")
            status = payload.get("status")
            
            device = db.query(Device).filter(Device.device_name == device_name).first()
            if not device:
                device = Device(device_name=device_name, status=status)
                db.add(device)
            else:
                device.status = status
            db.commit()

        elif msg.topic == "gate/status":
            # Broadcast gate status to all connected websocket clients
            status = payload.get("status")
            import asyncio
            asyncio.run_coroutine_threadsafe(
                manager.broadcast_log({"type": "gate_status", "status": status}),
                asyncio.get_event_loop()
            )
            
        elif msg.topic == "gate/auth/request":
            # Handle RFID auth request
            uid = payload.get("uid")
            method = payload.get("method")
            if method == "rfid":
                print(f"RFID Auth request for UID: {uid}")
                # Implementation for verifying RFID would go here
                
        db.close()
    except Exception as e:
        print(f"Error processing MQTT message: {e}")

client.on_connect = on_connect
client.on_message = on_message

if MQTT_USER and MQTT_PASSWORD:
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

def start_mqtt():
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"Failed to connect to MQTT: {e}")

def publish_gate_command(action: str, source: str = "manual", user_id: int | None = None, username: str | None = None, confidence: float | None = None):
    payload = {
        "action": action,
        "source": source
    }
    if user_id is not None: payload["user_id"] = str(user_id)
    if username is not None: payload["username"] = username
    if confidence is not None: payload["confidence"] = str(confidence)
    
    client.publish("gate/open" if action == "open" else "gate/close", json.dumps(payload))
    
    if action == "open":
        try:
            db = SessionLocal()
            log_method = "Face Recognition / Gesture" if "gesture" in source else "Manual Control"
            
            if not username and "gesture_" in source:
                username = source.split("gesture_")[-1]
                
            user = db.query(User).filter(User.name == username).first() if username else None
            
            new_log = AccessLog(
                user_id=user.id if user else None,
                method=log_method,
                status="Success"
            )
            db.add(new_log)
            db.commit()
            db.close()
        except Exception as e:
            print(f"Failed to save access log: {e}")

