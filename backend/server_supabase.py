import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import FastAPI, APIRouter, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from dotenv import load_dotenv

# Supabase
from supabase import create_client, Client

# -----------------------------
# ENV / SETTINGS
# -----------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", os.getenv("VITE_SUPABASE_URL", "")).strip()
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", os.getenv("VITE_SUPABASE_ANON_KEY", "")).strip()

# MVP_MODE=true => returns code in response (test only).
MVP_MODE = os.getenv("MVP_MODE", "true").strip().lower() == "true"

OTP_COOLDOWN_SECONDS = int(os.getenv("OTP_COOLDOWN_SECONDS", "60").strip() or "60")
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "5").strip() or "5")

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    SECRET_KEY = "dev-secret-not-for-production"

ALLOWED_STATUSES: Dict[str, str] = {
    "OK": "Je suis la",
    "NEED_CONTACT": "Aujourd'hui, c'est different",
}

# -----------------------------
# SUPABASE CLIENT
# -----------------------------
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# MODELS
# -----------------------------
class RequestCodeInput(BaseModel):
    email: EmailStr

class RequestCodeResponse(BaseModel):
    message: str
    code: Optional[str] = None

class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str

class VerifyCodeResponse(BaseModel):
    token: str

class StatusGetResponse(BaseModel):
    status_key: Optional[str] = None
    status_label: Optional[str] = None
    updated_at: Optional[str] = None

class StatusSetInput(BaseModel):
    status_key: str
    status_label: Optional[str] = None

class StatusSetResponse(BaseModel):
    status_key: str
    status_label: str
    updated_at: str

# -----------------------------
# HELPERS
# -----------------------------
def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def generate_code() -> str:
    return f"{uuid.uuid4().int % 1000000:06d}"

def generate_token() -> str:
    return str(uuid.uuid4())

async def get_email_from_token(x_session_token: Optional[str]) -> str:
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Missing X-Session-Token")

    response = supabase.table("sessions").select("email, expires_at").eq("token", x_session_token).execute()

    if not response.data:
        raise HTTPException(status_code=401, detail="Token invalid")

    sess = response.data[0]
    expires_at = sess.get("expires_at")

    if expires_at:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if utcnow() > expires_dt:
            supabase.table("sessions").delete().eq("token", x_session_token).execute()
            raise HTTPException(status_code=401, detail="Token expired")

    return sess["email"]

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

# -----------------------------
# APP
# -----------------------------
app = FastAPI(title="Je suis la API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

@api.get("/", tags=["default"])
async def root():
    return {"message": "Je suis la API"}

# -----------------------------
# AUTH
# -----------------------------
@api.post("/auth/request-code", response_model=RequestCodeResponse, tags=["auth"])
async def request_code(payload: RequestCodeInput):
    email = payload.email.strip().lower()
    now = utcnow()

    # Check cooldown
    response = supabase.table("otp_codes").select("last_sent_at").eq("email", email).execute()

    if response.data:
        existing = response.data[0]
        last_sent_at = existing.get("last_sent_at")
        if last_sent_at:
            last_dt = datetime.fromisoformat(last_sent_at.replace("Z", "+00:00"))
            if (now - last_dt).total_seconds() < OTP_COOLDOWN_SECONDS:
                raise HTTPException(status_code=429, detail="Please wait before requesting a new code")

    code = generate_code()
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

    supabase.table("otp_codes").upsert({
        "email": email,
        "code": code,
        "expires_at": iso(expires_at),
        "last_sent_at": iso(now),
        "used": False,
    }, on_conflict="email").execute()

    if MVP_MODE:
        return {"message": "Code genere (mode test)", "code": code}

    return {"message": "Code envoye"}

@api.post("/auth/verify-code", response_model=VerifyCodeResponse, tags=["auth"])
async def verify_code(payload: VerifyCodeInput):
    email = payload.email.strip().lower()
    code = payload.code.strip()
    now = utcnow()

    response = supabase.table("otp_codes").select("*").eq("email", email).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Code introuvable")

    record = response.data[0]

    if record.get("used"):
        raise HTTPException(status_code=400, detail="Code introuvable")

    expires_at = record.get("expires_at")
    if expires_at:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if now > expires_dt:
            supabase.table("otp_codes").delete().eq("email", email).execute()
            raise HTTPException(status_code=400, detail="Code expire")

    if code != record["code"]:
        raise HTTPException(status_code=400, detail="Code incorrect")

    # Mark code as used
    supabase.table("otp_codes").update({"used": True}).eq("email", email).execute()

    token = generate_token()
    expires_at = now + timedelta(days=30)

    supabase.table("sessions").upsert({
        "token": token,
        "email": email,
        "created_at": iso(now),
        "expires_at": iso(expires_at),
    }, on_conflict="token").execute()

    return {"token": token}

# -----------------------------
# STATUS
# -----------------------------
@api.get("/status", response_model=StatusGetResponse, tags=["status"])
async def get_status(x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    email = await get_email_from_token(x_session_token)

    response = supabase.table("status").select("*").eq("email", email).execute()

    if not response.data:
        return {"status_key": None, "status_label": None, "updated_at": None}

    doc = response.data[0]
    return {
        "status_key": doc.get("status_key"),
        "status_label": doc.get("status_label"),
        "updated_at": doc.get("updated_at"),
    }

@api.post("/status", response_model=StatusSetResponse, tags=["status"])
async def set_status(
    payload: StatusSetInput,
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
):
    email = await get_email_from_token(x_session_token)

    status_key = payload.status_key.strip().upper()
    if status_key not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Statut invalide")

    status_label = (payload.status_label or "").strip()
    if not status_label:
        status_label = ALLOWED_STATUSES[status_key]

    now = utcnow()

    supabase.table("status").upsert({
        "email": email,
        "status_key": status_key,
        "status_label": status_label,
        "updated_at": iso(now),
    }, on_conflict="email").execute()

    return {"status_key": status_key, "status_label": status_label, "updated_at": iso(now)}

app.include_router(api)
