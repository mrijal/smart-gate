# Camera Setup Guide

This guide explains how to configure the camera used by the Smart AI Gate Access System. 
By default, the system is configured to use the built-in laptop camera for easy testing and development. 

## Current Setup (Laptop Web Camera)

The camera capture logic is handled in `backend/app/services/camera.py`, and the stream is served through the `/api/video_feed` endpoint in `backend/app/main.py`.

In `main.py`, the camera source is passed as `0`, which tells OpenCV to use the first available local camera (usually the laptop's built-in webcam):

```python
@app.get("/api/video_feed")
def video_feed():
    # '0' represents the built-in laptop webcam
    return StreamingResponse(generate_frames(0), media_type="multipart/x-mixed-replace; boundary=frame")
```

## How to Set Up a Different Camera (IP Camera / RTSP / External USB)

When you are ready to deploy the system with a real security camera (e.g., an IP Camera with an RTSP stream) or an external USB camera, you only need to change the argument passed to `generate_frames()` in `backend/app/main.py`.

### 1. External USB Web Camera
If you attach a USB web camera, it will typically be assigned the next available index (e.g., `1`, `2`, etc.).

Change the argument from `0` to `1`:
```python
    return StreamingResponse(generate_frames(1), media_type="multipart/x-mixed-replace; boundary=frame")
```

### 2. IP Camera (RTSP Stream)
Most modern security cameras provide an RTSP (Real Time Streaming Protocol) link. You can pass this link directly as a string instead of an integer index.

**Example:**
If your camera's RTSP URL is `rtsp://username:password@192.168.1.100:554/stream1`, update the endpoint in `main.py` as follows:

```python
@app.get("/api/video_feed")
def video_feed():
    camera_url = "rtsp://username:password@192.168.1.100:554/stream1"
    return StreamingResponse(generate_frames(camera_url), media_type="multipart/x-mixed-replace; boundary=frame")
```

### 3. Making it Configurable (Recommended for Production)
For a cleaner production setup, it is recommended to load the camera source from an environment variable (like `.env`).

**Update your `.env` file:**
```env
CAMERA_SOURCE=rtsp://username:password@192.168.1.100:554/stream1
```

**Update `backend/app/main.py`:**
```python
import os
from fastapi.responses import StreamingResponse
from app.services.camera import generate_frames

@app.get("/api/video_feed")
def video_feed():
    # Fallback to 0 (laptop camera) if the environment variable is not set
    camera_source = os.getenv("CAMERA_SOURCE", 0)
    
    # Ensure it's treated as an integer if it's a digit ('0', '1', etc.)
    if isinstance(camera_source, str) and camera_source.isdigit():
        camera_source = int(camera_source)
        
    return StreamingResponse(generate_frames(camera_source), media_type="multipart/x-mixed-replace; boundary=frame")
```

## Troubleshooting
- **"Failed to read a frame"**: Check if another application (like Zoom or Teams) is using the laptop camera. 
- **RTSP Camera won't connect**: Verify the network connection to the camera, ensure the RTSP username and password are correct, and test the stream URL in a media player like VLC to confirm it is active.
