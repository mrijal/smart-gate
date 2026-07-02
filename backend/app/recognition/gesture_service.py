import cv2
import numpy as np
import logging
import math
import os

logger = logging.getLogger(__name__)

# MediaPipe imports (conditionally available)
try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, HandLandmarkerResult, RunningMode
    from mediapipe import Image, ImageFormat
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    mp = None
    BaseOptions = None
    HandLandmarker = None
    HandLandmarkerOptions = None
    HandLandmarkerResult = None
    RunningMode = None
    Image = None
    ImageFormat = None

use_mediapipe = False
hand_landmarker = None

if MEDIAPIPE_AVAILABLE:
    try:
        # Use downloaded model file
        model_path = os.path.join(os.path.dirname(__file__), '..', '..', 'hand_landmarker.task')
        model_path = os.path.abspath(model_path)
        
        if os.path.exists(model_path):
            base_options = BaseOptions(model_asset_path=model_path)
            options = HandLandmarkerOptions(
                base_options=base_options,
                running_mode=RunningMode.IMAGE,
                num_hands=2,
                min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.6,
                min_tracking_confidence=0.6
            )
            hand_landmarker = HandLandmarker.create_from_options(options)
            use_mediapipe = True
            logger.info("MediaPipe HandLandmarker initialized successfully (Tasks API).")
        else:
            logger.warning(f"MediaPipe model not found at {model_path}. Falling back to OpenCV.")
            use_mediapipe = False
    except Exception as e:
        logger.warning(f"MediaPipe HandLandmarker unavailable ({e}). Falling back to OpenCV convexity defects for gesture detection.")
        use_mediapipe = False
else:
    logger.warning("MediaPipe not installed. Falling back to OpenCV convexity defects for gesture detection.")
    use_mediapipe = False

# For drawing landmarks (same connections as old solutions)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),  # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),  # Index
    (5, 9), (9, 10), (10, 11), (11, 12),  # Middle
    (9, 13), (13, 14), (14, 15), (15, 16),  # Ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # Pinky
    (0, 17)  # Palm
]


def detect_open_hand(frame):
    """
    Detects if there is an open hand (5 fingers raised) in the frame.
    Returns (is_open_hand: bool, processed_frame_with_drawing)
    """
    if use_mediapipe and hand_landmarker is not None:
        # --- MediaPipe Tasks API Implementation ---
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = Image(image_format=ImageFormat.SRGB, data=rgb_frame)
        results = hand_landmarker.detect(mp_image)
        
        is_open_hand = False
        
        if results.hand_landmarks:
            for hand_landmarks, handedness in zip(results.hand_landmarks, results.handedness):
                # Draw landmarks
                for connection in HAND_CONNECTIONS:
                    start_idx, end_idx = connection
                    if start_idx < len(hand_landmarks) and end_idx < len(hand_landmarks):
                        start = hand_landmarks[start_idx]
                        end = hand_landmarks[end_idx]
                        h, w = frame.shape[:2]
                        cv2.line(frame, 
                                (int(start.x * w), int(start.y * h)),
                                (int(end.x * w), int(end.y * h)),
                                (0, 255, 0), 2)
                
                # Draw landmark points
                h, w = frame.shape[:2]
                for landmark in hand_landmarks:
                    cv2.circle(frame, (int(landmark.x * w), int(landmark.y * h)), 3, (0, 0, 255), -1)
                
                # Finger tip and PIP indices (same as old API)
                # Thumb: tip=4, ip=3; Index: tip=8, pip=6; Middle: tip=12, pip=10; Ring: tip=16, pip=14; Pinky: tip=20, pip=18
                fingers_tips = [4, 8, 12, 16, 20]
                fingers_pips = [3, 6, 10, 14, 18]
                
                raised_fingers = 0
                
                # Thumb: compare tip x with IP joint x
                hand_label = handedness[0].category_name if handedness else "Right"
                # MediaPipe handedness is from camera perspective (mirrored)
                # For right hand (from user perspective), tip.x > ip.x means extended
                if hand_label == "Right":
                    if hand_landmarks[fingers_tips[0]].x > hand_landmarks[fingers_pips[0]].x:
                        raised_fingers += 1
                else:  # Left hand
                    if hand_landmarks[fingers_tips[0]].x < hand_landmarks[fingers_pips[0]].x:
                        raised_fingers += 1
                
                for i in range(1, 5):
                    # Finger is raised if tip is above PIP (smaller y = higher up)
                    if hand_landmarks[fingers_tips[i]].y < hand_landmarks[fingers_pips[i]].y - 0.02:
                        raised_fingers += 1
                        
                if raised_fingers >= 4:
                    is_open_hand = True
                    # Once we find an open hand, we can stop checking other hands
                    break

        return is_open_hand, frame
        
    else:
        # --- OpenCV Fallback Implementation ---
        # Draw a Region of Interest (ROI) box on the right side of the screen
        # User must place their hand in this box to avoid detecting their face
        height, width = frame.shape[:2]
        roi_top, roi_bottom = int(height * 0.1), int(height * 0.7)
        roi_left, roi_right = int(width * 0.65), int(width * 0.95)
        
        # Draw the ROI Box
        cv2.rectangle(frame, (roi_left, roi_top), (roi_right, roi_bottom), (255, 100, 0), 2)
        cv2.putText(frame, "Put Hand Here", (roi_left, roi_top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 100, 0), 2)
        
        roi = frame[roi_top:roi_bottom, roi_left:roi_right]
        is_open_hand = False
        
        try:
            # Segment skin color
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            lower_skin = np.array([0, 20, 70], dtype=np.uint8)
            upper_skin = np.array([20, 255, 255], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower_skin, upper_skin)
            mask = cv2.GaussianBlur(mask, (5, 5), 0)
            
            contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            
            if contours:
                max_contour = max(contours, key=cv2.contourArea)
                if cv2.contourArea(max_contour) > 2000: # Minimum area to be considered a hand
                    hull = cv2.convexHull(max_contour, returnPoints=False)
                    defects = cv2.convexityDefects(max_contour, hull)
                    
                    if defects is not None:
                        count_defects = 0
                        for i in range(defects.shape[0]):
                            s, e, f, d = defects[i, 0]
                            start = tuple(max_contour[s][0])
                            end = tuple(max_contour[e][0])
                            far = tuple(max_contour[f][0])
                            
                            # Calculate triangle lengths
                            a = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
                            b = math.sqrt((far[0] - start[0])**2 + (far[1] - start[1])**2)
                            c = math.sqrt((end[0] - far[0])**2 + (end[1] - far[1])**2)
                            
                            # Cosine rule with safety clamps
                            denominator = 2 * b * c
                            if denominator > 0:
                                cos_val = (b**2 + c**2 - a**2) / denominator
                                # Clamp to prevent floating point Domain Errors
                                cos_val = max(min(cos_val, 1.0), -1.0)
                                angle = math.acos(cos_val) * 57.29
                                
                                # Angle < 90 degrees usually means a space between fingers
                                if angle <= 90:
                                    count_defects += 1
                                    cv2.circle(roi, far, 4, [0, 0, 255], -1) # Draw the gap
                                
                        # 4 gaps = 5 fingers (3 gaps is also fine for robustness)
                        if count_defects >= 3:
                            is_open_hand = True
        except Exception as e:
            # logger.error(f"Gesture error: {e}")
            pass
            
        return is_open_hand, frame