from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import os
import random

# ======================
# Configuration MongoDB
# ======================

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
OTP_COOLDOWN_SECONDS = int(os.environ.get("OTP_COOLDOWN_SECONDS", 60))

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

otp_codes = db.otp_codes

# ======================
# App FastAPI
# ======================

app = FastAPI(title="Je suis là API")
api = APIRouter(prefix="/api")

# ======================
# Models
# ======================

class RequestCodeInput(BaseModel):
    email: EmailStr

class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str

# ======================
# Routes
# ======================

@api.get("/")
async def root():
    return {"message": "Je suis là API"}

@api.post("/auth/request-code")
async def request_code(input: RequestCodeInput):
    now = datetime.now(timezone.utc)

    last = await otp_codes.find_one(
        {"email": input.email},
        sort=[("created_at", -1)]
    )

    if last and (now - last["created_at"]).total_seconds() < OTP_COOLDOWN_SECONDS:
        raise HTTPException(status_code=429, detail="Attends avant de redemander un code")

    code = str(random.randint(100000, 999999))

    await otp_codes.insert_one({
        "email": input.email,
        "code": code,
        "created_at": now,
        "expires_at": now + timedelta(minutes=10),
        "used": False
    })

    return {
        "message": "Code généré",
        "code": code  # MVP uniquement
    }

@api.post("/auth/verify-code")
async def verify_code(input: VerifyCodeInput):
    record = await otp_codes.find_one({
        "email": input.email,
        "code": input.code,
        "used": False,
        "expires_at": {"$gt": datetime.now(timezone.utc)}
    })

    if not record:
        raise HTTPException(status_code=400, detail="Code incorrect")

    await otp_codes.update_one(
        {"_id": record["_id"]},
        {"$set": {"used": True}}
    )

    return {
        "token": "SESSION_OK_MVP"
    }

# ======================
# Register router
# ======================

app.include_router(api)
