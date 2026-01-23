from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
import os
import uuid
import time

# =====================
# CONFIG
# =====================

MVP_MODE = os.getenv("MVP_MODE", "true").lower() == "true"
OTP_COOLDOWN = int(os.getenv("OTP_COOLDOWN_SECONDS", "60"))

# Stockage mémoire MVP (VOLONTAIREMENT)
OTP_STORE = {}
TOKEN_STORE = {}

# =====================
# MODELS
# =====================

class RequestCodeInput(BaseModel):
    email: EmailStr

class RequestCodeResponse(BaseModel):
    message: str
    code: str

class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str

class VerifyCodeResponse(BaseModel):
    token: str

# =====================
# APP
# =====================

app = FastAPI(title="Je suis là API")
router = APIRouter(prefix="/api")

@router.get("/")
def root():
    return {"message": "Je suis là API"}

# =====================
# AUTH
# =====================

@router.post("/auth/request-code", response_model=RequestCodeResponse)
def request_code(payload: RequestCodeInput):
    now = time.time()

    if payload.email in OTP_STORE:
        last_time = OTP_STORE[payload.email]["timestamp"]
        if now - last_time < OTP_COOLDOWN:
            raise HTTPException(status_code=429, detail="Attendre avant un nouveau code")

    code = str(uuid.uuid4().int)[-6:]

    OTP_STORE[payload.email] = {
        "code": code,
        "timestamp": now
    }

    return {
        "message": "Code généré",
        "code": code
    }

@router.post("/auth/verify-code", response_model=VerifyCodeResponse)
def verify_code(payload: VerifyCodeInput):
    entry = OTP_STORE.get(payload.email)

    if not entry:
        raise HTTPException(status_code=400, detail="Code introuvable")

    if payload.code != entry["code"]:
        raise HTTPException(status_code=400, detail="Code incorrect")

    token = str(uuid.uuid4())

    TOKEN_STORE[token] = {
        "email": payload.email,
        "created_at": time.time()
    }

    del OTP_STORE[payload.email]

    return {
        "token": token
    }

# =====================
# ROUTER
# =====================

app.include_router(router)
