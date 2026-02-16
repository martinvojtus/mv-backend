from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import os
import uuid
from supabase import create_client, Client

# --- KONFIGURÁCIA ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "TvojeTajneHeslo")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Pripojenie k Supabase Storage
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODEL DATABÁZY ---
class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    text = Column(Text)
    image_url = Column(String, nullable=True) # NOVÉ: Stĺpec pre obrázok
    at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True)

Base.metadata.create_all(bind=engine)

# --- Pydantic MODELY ---
class PostCreate(BaseModel):
    title: str
    text: str
    image_url: Optional[str] = None # NOVÉ

class PostUpdate(BaseModel):
    title: str
    text: str
    image_url: Optional[str] = None # NOVÉ

class PostResponse(BaseModel):
    id: int
    title: str
    text: str
    image_url: Optional[str] = None # NOVÉ
    at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

def verify_password(x_admin_password: str = Header(None)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

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
@app.get("/posts", response_model=List[PostResponse])
def get_posts(db: Session = Depends(get_db)):
    return db.query(Post).order_by(desc(Post.at)).all()

@app.post("/posts")
def create_post(post: PostCreate, db: Session = Depends(get_db), pwd: None = Depends(verify_password)):
    db_post = Post(title=post.title, text=post.text, image_url=post.image_url, at=datetime.utcnow())
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

@app.delete("/posts/{post_id}")
def delete_post(post_id: int, x_admin_password: str = Header(None)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # 1. KROK: Najprv zistíme, či má príspevok pripojený obrázok
    post_response = supabase.table("posts").select("image_url").eq("id", post_id).execute()
    
    if post_response.data and len(post_response.data) > 0:
        image_url = post_response.data[0].get("image_url")
        
        # 2. KROK: Ak obrázok existuje, zmažeme ho zo Storage
        if image_url:
            # Z dlhej URL adresy vysekáme len samotný názov súboru na konci
            # napr. "https://.../images/fotka123.jpg" -> "fotka123.jpg"
            file_name = image_url.split("/")[-1]
            
            try:
                # Nezabudni upraviť "images" na presný názov tvojho bucketu v Supabase, ak sa volá inak
                supabase.storage.from_("images").remove([file_name])
            except Exception as e:
                print(f"Warning: Nepodarilo sa zmazať obrázok zo Storage: {e}")

    # 3. KROK: Nakoniec zmažeme samotný príspevok z databázy
    response = supabase.table("posts").delete().eq("id", post_id).execute()
    
    return {"message": "Post and associated image deleted successfully"}


@app.put("/posts/{post_id}")
def update_post(post_id: int, post_update: PostUpdate, db: Session = Depends(get_db), pwd: None = Depends(verify_password)):
    db_post = db.query(Post).filter(Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    db_post.title = post_update.title
    db_post.text = post_update.text
    db_post.image_url = post_update.image_url
    db_post.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_post)
    return db_post

# NOVÉ: Endpoint na upload fotky
@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...), pwd: None = Depends(verify_password)):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase kľúče nie sú nastavené na Renderi.")
    
    try:
        # Vygenerujeme náhodný názov, aby sa fotky nepremazávali
        file_ext = file.filename.split(".")[-1]
        file_name = f"{uuid.uuid4()}.{file_ext}"
        contents = await file.read()
        
        # Odošleme do Supabase skladu
        supabase.storage.from_("post-images").upload(
            file_name, 
            contents, 
            {"content-type": file.content_type}
        )
        
        # Získame verejný odkaz na zobrazenie webe
        public_url = supabase.storage.from_("post-images").get_public_url(file_name)
        
        return {"image_url": public_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
