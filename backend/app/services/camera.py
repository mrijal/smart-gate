import cv2
import os
import time
import uuid
import logging
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
from app.recognition.face_service import recognize_faces
from app.recognition.gesture_service import detect_open_hand
from app.mqtt.mqtt_client import publish_gate_command

logger = logging.getLogger(__name__)

# Cooldown for gate opening (in seconds)
GATE_OPEN_COOLDOWN = 10.0
last_open_time = 0.0

# Face recognition interval (seconds)
FACE_RECOG_INTERVAL = 2.0

# Gesture recognition interval (seconds) - only run when known user present
GESTURE_INTERVAL = 1.0

# Unknown face detection interval (seconds)
UNKNOWN_FACE_INTERVAL = 3.0

# Face recognition toggle (can be turned off via API while keeping gesture tracking)
face_recognition_enabled = True

# Gate state tracking (shared across API and gesture trigger)
gate_state = "CLOSED"

def get_gate_state() -> str:
    return gate_state

def set_gate_state(state: str):
    global gate_state
    gate_state = state

def get_face_recognition_enabled() -> bool:
    return face_recognition_enabled

def set_face_recognition_enabled(enabled: bool):
    global face_recognition_enabled
    face_recognition_enabled = enabled
    logger.info(f"Face recognition {'enabled' if enabled else 'disabled'}")

# Async recognition executor
recognition_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="face_recog")
pending_recognition = None  # type: Future | None
last_face_recog_time = 0.0
cached_recognized_faces = []

last_gesture_time = 0.0
cached_gesture_result = False

last_unknown_report_time = 0.0


def generate_frames(camera_source=0):
    """
    Generator function to read frames, process face & gesture AI, and stream.
    Face recognition runs asynchronously every 2 seconds (non-blocking).
    Gesture recognition runs every 1s only when a known face is detected.
    """
    global last_open_time, last_face_recog_time, cached_recognized_faces
    global last_gesture_time, cached_gesture_result, pending_recognition
    global last_unknown_report_time, face_recognition_enabled, gate_state

    # Try to find a working camera
    cap = None
    for idx in range(3):
        test_cap = cv2.VideoCapture(idx)
        if test_cap.isOpened():
            ret, _ = test_cap.read()
            if ret:
                cap = test_cap
                logger.info(f"Using camera index {idx}")
                break
            test_cap.release()
    
    if cap is None:
        logger.error("No working camera found!")
        # Fallback to index 0
        cap = cv2.VideoCapture(camera_source)

# --- Optimizations to Reduce Lag ---
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Allow camera to warm up
    time.sleep(2.0)

    while True:
        success, frame = cap.read()
        if not success:
            break

        current_time = time.time()

        # 1. Face Recognition - Submit async every 2 seconds (non-blocking)
        if face_recognition_enabled:
            if current_time - last_face_recog_time >= FACE_RECOG_INTERVAL:
                # Check if previous recognition is done, if not skip this round
                if pending_recognition is None or pending_recognition.done():
                    # Submit new recognition task (frame copied to avoid race conditions)
                    pending_recognition = recognition_executor.submit(recognize_faces, frame.copy())
                    last_face_recog_time = current_time
                # If previous not done, skip this interval - will try next frame

            # Check if async recognition completed
            if pending_recognition is not None and pending_recognition.done():
                try:
                    cached_recognized_faces = pending_recognition.result()
                except Exception as e:
                    logger.error(f"Face recognition error: {e}")
                    cached_recognized_faces = []
                pending_recognition = None  # type: ignore

        # Use cached results for drawing (never blocks)
        recognized_faces = cached_recognized_faces if face_recognition_enabled else []
        known_user_present = False if face_recognition_enabled else True
        user_name = None
        has_unknown = False

        if face_recognition_enabled:
            for face in recognized_faces:
                name = face["name"]
                # Draw bounding box and name on every frame
                bbox = face["bbox"]
                color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
                cv2.putText(frame, f"{name} ({face['score']:.2f})", (bbox[0], bbox[1] - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                if name != "Unknown":
                    known_user_present = True
                    user_name = name
                else:
                    has_unknown = True

            # 3. Unknown face threat detection - capture face and report to backend
            if has_unknown and current_time - last_unknown_report_time >= UNKNOWN_FACE_INTERVAL:
                last_unknown_report_time = current_time
                image_path = None
                for face in recognized_faces:
                    if face["name"] == "Unknown":
                        bbox = face["bbox"]
                        x1, y1, x2, y2 = [max(0, int(v)) for v in bbox]
                        h, w = frame.shape[:2]
                        x1, x2 = min(x1, w), min(x2, w)
                        y1, y2 = min(y1, h), min(y2, h)
                        face_crop = frame[y1:y2, x1:x2]
                        if face_crop.size > 0:
                            os.makedirs("unknown_faces", exist_ok=True)
                            filename = f"unknown_faces/unknown_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
                            cv2.imwrite(filename, face_crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            image_path = filename
                        break
                try:
                    params = {}
                    if image_path:
                        params["image_path"] = image_path
                    requests.post("http://localhost:8000/api/unknown-face-detected", params=params, timeout=1)
                except Exception:
                    pass

        # 2. Gesture Recognition (Only check if a known user is in frame, throttled to 1 FPS)
        if known_user_present:
            if current_time - last_gesture_time >= GESTURE_INTERVAL:
                cached_gesture_result, frame = detect_open_hand(frame)
                last_gesture_time = current_time
            # If gesture detected, draw on frame (use cached result for performance)
            if cached_gesture_result:
                cv2.putText(frame, "GESTURE 5 DETECTED", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)

                # Check cooldown to avoid spamming MQTT
                if current_time - last_open_time > GATE_OPEN_COOLDOWN:
                    logger.info(f"Gesture triggered by {user_name}. Opening gate!")
                    publish_gate_command("open", source=f"gesture_{user_name}")
                    gate_state = "OPEN"
                    last_open_time = current_time
        else:
            # Reset gesture cache when no known user present
            cached_gesture_result = False

        # --- Optimizations to Reduce Lag ---
        # 1. Lower JPEG quality to 50 for faster network streaming
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
        ret, buffer = cv2.imencode('.jpg', frame, encode_param)

        if not ret:
            continue

        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        # 2. Limit framerate to ~30 FPS max
        time.sleep(0.033)

    # Cleanup
    recognition_executor.shutdown(wait=False)
    cap.release()