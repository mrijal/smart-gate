import cv2
import time
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from app.recognition.face_service import recognize_faces
from app.recognition.gesture_service import detect_open_hand
from app.mqtt.mqtt_client import publish_gate_command

logger = logging.getLogger(__name__)

# Cooldown for gate opening (in seconds)
GATE_OPEN_COOLDOWN = 5.0
last_open_time = 0.0

# Face recognition interval (seconds)
FACE_RECOG_INTERVAL = 2.0

# Gesture recognition interval (seconds) - only run when known user present
GESTURE_INTERVAL = 1.0

# Async recognition executor
recognition_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="face_recog")
pending_recognition = None  # type: Future | None
last_face_recog_time = 0.0
cached_recognized_faces = []

last_gesture_time = 0.0
cached_gesture_result = False


def generate_frames(camera_source=0):
    """
    Generator function to read frames, process face & gesture AI, and stream.
    Face recognition runs asynchronously every 2 seconds (non-blocking).
    Gesture recognition runs every 1s only when a known face is detected.
    """
    global last_open_time, last_face_recog_time, cached_recognized_faces
    global last_gesture_time, cached_gesture_result, pending_recognition

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
        recognized_faces = cached_recognized_faces
        known_user_present = False
        user_name = None

        for face in recognized_faces:
            name = face["name"]
            # Draw bounding box and name on every frame
            bbox = face["bbox"]
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
            cv2.putText(frame, f"{name} ({face['score']:.2f})", (bbox[0], bbox[1] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            if name != "Unknown":
                known_user_present = True
                user_name = name

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