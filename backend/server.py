from fastapi import FastAPI, APIRouter, Depends, HTTPException, Header
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from bson import ObjectId


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# MongoDB connection
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# Create the main app without a prefix
app = FastAPI(title="Je suis là API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Pydantic helpers
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        try:
            return ObjectId(str(v))
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Invalid ObjectId") from exc


# Legacy health models (optionnel mais conservé)
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


# Auth & user models
class RequestCodeInput(BaseModel):
    email: EmailStr


class RequestCodeResponse(BaseModel):
    message: str
    code: str  # NOTE: renvoyé directement dans le MVP pour simplifier


class VerifyCodeInput(BaseModel):
    email: EmailStr
    code: str


class UserPublic(BaseModel):
    id: str
    email: EmailStr


class VerifyCodeResponse(BaseModel):
    token: str
    user: UserPublic


# Status models
# Version minimale : deux statuts explicites seulement
ALLOWED_STATUSES = {
    "OK": "Je suis là",
    "NEED_CONTACT": "Aujourd'hui, c'est différent",
}


class StatusOutput(BaseModel):
    status_key: str
    status_label: str
    updated_at: datetime


class StatusUpdateInput(BaseModel):
    status_key: str


# Dépendance d'authentification
async def get_current_user(x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")):
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Session manquante")

    session = await db.sessions.find_one({"token": x_session_token})
    if not session:
        raise HTTPException(status_code=401, detail="Session invalide")

    user = await db.users.find_one({"_id": session["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")

    return user


# Routes de base (simple santé du service)
@api_router.get("/")
async def root():
    return {"message": "Je suis là API"}


# Point de terminaison de santé hérité (facultatif)
@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):  # type: ignore[valid-type]
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)

    doc = status_obj.model_dump()
    doc["timestamp"] = doc["timestamp"].isoformat()

    _ = await db.status_checks.insert_one(doc)
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)

    for check in status_checks:
        if isinstance(check["timestamp"], str):
            check["timestamp"] = datetime.fromisoformat(check["timestamp"])

    return status_checks


# Auth endpoints
@api_router.post("/auth/request-code", response_model=RequestCodeResponse)
async def request_code(input_data: RequestCodeInput):
    email = input_data.email.lower()

    # Créer ou récupérer l'utilisateur
    user = await db.users.find_one({"email": email})
    now_iso = datetime.now(timezone.utc).isoformat()
    if not user:
        user_doc = {"email": email, "created_at": now_iso, "last_login_at": None}
        result = await db.users.insert_one(user_doc)
        user_id = result.inserted_id
    else:
        user_id = user["_id"]

    # Générer un code simple à 6 chiffres
    raw_code = str(uuid.uuid4().int)[-6:]
    code = raw_code.zfill(6)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    login_code_doc = {
        "user_id": user_id,
        "code": code,
        "expires_at": expires_at.isoformat(),
        "used": False,
    }
    await db.login_codes.insert_one(login_code_doc)

    # MVP : on renvoie le code directement
    return RequestCodeResponse(message="code_generated", code=code)


@api_router.post("/auth/verify-code", response_model=VerifyCodeResponse)
async def verify_code(input_data: VerifyCodeInput):
    email = input_data.email.lower()
    code = input_data.code

    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=400, detail="Utilisateur inconnu")

    # Récupérer le code le plus récent correspondant
    login_code = await db.login_codes.find_one(
        {"user_id": user["_id"], "code": code, "used": False},
        sort=[("expires_at", -1)],
    )
    if not login_code:
        raise HTTPException(status_code=400, detail="Code invalide")

    try:
        expires_at = datetime.fromisoformat(login_code["expires_at"])
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Code expiré")

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Code expiré")

    # Marquer comme utilisé
    await db.login_codes.update_one(
        {"_id": login_code["_id"]}, {"$set": {"used": True}}
    )

    # Créer une session
    token = str(uuid.uuid4())
    session_doc = {
        "user_id": user["_id"],
        "token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.sessions.insert_one(session_doc)

    # Mettre à jour last_login_at
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login_at": datetime.now(timezone.utc).isoformat()}},
    )

    user_public = UserPublic(id=str(user["_id"]), email=user["email"])
    return VerifyCodeResponse(token=token, user=user_public)


# Status endpoints
@api_router.get("/me/status", response_model=Optional[StatusOutput])
async def get_my_status(current_user=Depends(get_current_user)):
    status_doc = await db.statuses.find_one({"user_id": current_user["_id"]})
    if not status_doc:
        return None

    updated_at = (
        datetime.fromisoformat(status_doc["updated_at"])
        if isinstance(status_doc["updated_at"], str)
        else status_doc["updated_at"]
    )

    return StatusOutput(
        status_key=status_doc["status_key"],
        status_label=status_doc["status_label"],
        updated_at=updated_at,
    )


@api_router.post("/me/status", response_model=StatusOutput)
async def update_my_status(input_data: StatusUpdateInput, current_user=Depends(get_current_user)):
    status_key = input_data.status_key
    if status_key not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Statut non autorisé")

    label = ALLOWED_STATUSES[status_key]
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    await db.statuses.update_one(
        {"user_id": current_user["_id"]},
        {
            "$set": {
                "user_id": current_user["_id"],
                "status_key": status_key,
                "status_label": label,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    return StatusOutput(status_key=status_key, status_label=label, updated_at=now)


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
