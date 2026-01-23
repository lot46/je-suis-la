from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta, timezone
import os
import random
import string
import uuid

# =========================
# ENV
# =========================
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
MVP_MODE = os.getenv("MVP_MODE", "true").lower() == "true"
OTP_COOLDOWN_SECONDS = int(os.getenv("OTP_COOLDOWN_SECONDS", "60"))

# =========================
# Mongo
# =========================
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
otp_codes = db.otp_codes
sessions = db.sessions

# =========================
# App
# =========================
app = FastAPI(title="Je suis là API", version="0.1.0")
api = APIRouter(prefix="/api")

# =========================
# Models
# =========================
class RequestCodeInput(BaseModel):
    email: EmailStr

class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str

# =========================
# Utils
# =========================
def now_utc():
    return datetime.now(timezone.utc)

def gen_code():
    return "".join(random.choices(string.digits, k=6))

def gen_token():
    return str(uuid.uuid4())

# =========================
# Routes
# =========================
@api.get("/")
async def root():
    return {"message": "Je suis là API"}

@api.post("/auth/request-code")
async def request_code(payload: RequestCodeInput):
    email = payload.email.strip().lower()
    now = now_utc()

    # Cooldown anti-spam
    last = await otp_codes.find_one({"email": email}, sort=[("created_at", -1)])
    if last and (now - last["created_at"]).total_seconds() < OTP_COOLDOWN_SECONDS:
        raise HTTPException(status_code=429, detail="Veuillez attendre avant de redemander un code")

    code = gen_code()

    await otp_codes.insert_one({
        "email": email,
        "code": code,
        "created_at": now,
        "expires_at": now + timedelta(minutes=5),
        "used": False,
    })

    # ✅ BLOc 1 : comportement MVP_MODE
    if MVP_MODE:
        return {"message": "Code généré (mode test)", "code": code}

    # En mode public : on ne renvoie jamais le code
    return {"message": "Code généré"}

@api.post("/auth/verify-code")
async def verify_code(payload: VerifyCodeInput):
    email = payload.email.strip().lower()
    code = payload.code.strip()
    now = now_utc()

    record = await otp_codes.find_one({
        "email": email,
        "code": code,
        "used": False,
        "expires_at": {"$gt": now}
    })

    if not record:
        raise HTTPException(status_code=400, detail="Code incorrect")

    # one-shot
    await otp_codes.update_one({"_id": record["_id"]}, {"$set": {"used": True}})

    token = gen_token()
    await sessions.insert_one({
        "token": token,
        "email": email,
        "created_at": now,
        "expires_at": now + timedelta(days=30),
    })

    return {"token": token}

app.include_router(api)
