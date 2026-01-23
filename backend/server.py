from fastapi import FastAPI, APIRouter, HTTPException
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
# APP + ROUTER (IMPORTANT : api est défini AVANT les décorateurs)
# =====================
app = FastAPI(title="Je suis là API", version="0.1.0")
api = APIRouter(prefix="/api")

# =====================
# STOCKAGE MVP (mémoire)
# =====================
otp_store = {}  # email -> {"code": str, "expires_at": datetime, "last_sent": datetime}

# =====================
# MODELS
# =====================
class RequestCodeInput(BaseModel):
    email: EmailStr

class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str

# =====================
# UTILS
# =====================
def gen_code() -> str:
    return "".join(random.choices(string.digits, k=6))

def gen_token() -> str:
    return str(uuid.uuid4())

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

    # MVP_MODE=true : on renvoie le code (test)
    if MVP_MODE:
        return {"message": "Code généré (mode test)", "code": code}

    # MVP_MODE=false : on ne renvoie pas le code (prod)
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
    return {"token": gen_token()}

# IMPORTANT
app.include_router(api)
