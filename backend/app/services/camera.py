import cv2
import time
import logging
from app.recognition.face_service import recognize_faces
from app.recognition.gesture_service import detect_open_hand
from app.mqtt.mqtt_client import publish_gate_command

logger = logging.getLogger(__name__)

# Cooldown for gate opening (in seconds)
GATE_OPEN_COOLDOWN = 5.0
last_open_time = 0.0

def generate_frames(camera_source=0):
    """
    Generator function to read frames, process face & gesture AI, and stream.
    """
    global last_open_time
    cap = cv2.VideoCapture(camera_source)
    
    # --- Optimizations to Reduce Lag ---
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)   # Lower resolution width
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)  # Lower resolution height
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)      # Don't queue old frames
    
    # Allow camera to warm up
    time.sleep(2.0)
    
    while True:
        success, frame = cap.read()
        if not success:
            break
            
        # 1. Face Recognition
        recognized_faces = recognize_faces(frame)
        known_user_present = False
        user_name = None
        
        for face in recognized_faces:
            name = face["name"]
            
            if name != "Unknown":
                known_user_present = True
                user_name = name

        # 2. Gesture Recognition (Only check if a known user is in frame to save processing)
        if known_user_present:
            is_open_hand, frame = detect_open_hand(frame)
            
            if is_open_hand:
                cv2.putText(frame, "GESTURE 5 DETECTED", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3)
                
                # Check cooldown to avoid spamming MQTT
                current_time = time.time()
                if current_time - last_open_time > GATE_OPEN_COOLDOWN:
                    logger.info(f"Gesture triggered by {user_name}. Opening gate!")
                    publish_gate_command("open", source=f"gesture_{user_name}")
                    last_open_time = current_time
                    
        # --- Optimizations to Reduce Lag ---
        # 1. Lower JPEG quality to 60 (default is 95) for faster network streaming
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 60]
        ret, buffer = cv2.imencode('.jpg', frame, encode_param)
        
        if not ret:
            continue
            
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # 2. Limit framerate to ~20 FPS max to give CPU time to breathe
        time.sleep(0.05)
               
    cap.release()
