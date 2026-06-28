import cv2
import numpy as np
import logging
import math

logger = logging.getLogger(__name__)

use_mediapipe = False
try:
    import mediapipe as mp
    # Check if the solutions module is actually available
    if hasattr(mp, 'solutions'):
        mp_hands = mp.solutions.hands
        mp_drawing = mp.solutions.drawing_utils
        
        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        use_mediapipe = True
    else:
        raise AttributeError("mediapipe has no attribute 'solutions'")
except Exception as e:
    logger.warning(f"MediaPipe unavailable ({e}). Falling back to OpenCV convexity defects for gesture detection.")


def detect_open_hand(frame):
    """
    Detects if there is an open hand (5 fingers raised) in the frame.
    Returns (is_open_hand: bool, processed_frame_with_drawing)
    """
    if use_mediapipe:
        # --- MediaPipe Implementation ---
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)
        
        is_open_hand = False
        
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                
                fingers_tips = [
                    mp_hands.HandLandmark.THUMB_TIP,
                    mp_hands.HandLandmark.INDEX_FINGER_TIP,
                    mp_hands.HandLandmark.MIDDLE_FINGER_TIP,
                    mp_hands.HandLandmark.RING_FINGER_TIP,
                    mp_hands.HandLandmark.PINKY_TIP
                ]
                fingers_pips = [
                    mp_hands.HandLandmark.THUMB_IP,
                    mp_hands.HandLandmark.INDEX_FINGER_PIP,
                    mp_hands.HandLandmark.MIDDLE_FINGER_PIP,
                    mp_hands.HandLandmark.RING_FINGER_PIP,
                    mp_hands.HandLandmark.PINKY_PIP
                ]
                
                raised_fingers = 0
                
                if hand_landmarks.landmark[fingers_tips[0]].x < hand_landmarks.landmark[fingers_pips[0]].x:
                    raised_fingers += 1
                elif hand_landmarks.landmark[fingers_tips[0]].x > hand_landmarks.landmark[fingers_pips[0]].x:
                     raised_fingers += 1
                
                for i in range(1, 5):
                    if hand_landmarks.landmark[fingers_tips[i]].y < hand_landmarks.landmark[fingers_pips[i]].y:
                        raised_fingers += 1
                        
                if raised_fingers >= 4:
                    is_open_hand = True

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
                            
                            # Cosine rule
                            angle = math.acos((b**2 + c**2 - a**2) / (2 * b * c)) * 57.29
                            
                            # Angle < 90 degrees usually means a space between fingers
                            if angle <= 90:
                                count_defects += 1
                                cv2.circle(roi, far, 4, [0, 0, 255], -1) # Draw the gap
                                
                        # 4 gaps = 5 fingers
                        if count_defects >= 4:
                            is_open_hand = True
        except Exception as e:
            # Catch cv2 errors if ROI is out of bounds or convexHull fails
            pass
            
        return is_open_hand, frame
