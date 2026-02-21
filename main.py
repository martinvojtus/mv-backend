from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, desc
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime
import os
import uuid
from supabase import create_client, Client

# =============================
# ENV CONFIG
# =============================

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

if not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_PASSWORD not set")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# =============================
# DATABASE MODEL
# =============================

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    text = Column(Text)
    image_url = Column(String, nullable=True)

    at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=True, index=True)

    show_date = Column(Boolean, default=True, index=True)

Base.metadata.create_all(bind=engine)

# =============================
# SCHEMAS
# =============================

class PostBase(BaseModel):
    title: str
    text: str
    image_url: Optional[str] = None
    show_date: bool = True

class PostCreate(PostBase):
    pass

class PostUpdate(PostBase):
    pass

class PostResponse(PostBase):
    id: int
    at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

# =============================
# SECURITY
# =============================

def verify_password(x_admin_password: str = Header(None)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

# =============================
# APP
# =============================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # môžeš zmeniť na konkrétnu doménu
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =============================
# ENDPOINTS
# =============================

@app.get("/posts", response_model=List[PostResponse])
def get_posts(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return (
        db.query(Post)
        .order_by(desc(Post.at))
        .offset(skip)
        .limit(limit)
        .all()
    )

@app.post("/posts", response_model=PostResponse)
def create_post(post: PostCreate, db: Session = Depends(get_db), pwd: None = Depends(verify_password)):
    db_post = Post(**post.dict(), at=datetime.utcnow())
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

@app.put("/posts/{post_id}", response_model=PostResponse)
def update_post(post_id: int, post: PostUpdate, db: Session = Depends(get_db), pwd: None = Depends(verify_password)):
    db_post = db.query(Post).filter(Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404)

    if db_post.image_url and db_post.image_url != post.image_url and supabase:
        old_file = db_post.image_url.split("/")[-1]
        try:
            supabase.storage.from_("post-images").remove([old_file])
        except:
            pass

    db_post.title = post.title
    db_post.text = post.text
    db_post.image_url = post.image_url
    db_post.show_date = post.show_date
    db_post.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(db_post)
    return db_post

@app.delete("/posts/{post_id}")
def delete_post(post_id: int, db: Session = Depends(get_db), pwd: None = Depends(verify_password)):
    db_post = db.query(Post).filter(Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404)

    if db_post.image_url and supabase:
        file_name = db_post.image_url.split("/")[-1]
        try:
            supabase.storage.from_("post-images").remove([file_name])
        except:
            pass

    db.delete(db_post)
    db.commit()
    return {"message": "Deleted"}

@app.delete("/posts")
def delete_all(db: Session = Depends(get_db), pwd: None = Depends(verify_password)):
    db.query(Post).delete()
    db.commit()
    return {"message": "All posts deleted"}

@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...), pwd: None = Depends(verify_password)):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    content = await file.read()

    supabase.storage.from_("post-images").upload(
        filename,
        content,
        {"content-type": file.content_type}
    )

    url = supabase.storage.from_("post-images").get_public_url(filename)
    return {"image_url": url}