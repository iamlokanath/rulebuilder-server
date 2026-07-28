from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import get_settings
from app.core.database import get_database
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas.common import (
    GoogleAuthRequest,
    MessageResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def serialize_user(user: dict) -> UserResponse:
    return UserResponse(
        id=user["_id"],
        name=user["name"],
        email=user["email"],
        created_at=user["created_at"],
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(payload: UserCreate) -> UserResponse:
    db = get_database()
    existing = await db.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = {
        "_id": str(uuid4()),
        "name": payload.name.strip(),
        "email": payload.email.lower(),
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc),
        "auth_provider": "password",
    }
    await db.users.insert_one(user)
    return serialize_user(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT access token",
)
async def login(payload: UserLogin) -> TokenResponse:
    db = get_database()
    user = await db.users.find_one({"email": payload.email.lower()})
    if not user or not user.get("password_hash"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(user["_id"], extra={"email": user["email"]})
    return TokenResponse(access_token=token)


@router.post(
    "/google",
    response_model=TokenResponse,
    summary="Login or register with Google ID token",
)
async def google_login(payload: GoogleAuthRequest) -> TokenResponse:
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is not configured",
        )

    try:
        info = id_token.verify_oauth2_token(
            payload.id_token,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        ) from exc

    email = str(info.get("email", "")).lower().strip()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account email is required",
        )

    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        user = {
            "_id": str(uuid4()),
            "name": str(info.get("name") or email.split("@")[0]),
            "email": email,
            "password_hash": None,
            "auth_provider": "google",
            "google_sub": info.get("sub"),
            "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(user)
    else:
        await db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "auth_provider": user.get("auth_provider") or "google",
                    "google_sub": info.get("sub"),
                }
            },
        )

    token = create_access_token(user["_id"], extra={"email": user["email"]})
    return TokenResponse(access_token=token)


@router.get(
    "/health",
    response_model=MessageResponse,
    summary="Auth module health check",
)
async def auth_health() -> MessageResponse:
    return MessageResponse(message="Auth module is healthy")
