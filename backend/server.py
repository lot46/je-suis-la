# backend/server.py
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import FastAPI, APIRouter, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("je-suis-la")

UTC = timezone.utc

# -----------------------------
# Env / Config
# -----------------------------
MONGO_URL = os.getenv("MONGO_URL", "").strip()
DB_NAME = os.getenv("DB_NAME", "").strip()

MVP_MODE = os.getenv("MVP_MODE", "true").strip().lower() == "true"
OTP_COOLDOWN_SECONDS = int(os.getenv("OTP_COOLDOWN_SECONDS", "60").strip())
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "5").strip())
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30").strip())

# (Optionnel) clé interne. Si absente, on continue quand même.
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()

if not MONGO_URL:
    raise RuntimeError("Missing env var MONGO_URL")
if not DB_NAME:
    raise RuntimeError("Missing env var DB_NAME")

# -----------------------------
# DB
# -----------------------------
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

col_otp = db["otp_codes"]
col_sessions = db["sessions"]
col_status = db["status"]

# -----------------------------
# Business rules
# -----------------------------
ALLOWED_STATUSES: Dict[str, str] = {
    "OK": "Je suis là",
    "NEED_CONTACT": "Aujourd’hui, c’est différent",
}

def normalize_status_key(raw: str) -> str:
    k = (raw or "").strip().upper()
    # tolérance : ok / need_contact / need-contact / needcontact
    if k == "OK":
        return "OK"
    k = k.replace("-", "_")
    if k == "NEEDCONTACT":
        k = "NEED_CONTACT"
    return k

def now_utc() -> datetime:
    return datetime.now(UTC)

def generate_code() -> str:
    # 6 digits, leading zeros allowed
    return f"{uuid.uuid4().int % 1000000:06d}"

def generate_token() -> str:
    return str(uuid.uuid4())

async def send_otp_email_stub(email: str, code: str) -> None:
    """
    MVP: pas d’envoi d’e-mail réel.
    PROD (plus tard): ici on branchera un provider email.
    """
    logger.info("MVP OTP for %s: %s", email, code)

# -----------------------------
# Schemas
# -----------------------------
class RequestCodeInput(BaseModel):
    email: EmailStr

class RequestCodeResponse(BaseModel):
    message: str
    code: Optional[str] = None  # renvoyé uniquement en MVP

class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)

class VerifyCodeResponse(BaseModel):
    token: str

class StatusOutput(BaseModel):
    status_key: Optional[str] = None
    status_label: Optional[str] = None
    updated_at: Optional[datetime] = None

class StatusSetInput(BaseModel):
    status_key: str

# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI(
    title="Je suis là API",
    version="0.1.0",
)

# CORS: permissif pour MVP (PWA / tests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

@api.get("/", summary="Root")
async def root():
    return {"message": "Je suis là API"}

# -----------------------------
# Auth: request code
# -----------------------------
@api.post("/auth/request-code", response_model=RequestCodeResponse, summary="Request Code")
async def request_code(payload: RequestCodeInput):
    email = payload.email.strip().lower()
    now = now_utc()

    # cooldown
    existing = await col_otp.find_one({"email": email, "used": False})
    if existing and existing.get("last_sent"):
        last_sent = existing["last_sent"]
        if isinstance(last_sent, datetime):
            delta = (now - last_sent).total_seconds()
            if delta < OTP_COOLDOWN_SECONDS:
                raise HTTPException(
                    status_code=429,
                    detail="Veuillez attendre avant de redemander un code",
                )

    code = generate_code()
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

    await col_otp.update_one(
        {"email": email},
        {"$set": {
            "email": email,
            "code": code,
            "used": False,
            "expires_at": expires_at,
            "last_sent": now,
        }},
        upsert=True,
    )

    # MVP: pas d'envoi réel
    await send_otp_email_stub(email, code)

    if MVP_MODE:
        return {"message": "Code généré (mode test)", "code": code}
    return {"message": "Code envoyé"}

# -----------------------------
# Auth: verify code -> token
# -----------------------------
@api.post("/auth/verify-code", response_model=VerifyCodeResponse, summary="Verify Code")
async def verify_code(payload: VerifyCodeInput):
    email = payload.email.strip().lower()
    code = payload.code.strip()
    now = now_utc()

    record = await col_otp.find_one({"email": email, "used": False})
    if not record:
        raise HTTPException(status_code=400, detail="Code introuvable")

    expires_at = record.get("expires_at")
    if not isinstance(expires_at, datetime) or now > expires_at:
        await col_otp.update_one({"email": email}, {"$set": {"used": True}})
        raise HTTPException(status_code=400, detail="Code expiré")

    if code != record.get("code"):
        raise HTTPException(status_code=400, detail="Code incorrect")

    # one-shot: marque comme utilisé
    await col_otp.update_one({"email": email}, {"$set": {"used": True}})

    token = generate_token()
    session_expires = now + timedelta(days=SESSION_TTL_DAYS)

    await col_sessions.insert_one({
        "token": token,
        "email": email,
        "created_at": now,
        "expires_at": session_expires,
    })

    return {"token": token}

# -----------------------------
# Dependency: session token
# -----------------------------
async def require_session(x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")) -> str:
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Session manquante")

    now = now_utc()
    sess = await col_sessions.find_one({"token": x_session_token})
    if not sess:
        raise HTTPException(status_code=401, detail="Token invalide")

    exp = sess.get("expires_at")
    if isinstance(exp, datetime) and now > exp:
        raise HTTPException(status_code=401, detail="Session expirée")

    return sess["email"]

# -----------------------------
# Status: get / set
# -----------------------------
@api.get("/status", response_model=StatusOutput, summary="Get Status")
async def get_status(email: str = Header(default=None, include_in_schema=False), x_email: Optional[str] = None, x_session_email: str = None, user_email: str = None, session_email: str = None, _=None, __=None, ___=None, ____=None, _____=None, ______=None, _______=None, ________=None, _________=None, __________=None, ___________=None, ____________=None):
    # NOTE: FastAPI header injection weirdness avoided; we use require_session below in a clean way.
    raise HTTPException(status_code=500, detail="Misconfigured route")

@api.post("/status", response_model=StatusOutput, summary="Set Status")
async def set_status(_: StatusSetInput):
    raise HTTPException(status_code=500, detail="Misconfigured route")

# Cleanly re-register routes with dependency (FastAPI limitation: can't "reuse" the previous decorated functions cleanly)
@api.get("/status", response_model=StatusOutput, include_in_schema=True)
async def get_status_real(x_session_email: str = None, x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    email = await require_session(x_session_token)
    doc = await col_status.find_one({"email": email})
    if not doc:
        return {"status_key": None, "status_label": None, "updated_at": None}
    return {
        "status_key": doc.get("status_key"),
        "status_label": doc.get("status_label"),
        "updated_at": doc.get("updated_at"),
    }

@api.post("/status", response_model=StatusOutput, include_in_schema=True)
async def set_status_real(payload: StatusSetInput, x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    email = await require_session(x_session_token)

    key = normalize_status_key(payload.status_key)
    if key not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Statut invalide")

    label = ALLOWED_STATUSES[key]
    now = now_utc()

    await col_status.update_one(
        {"email": email},
        {"$set": {"email": email, "status_key": key, "status_label": label, "updated_at": now}},
        upsert=True,
    )

    return {"status_key": key, "status_label": label, "updated_at": now}

# Register router
app.include_router(api)
