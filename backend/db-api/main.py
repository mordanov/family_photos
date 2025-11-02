import os
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from passlib.hash import bcrypt

# Environment variables for DB connection
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_USER = os.getenv("POSTGRES_USER", "pguser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "auth_db")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"

# SQLAlchemy setup
engine = sa.create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# SQLAlchemy ORM models
class UserTable(Base):
    __tablename__ = "users"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    username = sa.Column(sa.String, unique=True, index=True, nullable=False)
    password = sa.Column(sa.String, nullable=False)

class ImageTable(Base):
    __tablename__ = "images"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    filename = sa.Column(sa.String, nullable=False)
    folder = sa.Column(sa.String, nullable=False)
    owner = sa.Column(sa.String, nullable=False)

# Create tables if they do not exist
Base.metadata.create_all(engine)

# FastAPI app
app = FastAPI()

# Pydantic models
class User(BaseModel):
    username: str
    password: str
    model_config = ConfigDict(from_attributes=True)

class UserOut(BaseModel):
    id: int
    username: str
    model_config = ConfigDict(from_attributes=True)

class ImageMeta(BaseModel):
    id: Optional[int]
    filename: str
    folder: str
    owner: str
    model_config = ConfigDict(from_attributes=True)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Endpoints
@app.post("/auth/login")
def login(user: User, db: Session = Depends(get_db)):
    db_user = db.query(UserTable).filter(UserTable.username == user.username).first()
    if db_user and bcrypt.verify(user.password, db_user.password):
        return {"access_token": "dummy-token"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/auth/users", response_model=UserOut)
def create_user(user: User, db: Session = Depends(get_db)):
    if db.query(UserTable).filter(UserTable.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed = bcrypt.hash(user.password)
    new_user = UserTable(username=user.username, password=hashed)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return UserOut(id=new_user.id, username=new_user.username)

@app.put("/auth/users/{username}")
def modify_user(username: str, user: User, db: Session = Depends(get_db)):
    db_user = db.query(UserTable).filter(UserTable.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db_user.password = bcrypt.hash(user.password)
    db.commit()
    return {"msg": "User updated"}

@app.get("/images", response_model=List[ImageMeta])
def list_images(db: Session = Depends(get_db)):
    images = db.query(ImageTable).all()
    return [ImageMeta.model_validate(img) for img in images]

@app.post("/images/metadata", response_model=ImageMeta)
def add_image_metadata(meta: ImageMeta, db: Session = Depends(get_db)):
    new_image = ImageTable(filename=meta.filename, folder=meta.folder, owner=meta.owner)
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    return ImageMeta(id=new_image.id, filename=new_image.filename, folder=new_image.folder, owner=new_image.owner)

@app.delete("/images/metadata/{image_id}")
def delete_image_metadata(image_id: int, db: Session = Depends(get_db)):
    img = db.query(ImageTable).filter(ImageTable.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image metadata not found")
    db.delete(img)
    db.commit()
    return {"msg": "Metadata deleted"}