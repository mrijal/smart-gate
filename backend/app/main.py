from fastapi import FastAPI, Depends, BackgroundTasks, File, UploadFile, Form, Query
import os
import shutil
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, List
from app.recognition.face_service import extract_embedding, load_known_faces, add_known_face, recognize_faces
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from app.services.camera import generate_frames, set_face_recognition_enabled, get_face_recognition_enabled, set_gate_state, get_gate_state
from sqlalchemy.orm import Session
from app.database import database
from app.models import models
from app.mqtt.mqtt_client import start_mqtt, publish_gate_command
from app.websocket.ws_manager import manager
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn
from sqlalchemy import func, desc, or_
import cv2
import numpy as np

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Smart AI Gate Access System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("dataset", exist_ok=True)
app.mount("/dataset", StaticFiles(directory="dataset"), name="dataset")
os.makedirs("unknown_faces", exist_ok=True)
app.mount("/unknown_faces", StaticFiles(directory="unknown_faces"), name="unknown_faces")

@app.on_event("startup")
def startup_event():
    start_mqtt()
    # Load known faces from DB into memory
    db = database.SessionLocal()
    try:
        load_known_faces(db)
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Smart Gate API is running"}

@app.get("/api/gate/status")
def get_gate_status():
    return {"status": get_gate_state()}

@app.post("/api/gate/open")
def open_gate(source: str = "manual"):
    publish_gate_command("open", source=source)
    set_gate_state("OPEN")
    return {"status": "success", "message": "Gate open command sent"}

@app.post("/api/gate/close")
def close_gate(source: str = "manual"):
    publish_gate_command("close", source=source)
    set_gate_state("CLOSED")
    return {"status": "success", "message": "Gate close command sent"}

@app.get("/api/video_feed")
def video_feed():
    """
    Video streaming route. Put this in the src attribute of an img tag.
    By default, it uses camera_source=0 (the built-in laptop camera).
    """
    return StreamingResponse(generate_frames(0), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/users")
def get_users(db: Session = Depends(database.get_db)):
    users = db.query(models.User).all()
    return users

@app.post("/api/users/register")
def register_user(
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form("user"),
    photo: UploadFile = File(...),
    db: Session = Depends(database.get_db)
):
    dataset_dir = "dataset"
    os.makedirs(dataset_dir, exist_ok=True)
    
    file_path = os.path.join(dataset_dir, photo.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(photo.file, buffer)
        
    try:
        embedding = extract_embedding(file_path)
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
    embedding_json = json.dumps(embedding)
    
    new_user = models.User(
        name=name,
        email=email,
        role=role,
        photo=file_path,
        embedding=embedding_json
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Add to memory cache immediately so it works in the live stream without restart
    add_known_face(new_user.name, embedding)
    
    return {"status": "success", "message": "User registered successfully", "user_id": new_user.id}

@app.get("/api/logs")
def get_logs(
    db: Session = Depends(database.get_db),
    limit: int = 50,
    offset: int = 0,
    name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None)
):
    q = db.query(models.AccessLog, models.User).outerjoin(
        models.User, models.AccessLog.user_id == models.User.id
    )

    if name:
        q = q.filter(models.User.name.ilike(f"%{name}%"))
    if status:
        q = q.filter(models.AccessLog.status == status)
    if method:
        q = q.filter(models.AccessLog.method == method)

    total = q.count()

    logs = q.order_by(models.AccessLog.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for log, user in logs:
        photo_url = "/" + user.photo.replace("\\", "/") if user and user.photo else None
        result.append({
            "id": log.id,
            "user_id": log.user_id,
            "method": log.method,
            "status": log.status,
            "confidence": log.confidence,
            "image_path": log.image_path,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "name": user.name if user else "Unknown User",
            "photo": photo_url
        })
    return {"data": result, "total": total}

# --- Unknown face detection tracking (in-memory) ---
unknown_face_tracker = {
    "timestamps": [],  # list of detection times
    "last_alert": 0    # last alert timestamp
}

def track_unknown_face():
    now = time.time()
    unknown_face_tracker["timestamps"].append(now)
    cutoff = now - 30
    unknown_face_tracker["timestamps"] = [t for t in unknown_face_tracker["timestamps"] if t > cutoff]
    if len(unknown_face_tracker["timestamps"]) >= 5:
        if now - unknown_face_tracker["last_alert"] > 30:
            unknown_face_tracker["last_alert"] = now
            return True
    return False

@app.post("/api/unknown-face-detected")
def report_unknown_face(image_path: Optional[str] = None, db: Session = Depends(database.get_db)):
    alert = track_unknown_face()
    new_visitor = models.UnknownVisitor(
        confidence=0.0,
        image_path=image_path
    )
    db.add(new_visitor)
    if alert:
        threat_log = models.AccessLog(
            user_id=None,
            method="face",
            status="threat",
            confidence=0.0,
            image_path=image_path
        )
        db.add(threat_log)
    db.commit()
    return {"alert": alert, "message": "Unknown face logged"}

@app.get("/api/threat-logs")
def get_threat_logs(db: Session = Depends(database.get_db), limit: int = 50):
    logs = db.query(models.AccessLog).filter(
        models.AccessLog.status == "threat"
    ).order_by(models.AccessLog.created_at.desc()).limit(limit).all()
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "method": log.method,
            "status": log.status,
            "confidence": log.confidence,
            "image_path": log.image_path,
            "created_at": log.created_at.isoformat() if log.created_at else None
        })
    return result

@app.get("/api/unknown-visitors")
def get_unknown_visitors(db: Session = Depends(database.get_db), limit: int = 50):
    visitors = db.query(models.UnknownVisitor).order_by(
        models.UnknownVisitor.created_at.desc()
    ).limit(limit).all()
    result = []
    for v in visitors:
        result.append({
            "id": v.id,
            "image_path": v.image_path,
            "confidence": v.confidence,
            "created_at": v.created_at.isoformat() if v.created_at else None
        })
    return result

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return {"status": "error", "message": "User not found"}
    if user.photo and os.path.exists(user.photo):
        os.remove(user.photo)
    db.delete(user)
    db.commit()
    from app.recognition.face_service import load_known_faces
    load_known_faces(db)
    return {"status": "success", "message": "User deleted"}

@app.put("/api/users/{user_id}")
def update_user(
    user_id: int,
    name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(database.get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return {"status": "error", "message": "User not found"}
    if name:
        user.name = name
    if email:
        user.email = email
    if role:
        user.role = role
    if photo:
        dataset_dir = "dataset"
        os.makedirs(dataset_dir, exist_ok=True)
        file_path = os.path.join(dataset_dir, photo.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        if user.photo and os.path.exists(user.photo):
            os.remove(user.photo)
        user.photo = file_path
        try:
            embedding = extract_embedding(file_path)
            user.embedding = json.dumps(embedding)
        except Exception as e:
            return {"status": "error", "message": str(e)}
    db.commit()
    db.refresh(user)
    from app.recognition.face_service import load_known_faces
    load_known_faces(db)
    return {"status": "success", "message": "User updated"}

@app.get("/api/settings/face-recognition")
def get_face_recognition_setting():
    return {"enabled": get_face_recognition_enabled()}

@app.post("/api/settings/face-recognition")
def set_face_recognition_setting(enabled: bool = True):
    set_face_recognition_enabled(enabled)
    return {"enabled": get_face_recognition_enabled()}

@app.get("/api/devices")
def get_devices(db: Session = Depends(database.get_db)):
    devices = db.query(models.Device).all()
    return devices

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming ws messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
