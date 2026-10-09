import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal, get_db
from .models import User, UserSession
from .schemas import LoginCreate, RegisterCreate

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
COOKIE_NAME = "cropgrid_session"
SESSION_DAYS = 7
PASSWORD_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)).hex()
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False


def user_payload(user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role}


def issue_session(user: User, response: Response, db: Session) -> None:
    raw_token = secrets.token_urlsafe(32)
    expiry = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db.add(UserSession(user_id=user.id, token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), expires_at=expiry))
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        raw_token,
        httponly=True,
        secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw_token = request.cookies.get(COOKIE_NAME)
    if not raw_token:
        raise HTTPException(401, "Please sign in to continue.")
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
    if not session:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    expiry = session.expires_at.replace(tzinfo=timezone.utc) if session.expires_at.tzinfo is None else session.expires_at
    if expiry <= datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "This account is unavailable.")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Your account role cannot perform this action.")
        return user
    return dependency


@router.post("/register", status_code=201)
def register(payload: RegisterCreate, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account with that email already exists.")
    user = User(full_name=payload.full_name.strip(), email=email, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    issue_session(user, response, db)
    return user_payload(user)


@router.post("/login")
def login(payload: LoginCreate, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    issue_session(user, response, db)
    return user_payload(user)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_payload(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_token = request.cookies.get(COOKIE_NAME)
    if raw_token:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")
    response.status_code = 204
    return response


def bootstrap_admin() -> None:
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email and not password:
        return
    if not email or len(password) < 16:
        raise RuntimeError("Set both ADMIN_EMAIL and an ADMIN_PASSWORD of at least 16 characters to provision the admin account.")
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            if existing.role != "ADMIN":
                raise RuntimeError("ADMIN_EMAIL is already registered as a non-admin account; use a separate admin email.")
            return
        db.add(User(full_name="CropGrid Administrator", email=email, password_hash=hash_password(password), role="ADMIN"))
        db.commit()
