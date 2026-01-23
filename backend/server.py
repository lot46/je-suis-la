from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import os
import random
import string

# =========================================================
# CONFIG
# =========================================================

MVP_MODE = os.getenv("MVP_MODE", "true").lower() == "true"
OTP_COOLDOWN_SECONDS = int(os.getenv("OTP_COOLDOWN_SECONDS", "60"))

# =========================================================
# APP
# =========================================================

app = FastAPI(title="Je suis là API", version="0.1.0")
api = APIRouter(prefix="/api")

# =========================================================
# STOCKAGE OTP (MVP SIMPLE, MÉMOIRE)
# =========================================================
# ⚠️ Volontairement en mémoire (MVP)
# ⚠️ Aucun stockage sensible long terme
# ⚠️ Conforme éthique : temporaire, effaçable

otp_store = {}
# structure :
# {
#   email: {
#       "code": "123456",
#       "expires_at": datetime,
#       "last_sent": datetime
#   }
# }

# =========================================================
# MODELS
# =========================================================

class RequestCodeInput(BaseModel):
    email: EmailStr


class RequestCodeResponse(BaseModel):
    message: str
    code: str  # ⚠️ renvoyé UNIQUEMENT en MVP


class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str


class VerifyCodeResponse(BaseModel):
    token: str


# =========================================================
# UTILS
# =========================================================

def generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def generate_token() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=32))


# =========================================================
# ROUTES
# =========================================================

@api.get("/")
def root():
    return {"message": "Je suis là API"}


@api.post("/auth/request-code", response_model=RequestCodeResponse)
def request_code(payload: RequestCodeInput):
    now = datetime.utcnow()

    record = otp_store.get(payload.email)

    if record and now - record["last_sent"] < timedelta(seconds=OTP_COOLDOWN_SECONDS):
        raise HTTPException(
            status_code=429,
            detail="Veuillez attendre avant de redemander un code"
        )

    code = generate_code()

    otp_store[payload.email] = {
        "code": code,
        "expires_at": now + timedelta(minutes=5),
        "last_sent": now
    }

    return {
        "message": "Code généré",
        "code": code  # ⚠️ MVP uniquement
    }


@api.post("/auth/verify-code", response_model=VerifyCodeResponse)
def verify_code(payload: VerifyCodeInput):
    record = otp_store.get(payload.email)

    if not record:
        raise HTTPException(status_code=400, detail="Code introuvable")

    if datetime.utcnow() > record["expires_at"]:
        del otp_store[payload.email]
        raise HTTPException(status_code=400, detail="Code expiré")

    if payload.code != record["code"]:
        raise HTTPException(status_code=400, detail="Code incorrect")

    del otp_store[payload.email]

    return {
        "token": generate_token()
    }


# =========================================================
# REGISTER ROUTER
# =========================================================

app.include_router(api)
