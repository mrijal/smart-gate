from fastapi import FastAPI, Depends, BackgroundTasks, File, UploadFile, Form
import os
import shutil
import json
from app.recognition.face_service import extract_embedding, load_known_faces, add_known_face
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from app.services.camera import generate_frames
from sqlalchemy.orm import Session
from app.database import database
from app.models import models
from app.mqtt.mqtt_client import start_mqtt, publish_gate_command
from app.websocket.ws_manager import manager
from fastapi import WebSocket, WebSocketDisconnect
import uvicorn

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Smart AI Gate Access System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    start_mqtt()
    # Load known faces from DB into memory
    db = next(database.get_db())
    load_known_faces(db)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Smart Gate API is running"}

@app.post("/api/gate/open")
def open_gate(source: str = "manual"):
    publish_gate_command("open", source=source)
    return {"status": "success", "message": "Gate open command sent"}

@app.post("/api/gate/close")
def close_gate(source: str = "manual"):
    publish_gate_command("close", source=source)
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
def get_logs(db: Session = Depends(database.get_db), limit: int = 50):
    logs = db.query(models.AccessLog).order_by(models.AccessLog.created_at.desc()).limit(limit).all()
    return logs

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
