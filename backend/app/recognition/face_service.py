import cv2
import numpy as np
import logging
import json
from sqlalchemy.orm import Session
from app.models.models import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Fallback AI flag
use_mock_ai = False

try:
    import insightface
    # Initialize the InsightFace model
    model = insightface.app.FaceAnalysis()
    # ctx_id=0 for GPU, -1 for CPU
    model.prepare(ctx_id=-1, det_size=(640, 640))
    logger.info("InsightFace model loaded successfully.")
except Exception as e:
    logger.warning(f"Failed to load InsightFace ({e}). Falling back to Mock AI.")
    use_mock_ai = True

# In-memory cache for fast real-time recognition
known_embeddings = []
known_names = []

def load_known_faces(db: Session):
    global known_embeddings, known_names
    known_embeddings = []
    known_names = []
    
    users = db.query(User).filter(User.embedding != None).all()
    for u in users:
        try:
            emb_list = json.loads(u.embedding)
            known_embeddings.append(np.array(emb_list))
            known_names.append(u.name)
        except Exception as e:
            logger.error(f"Failed to load embedding for user {u.id}: {e}")
            
    logger.info(f"Loaded {len(known_names)} known faces into memory.")

def add_known_face(name: str, embedding: list):
    global known_embeddings, known_names
    known_embeddings.append(np.array(embedding))
    known_names.append(name)
    logger.info(f"Added {name} to known faces in memory.")

def compute_similarity(emb1, emb2):
    # Cosine similarity
    return np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

def recognize_faces(frame: np.ndarray):
    """
    Process a single frame to detect and recognize faces.
    Returns a list of dicts: [{"bbox": [x1,y1,x2,y2], "name": str, "score": float}]
    """
    if use_mock_ai:
        # Mock recognition doesn't actually detect faces well, just return empty
        # or a fake bounding box if you want to test drawing without a camera
        return []
        
    faces = model.get(frame)
    results = []
    
    for face in faces:
        bbox = face.bbox.astype(int).tolist() # [x1, y1, x2, y2]
        emb = face.embedding
        
        best_match_name = "Unknown"
        best_score = 0.0
        
        for i, known_emb in enumerate(known_embeddings):
            score = compute_similarity(emb, known_emb)
            if score > best_score:
                best_score = score
                best_match_name = known_names[i]
                
        # Threshold for insightface cosine similarity is typically around 0.45
        if best_score < 0.45:
            best_match_name = "Unknown"
            
        results.append({
            "bbox": bbox,
            "name": best_match_name,
            "score": best_score
        })
        
    return results

def extract_embedding(image_path: str):
    """
    Extract face embedding using InsightFace, or return a mock embedding if unavailable.
    Returns the embedding as a list of floats.
    """
    if use_mock_ai:
        logger.info(f"Using Mock AI embedding for {image_path}")
        return np.random.rand(512).tolist()
        
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image at {image_path}")
        
    faces = model.get(img)
    if not faces:
        raise ValueError("No face detected in the image.")
        
    face = faces[0]
    embedding = face.embedding.tolist()
    return embedding

def register_face(image_path: str, user_id: int):
    pass

def handle_unknown_face(frame: np.ndarray, bbox):
    pass
