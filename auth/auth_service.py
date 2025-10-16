import os
import psycopg2
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from contextlib import asynccontextmanager

# Environment variables
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "pguser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "auth_db")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key")

def get_db_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )

def init_db():
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL
                    )
                    """
                )
                connection.commit()
        print("Database initialized successfully.")
    except psycopg2.Error as e:
        print(f"Database initialization error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(  # type: ignore
    CORSMiddleware,
    allow_origins=["*"],  # Change to your frontend domain(s) in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserModel(BaseModel):
    email: str

@app.get("/")
async def healthcheck():
    return {"status": "ok"}

@app.get("/api/auth/login")
async def login(id_token_str: str):
    if not id_token_str:
        raise HTTPException(status_code=400, detail="Missing id_token")

    try:
        idinfo = id_token.verify_oauth2_token(id_token_str, GoogleRequest())
        email = idinfo["email"]

        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()

        if not user:
            raise HTTPException(status_code=403, detail="Unauthorized user")

        payload = {
            "email": email,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

        return {"token": token}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.post("/api/auth/validate-token")
async def validate_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=400, detail="Missing Authorization header")

    try:
        parts = auth_header.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=400, detail="Invalid Authorization header format")
        token = parts[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return {"email": payload["email"]}
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/auth/add-user")
async def add_user(user: UserModel):
    email = user.email
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO users (email) VALUES (%s)", (email,))
                connection.commit()
        return {"message": f"User {email} added successfully."}
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail=f"User {email} is already authorized.")
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8080)