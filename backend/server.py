import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import FastAPI, APIRouter, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# -----------------------------
# ENV / SETTINGS
# -----------------------------
load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "").strip()
DB_NAME = os.getenv("DB_NAME", "je_suis_la").strip()

# MVP_MODE=true => on renvoie le code dans la réponse (test uniquement).
# MVP_MODE=false => on NE renvoie JAMAIS le code (il faut envoyer par email via un provider).
MVP_MODE = os.getenv("MVP_MODE", "true").strip().lower() == "true"

OTP_COOLDOWN_SECONDS = int(os.getenv("OTP_COOLDOWN_SECONDS", "60").strip() or "60")
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "5").strip() or "5")

# Secret de session (utilisé pour versionner/sécuriser le modèle, même si on stocke le token en DB)
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    # On évite de crasher si l'env n'est pas encore posée,
    # mais en prod tu DOIS la définir côté Render.
    SECRET_KEY = "dev-secret-not-for-production"

ALLOWED_STATUSES: Dict[str, str] = {
    "OK": "Je suis là",
    "NEED_CONTACT": "Aujourd’hui, c’est différent",
}

# -----------------------------
# DB
# -----------------------------
if not MONGO_URL:
    raise RuntimeError("MONGO_URL is missing. Set it in Render Environment Variables.")

mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client[DB_NAME]

otp_codes = db["otp_codes"]      # {email, code, expires_at, last_sent_at, used}
sessions = db["sessions"]        # {token, email, created_at, expires_at}
status_coll = db["status"]       # {email, status_key, status_label, updated_at}

# Indexes (best-effort)
# NOTE: motor creates indexes async at runtime; if it fails, app still runs.
async def ensure_indexes():
    try:
        await otp_codes.create_index("email", unique=True)
        await sessions.create_index("token", unique=True)
        await status_coll.create_index("email", unique=True)
    except Exception:
        pass

# -----------------------------
# MODELS
# -----------------------------
class RequestCodeInput(BaseModel):
    email: EmailStr

class RequestCodeResponse(BaseModel):
    message: str
    # En MVP_MODE uniquement, on renvoie "code"
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
    # optionnel : si non fourni, on le déduit via ALLOWED_STATUSES
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
    # 6 digits
    return f"{uuid.uuid4().int % 1000000:06d}"

def generate_token() -> str:
    return str(uuid.uuid4())

async def get_email_from_token(x_session_token: Optional[str]) -> str:
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Missing X-Session-Token")
    sess = await sessions.find_one({"token": x_session_token})
    if not sess:
        raise HTTPException(status_code=401, detail="Token invalid")
    if sess.get("expires_at") and utcnow() > sess["expires_at"]:
        # session expirée
        await sessions.delete_one({"token": x_session_token})
        raise HTTPException(status_code=401, detail="Token expired")
    return sess["email"]

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

# -----------------------------
# APP
# -----------------------------
app = FastAPI(title="Je suis là API", version="0.1.0")

# CORS permissif pour MVP (à durcir ensuite)
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
    return {"message": "Je suis là API"}

# -----------------------------
# AUTH
# -----------------------------
@api.post("/auth/request-code", response_model=RequestCodeResponse, tags=["auth"])
async def request_code(payload: RequestCodeInput):
    email = payload.email.strip().lower()
    now = utcnow()

    # cooldown
    existing = await otp_codes.find_one({"email": email})
    if existing and existing.get("last_sent_at"):
        last_sent_at = existing["last_sent_at"]
        if isinstance(last_sent_at, str):
            # safety: if stored as string, ignore cooldown
            last_sent_at = None
        if last_sent_at and (now - last_sent_at).total_seconds() < OTP_COOLDOWN_SECONDS:
            raise HTTPException(status_code=429, detail="Please wait before requesting a new code")

    code = generate_code()
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

    await otp_codes.update_one(
        {"email": email},
        {"$set": {
            "email": email,
            "code": code,
            "expires_at": expires_at,
            "last_sent_at": now,
            "used": False,
        }},
        upsert=True
    )

    # MVP: on renvoie le code (test). Prod: on ne renvoie jamais le code.
    if MVP_MODE:
        return {"message": "Code généré (mode test)", "code": code}

    # PRODUCTION PATH (placeholder)
    # Ici tu brancheras un provider email (Mailgun/SES/Sendgrid etc.)
    # et tu renverras une réponse neutre.
    return {"message": "Code envoyé"}

@api.post("/auth/verify-code", response_model=VerifyCodeResponse, tags=["auth"])
async def verify_code(payload: VerifyCodeInput):
    email = payload.email.strip().lower()
    code = payload.code.strip()
    now = utcnow()

    record = await otp_codes.find_one({"email": email})
    if not record or record.get("used"):
        raise HTTPException(status_code=400, detail="Code introuvable")

    if now > record["expires_at"]:
        await otp_codes.delete_one({"email": email})
        raise HTTPException(status_code=400, detail="Code expiré")

    if code != record["code"]:
        raise HTTPException(status_code=400, detail="Code incorrect")

    # code one-shot: mark used
    await otp_codes.update_one({"email": email}, {"$set": {"used": True}})

    token = generate_token()
    # Session TTL: 30 jours (MVP)
    expires_at = now + timedelta(days=30)

    await sessions.update_one(
        {"token": token},
        {"$set": {
            "token": token,
            "email": email,
            "created_at": now,
            "expires_at": expires_at,
        }},
        upsert=True
    )

    return {"token": token}

# -----------------------------
# STATUS
# -----------------------------
@api.get("/status", response_model=StatusGetResponse, tags=["status"])
async def get_status(x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    email = await get_email_from_token(x_session_token)
    doc = await status_coll.find_one({"email": email})
    if not doc:
        return {"status_key": None, "status_label": None, "updated_at": None}
    updated_at = doc.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = iso(updated_at)
    return {
        "status_key": doc.get("status_key"),
        "status_label": doc.get("status_label"),
        "updated_at": updated_at,
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

    await status_coll.update_one(
        {"email": email},
        {"$set": {
            "email": email,
            "status_key": status_key,
            "status_label": status_label,
            "updated_at": now,
        }},
        upsert=True
    )

    return {"status_key": status_key, "status_label": status_label, "updated_at": iso(now)}

app.include_router(api)

@app.on_event("startup")
async def _startup():
    await ensure_indexes()
