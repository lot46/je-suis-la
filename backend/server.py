from fastapi import FastAPI, APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import os
import random
import string
import uuid

# =====================
# ENV
# =====================
MVP_MODE = os.getenv("MVP_MODE", "true").lower() == "true"
OTP_COOLDOWN_SECONDS = int(os.getenv("OTP_COOLDOWN_SECONDS", "60"))

# =====================
# APP + ROUTER
# =====================
app = FastAPI(title="Je suis là API", version="0.1.0")
api = APIRouter(prefix="/api")

# =====================
# STOCKAGE MVP (en mémoire)
# =====================
otp_store = {}      # email -> {"code": str, "expires_at": datetime, "last_sent": datetime}
token_store = {}    # token -> {"email": str, "created_at": datetime}
status_store = {}   # email -> {"status_key": str, "status_label": str, "updated_at": str}

# =====================
# MODELS
# =====================
class RequestCodeInput(BaseModel):
    email: EmailStr

class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str

class StatusUpdateInput(BaseModel):
    status_key: str  # "OK" or "NEED_CONTACT"

# =====================
# UTILS
# =====================
def gen_code() -> str:
    return "".join(random.choices(string.digits, k=6))

def gen_token() -> str:
    return str(uuid.uuid4())

def now_utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def status_label(key: str) -> str:
    if key == "OK":
        return "Je suis là"
    if key == "NEED_CONTACT":
        return "Aujourd'hui, c'est différent"
    raise HTTPException(status_code=400, detail="Statut invalide")

def get_email_from_token(x_session_token: str | None) -> str:
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Token manquant")
    rec = token_store.get(x_session_token)
    if not rec:
        raise HTTPException(status_code=401, detail="Token invalide")
    return rec["email"]

# =====================
# ROUTES
# =====================
@api.get("/")
def root():
    return {"message": "Je suis là API"}

@api.post("/auth/request-code")
def request_code(payload: RequestCodeInput):
    email = payload.email.strip().lower()
    now = datetime.utcnow()

    rec = otp_store.get(email)
    if rec and (now - rec["last_sent"]).total_seconds() < OTP_COOLDOWN_SECONDS:
        raise HTTPException(status_code=429, detail="Veuillez attendre avant de redemander un code")

    code = gen_code()
    otp_store[email] = {
        "code": code,
        "expires_at": now + timedelta(minutes=5),
        "last_sent": now,
    }

    # MVP : on renvoie le code pour test
    if MVP_MODE:
        return {"message": "Code généré (mode test)", "code": code}

    # Prod : on ne renvoie pas le code (plus tard on branchera email)
    return {"message": "Code généré"}

@api.post("/auth/verify-code")
def verify_code(payload: VerifyCodeInput):
    email = payload.email.strip().lower()
    code = payload.code.strip()
    now = datetime.utcnow()

    rec = otp_store.get(email)
    if not rec:
        raise HTTPException(status_code=400, detail="Code introuvable")

    if now > rec["expires_at"]:
        del otp_store[email]
        raise HTTPException(status_code=400, detail="Code expiré")

    if code != rec["code"]:
        raise HTTPException(status_code=400, detail="Code incorrect")

    # one-shot
    del otp_store[email]

    token = gen_token()
    token_store[token] = {"email": email, "created_at": now}

    return {"token": token}

# ✅ STATUS (ce qui manquait)
@api.get("/status")
def get_status(x_session_token: str | None = Header(default=None, alias="X-Session-Token")):
    email = get_email_from_token(x_session_token)
    return status_store.get(email, {"status_key": None, "status_label": None, "updated_at": None})

@api.post("/status")
def set_status(payload: StatusUpdateInput, x_session_token: str | None = Header(default=None, alias="X-Session-Token")):
    email = get_email_from_token(x_session_token)
    label = status_label(payload.status_key)
    status_store[email] = {
        "status_key": payload.status_key,
        "status_label": label,
        "updated_at": now_utc_iso()
    }
    return status_store[email]

# IMPORTANT
app.include_router(api)
