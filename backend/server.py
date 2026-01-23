from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta, timezone
import os
import random
import string
import uuid
import smtplib
from email.message import EmailMessage

# =========================
# ENV
# =========================
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
MVP_MODE = os.getenv("MVP_MODE", "true").lower() == "true"
OTP_COOLDOWN_SECONDS = int(os.getenv("OTP_COOLDOWN_SECONDS", "60"))

# SMTP (utilisé seulement si MVP_MODE == false)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "")

# =========================
# Mongo
# =========================
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
otp_codes = db.otp_codes
sessions = db.sessions

# =========================
# App
# =========================
app = FastAPI(title="Je suis là API", version="0.1.0")
api = APIRouter(prefix="/api")

# =========================
# Models
# =========================
class RequestCodeInput(BaseModel):
    email: EmailStr

class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str

# =========================
# Utils
# =========================
def now_utc():
    return datetime.now(timezone.utc)

def gen_code():
    return "".join(random.choices(string.digits, k=6))

def gen_token():
    return str(uuid.uuid4())

def send_otp_email(to_email: str, code: str):
    """
    Envoi du code par email (mode public).
    Utilise SMTP standard. Ne s'exécute que si MVP_MODE == false.
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and FROM_EMAIL):
        raise RuntimeError("SMTP env vars missing (SMTP_HOST/SMTP_USER/SMTP_PASS/FROM_EMAIL)")

    msg = EmailMessage()
    msg["Subject"] = "Je suis là — votre code de connexion"
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email

    # Texte simple, neutre, sans marketing, conforme (pas de promesse)
    msg.set_content(
        f"Bonjour,\n\n"
        f"Voici votre code de connexion Je suis là : {code}\n"
        f"Ce code expire dans 5 minutes.\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer ce message.\n\n"
        f"— Je suis là\n"
    )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

# =========================
# Routes
# =========================
@api.get("/")
async def root():
    return {"message": "Je suis là API"}

@api.post("/auth/request-code")
async def request_code(payload: RequestCodeInput):
    email = payload.email.strip().lower()
    now = now_utc()

    # Cooldown anti-spam
    last = await otp_codes.find_one({"email": email}, sort=[("created_at", -1)])
    if last and (now - last["created_at"]).total_seconds() < OTP_COOLDOWN_SECONDS:
        raise HTTPException(status_code=429, detail="Veuillez attendre avant de redemander un code")

    code = gen_code()

    await otp_codes.insert_one({
        "email": email,
        "code": code,
        "created_at": now,
        "expires_at": now + timedelta(minutes=5),
        "used": False,
    })

    # Mode MVP : on renvoie le code (test uniquement)
    if MVP_MODE:
        return {"message": "Code généré (mode test)", "code": code}

    # Mode public : on envoie par email, et on ne renvoie jamais le code
    try:
        send_otp_email(email, code)
    except Exception as e:
        # Message volontairement neutre (ne pas exposer les secrets)
        raise HTTPException(status_code=500, detail="Envoi du code impossible (configuration email)")

    return {"message": "Code envoyé"}

@api.post("/auth/verify-code")
async def verify_code(payload: VerifyCodeInput):
    email = payload.email.strip().lower()
    code = payload.code.strip()
    now = now_utc()

    record = await otp_codes.find_one({
        "email": email,
        "code": code,
        "used": False,
        "expires_at": {"$gt": now}
    })

    if not record:
        raise HTTPException(status_code=400, detail="Code incorrect")

    # one-shot
    await otp_codes.update_one({"_id": record["_id"]}, {"$set": {"used": True}})

    token = gen_token()
    await sessions.insert_one({
        "token": token,
        "email": email,
        "created_at": now,
        "expires_at": now + timedelta(days=30),
    })

    return {"token": token}

app.include_router(api)
