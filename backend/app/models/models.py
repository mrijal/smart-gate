from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    email = Column(String(255), unique=True, index=True)
    role = Column(String(50), default="user")
    photo = Column(String(255), nullable=True)
    embedding = Column(Text, nullable=True) # JSON string array or binary
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class FaceImage(Base):
    __tablename__ = "face_images"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    image_path = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    method = Column(String(50)) # "face" or "rfid"
    status = Column(String(50)) # "success" or "failed"
    confidence = Column(Float, nullable=True)
    image_path = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UnknownVisitor(Base):
    __tablename__ = "unknown_visitors"

    id = Column(Integer, primary_key=True, index=True)
    image_path = Column(String(255))
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_name = Column(String(100), unique=True)
    status = Column(String(50)) # "online" or "offline"
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
