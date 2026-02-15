from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import os

# --- KONFIGURÁCIA ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Nacitame heslo z Renderu (ak tam nie je, pouzije sa predvolene)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "TvojeTajneHeslo")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODEL DATABÁZY ---
class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    text = Column(Text)
    at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True)

Base.metadata.create_all(bind=engine)

# --- Pydantic MODELY ---
class PostCreate(BaseModel):
    title: str
    text: str

class PostUpdate(BaseModel):
    title: str
    text: str

class PostResponse(BaseModel):
    id: int
    title: str
    text: str
    at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

# --- BEZPEČNOSTNÁ BRÁNA (NOVÉ) ---
def verify_password(x_admin_password: str = Header(None)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized: Nesprávne heslo")

# --- APP ---
app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTY ---

# 1. Čítanie (GET) - VEREJNÉ (Bez hesla, aby web fungoval pre vsetkych)
@app.get("/posts", response_model=List[PostResponse])
def get_posts(db: Session = Depends(get_db)):
    return db.query(Post).order_by(desc(Post.at)).all()

# 2. Nový status (POST) - CHRÁNENÉ HESLOM
@app.post("/posts")
def create_post(post: PostCreate, db: Session = Depends(get_db), pwd: None = Depends(verify_password)):
    db_post = Post(title=post.title, text=post.text, at=datetime.utcnow())
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

# 3. Zmazanie (DELETE) - CHRÁNENÉ HESLOM
@app.delete("/posts/{post_id}")
def delete_post(post_id: int, db: Session = Depends(get_db), pwd: None = Depends(verify_password)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(post)
    db.commit()
    return {"message": "Deleted"}

# 4. Úprava (PUT) - CHRÁNENÉ HESLOM
@app.put("/posts/{post_id}")
def update_post(post_id: int, post_update: PostUpdate, db: Session = Depends(get_db), pwd: None = Depends(verify_password)):
    db_post = db.query(Post).filter(Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    db_post.title = post_update.title
    db_post.text = post_update.text
    db_post.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_post)
    return db_post
