from fastapi import FastAPI, APIRouter, Header, HTTPException
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict
import os
import random
import uuid
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

# -----------------------------
# Je suis là - API V1
# Auth e-mail + code (MVP: code renvoyé dans la réponse)
# Statut: OK / NEED_CONTACT
# MongoDB via Motor
# -----------------------------

APP_TITLE = "Je suis là API"

ALLOWED_STATUSES: Dict[str, str] = {
    "OK": "Je suis là",
    "NEED_CONTACT": "Aujourd'hui, c'est différent",
}

OTP_TTL_MINUTES = 10
SESSION_TTL_DAYS = 30

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _utc_in_minutes(minutes: int) -> datetime:
    return _utc_now() + timedelta(minutes=minutes)

def _utc_in_days(days: int) -> datetime:
    return _utc_now() + timedelta(days=days)

def _norm_email(email: str) -> str:
    return email.strip().lower()

def _gen_otp_code() -> str:
    return f"{random.randint(0, 999999):06d}"

# -----------------------------
# MongoDB connection
# -----------------------------
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

if not MONGO_URL:
    raise RuntimeError("Missing env var: MONGO_URL")
if not DB_NAME:
    raise RuntimeError("Missing env var: DB_NAME")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Collections
otp_col = db["otp_codes"]
users_col = db["users"]
sessions_col = db["sessions"]
status_col = db["status"]  # one doc per user

# -----------------------------
# Models
# -----------------------------
class RequestCodeInput(BaseModel):
    email: EmailStr

class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str

class StatusUpdateInput(BaseModel):
    status_key: str

class StatusOutput(BaseModel):
    status_key: Optional[str] = None
    status_label: Optional[str] = None

# -----------------------------
# App + Router
# -----------------------------
app = FastAPI(title=APP_TITLE)
api_router = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # V1
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Helpers
# -----------------------------
async def _create_or_refresh_otp(email: str) -> str:
    code = _gen_otp_code()
    await otp_col.update_one(
        {"email": email},
        {"$set": {
            "email": email,
            "code": code,
            "created_at": _utc_now(),
            "expires_at": _utc_in_minutes(OTP_TTL_MINUTES),
        }},
        upsert=True
    )
    return code

async def _verify_otp(email: str, code: str) -> bool:
    doc = await otp_col.find_one({"email": email, "code": code})
    if not doc:
        return False
    expires_at = doc.get("expires_at")
    if expires_at and expires_at < _utc_now():
        return False
    return True

async def _consume_otp(email: str):
    await otp_col.delete_one({"email": email})

async def _get_or_create_user(email: str):
    user = await users_col.find_one({"email": email})
    if user:
        return user
    user_doc = {"email": email, "created_at": _utc_now()}
    res = await users_col.insert_one(user_doc)
    user_doc["_id"] = res.inserted_id
    return user_doc

async def _create_session(email: str, user_id):
    token = str(uuid.uuid4())
    await sessions_col.insert_one({
        "token": token,
        "email": email,
        "user_id": user_id,
        "created_at": _utc_now(),
        "expires_at": _utc_in_days(SESSION_TTL_DAYS),
    })
    return token

async def _require_session(x_session_token: Optional[str]) -> dict:
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Session manquante")
    sess = await sessions_col.find_one({"token": x_session_token})
    if not sess:
        raise HTTPException(status_code=401, detail="Session invalide")
    expires_at = sess.get("expires_at")
    if expires_at and expires_at < _utc_now():
        raise HTTPException(status_code=401, detail="Session expirée")
    return sess

async def _get_status(email: str) -> Optional[str]:
    doc = await status_col.find_one({"email": email})
    if not doc:
        return None
    return doc.get("status_key")

async def _set_status(email: str, status_key: str):
    await status_col.update_one(
        {"email": email},
        {"$set": {
            "email": email,
            "status_key": status_key,
            "updated_at": _utc_now(),
        }},
        upsert=True
    )

# -----------------------------
# Routes
# -----------------------------
@api_router.get("/")
async def api_root():
    return {"message": "Je suis là API"}

@api_router.get("/health")
async def health():
    return {"ok": True}

@api_router.post("/auth/request-code")
async def request_code(payload: RequestCodeInput):
    email = _norm_email(payload.email)
    code = await _create_or_refresh_otp(email)
    # MVP: on renvoie le code directement
    return {"message": "Code généré", "code": code}

@api_router.post("/auth/verify-code")
async def verify_code(payload: VerifyCodeInput):
    email = _norm_email(payload.email)
    code = payload.code.strip()

    ok = await _verify_otp(email, code)
    if not ok:
        raise HTTPException(status_code=400, detail="Code introuvable")

    # One-shot code
    await _consume_otp(email)

    # User + session
    user = await _get_or_create_user(email)
    token = await _create_session(email, user["_id"])

    return {"token": token, "user": {"email": email}}

@api_router.get("/status", response_model=StatusOutput)
async def get_status(x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    sess = await _require_session(x_session_token)
    email = sess["email"]
    status_key = await _get_status(email)
    if not status_key:
        return {"status_key": None, "status_label": None}
    return {"status_key": status_key, "status_label": ALLOWED_STATUSES.get(status_key)}

@api_router.post("/status", response_model=StatusOutput)
async def set_status(payload: StatusUpdateInput, x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    sess = await _require_session(x_session_token)
    email = sess["email"]

    status_key = payload.status_key.strip()
    if status_key not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Statut invalide")

    await _set_status(email, status_key)
    return {"status_key": status_key, "status_label": ALLOWED_STATUSES[status_key]}

app.include_router(api_router)
