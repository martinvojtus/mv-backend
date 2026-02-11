from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, create_engine, Session, select
from typing import List, Optional
from datetime import datetime
import os

# Databáza
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
engine = create_engine(DB_URL)

class Post(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    text: str
    at: datetime = Field(default_factory=datetime.utcnow)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def boot(): SQLModel.metadata.create_all(engine)

@app.get("/posts", response_model=List[Post])
def get_posts():
    with Session(engine) as s: return s.exec(select(Post).order_by(Post.at.desc())).all()

@app.post("/posts")
def add_post(p: Post):
    with Session(engine) as s:
        s.add(p); s.commit(); s.refresh(p); return p
