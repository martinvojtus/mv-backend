from fastapi import FastAPI, HTTPException, Depends
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
    updated_at = Column(DateTime(timezone=True), nullable=True) # Nový stĺpec

Base.metadata.create_all(bind=engine)

# --- Pydantic MODELY (Pre komunikáciu) ---
class PostCreate(BaseModel):
    title: String
    text: String

class PostUpdate(BaseModel):
    title: String
    text: String

class PostResponse(BaseModel):
    id: int
    title: str
    text: str
    at: datetime
    updated_at: Optional[datetime] = None # Môže byť prázdne

    class Config:
        orm_mode = True

# --- APP ---
app = FastAPI()

# Funkcia pre pripojenie k DB
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

# 1. Čítanie (GET)
@app.get("/posts", response_model=List[PostResponse])
def get_posts(db: Session = Depends(get_db)):
    return db.query(Post).order_by(desc(Post.at)).all()

# 2. Nový status (POST)
@app.post("/posts")
def create_post(post: PostCreate, db: Session = Depends(get_db)):
    db_post = Post(title=post.title, text=post.text, at=datetime.utcnow())
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

# 3. Zmazanie (DELETE) - NOVÉ
@app.delete("/posts/{post_id}")
def delete_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(post)
    db.commit()
    return {"message": "Deleted"}

# 4. Úprava (PUT) - NOVÉ
@app.put("/posts/{post_id}")
def update_post(post_id: int, post_update: PostUpdate, db: Session = Depends(get_db)):
    db_post = db.query(Post).filter(Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Aktualizujeme údaje
    db_post.title = post_update.title
    db_post.text = post_update.text
    # Nastavíme čas úpravy
    db_post.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_post)
    return db_post
