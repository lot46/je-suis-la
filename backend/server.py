from fastapi import FastAPI, APIRouter, Header, HTTPException
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import random
import time

# -----------------------------
# V1 "Je suis là" - sans base de données (Option 1)
# - pas de MONGO_URL
# - pas de DB_NAME
# - stockage minimal en mémoire (reset si redémarrage Render)
# -----------------------------

APP_TITLE = "Je suis là API"

# Deux statuts (V1 verrouillée)
ALLOWED_STATUSES = {
    "OK": "Je suis là",
    "NEED_CONTACT": "Aujourd'hui, c'est différent",
}

# Stockage en mémoire
# email -> code + expiration
otp_store = {}  # { email: {"code": "123456", "expires_at": 1234567890} }
# token -> email
session_store = {}  # { token: email }
# email -> status_key
status_store = {}  # { email: "OK" | "NEED_CONTACT" }

# Config OTP
OTP_TTL_SECONDS = 10 * 60  # 10 minutes


# ------------ Models ------------
class RequestCodeInput(BaseModel):
    email: str


class RequestCodeResponse(BaseModel):
    message: str
    code: str  # MVP: on renvoie le code à l'écran (comme avant)


class VerifyCodeInput(BaseModel):
    email: str
    code: str


class VerifyCodeResponse(BaseModel):
    token: str


class StatusOutput(BaseModel):
    status_key: Optional[str] = None
    status_label: Optional[str] = None


class StatusUpdateInput(BaseModel):
    status_key: str


# ------------ App + Router ------------
app = FastAPI(title=APP_TITLE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # V1
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")


def _gen_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def _now() -> int:
    return int(time.time())


def _require_session(x_session_token: Optional[str]) -> str:
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Session manquante")
    email = session_store.get(x_session_token)
    if not email:
        raise HTTPException(status_code=401, detail="Session invalide")
    return email


@api_router.get("/")
async def root():
    return {"message": "Je suis là API"}


@api_router.post("/auth/request-code", response_model=RequestCodeResponse)
async def request_code(payload: RequestCodeInput):
    email = payload.email.strip().lower()
    code = _gen_code()
    otp_store[email] = {"code": code, "expires_at": _now() + OTP_TTL_SECONDS}
    # MVP: on retourne le code à l'écran
    return {"message": "Code généré", "code": code}


@api_router.post("/auth/verify-code", response_model=VerifyCodeResponse)
async def verify_code(payload: VerifyCodeInput):
    email = payload.email.strip().lower()
    code = payload.code.strip()

    entry = otp_store.get(email)
    if not entry:
        raise HTTPException(status_code=400, detail="Code introuvable")
    if _now() > entry["expires_at"]:
        raise HTTPException(status_code=400, detail="Code expiré")
    if code != entry["code"]:
        raise HTTPException(status_code=400, detail="Code incorrect")

    token = str(uuid.uuid4())
    session_store[token] = email
    # Initialise statut si absent
    status_store.setdefault(email, None)
    return {"token": token}


@api_router.get("/status", response_model=StatusOutput)
async def get_status(x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    email = _require_session(x_session_token)
    status_key = status_store.get(email)
    if not status_key:
        return {"status_key": None, "status_label": None}
    return {"status_key": status_key, "status_label": ALLOWED_STATUSES.get(status_key)}


@api_router.post("/status", response_model=StatusOutput)
async def set_status(payload: StatusUpdateInput, x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    email = _require_session(x_session_token)
    status_key = payload.status_key.strip()
    if status_key not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Statut invalide")
    status_store[email] = status_key
    return {"status_key": status_key, "status_label": ALLOWED_STATUSES[status_key]}


app.include_router(api_router)
