"""Email-verified recovery. Never return reset tokens or existing passwords."""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .auth import COOKIE_NAME, get_current_user, hash_password, verify_password
from .database import SessionLocal, get_db
from .models import AuthThrottle, PasswordReset, User, UserSession

router = APIRouter(prefix="/api/v1/auth", tags=["password recovery"])
logger = logging.getLogger(__name__)
RESET_MESSAGE = "If an active account exists for that email, a reset link will be sent. Check your inbox and spam folder."


class ForgotPassword(BaseModel):
    email: str = Field(min_length=6, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ResetPassword(BaseModel):
    token: str = Field(min_length=40, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)
    confirm_password: str = Field(min_length=10, max_length=128)


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)
    confirm_password: str = Field(min_length=10, max_length=128)


def mail_settings():
    key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("PASSWORD_RESET_FROM_EMAIL", "").strip()
    base = os.getenv("APP_PUBLIC_URL", "").strip().rstrip("/")
    url = urlparse(base)
    local = url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}
    if not key or not sender or not url.hostname or (url.scheme != "https" and not local) or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
        raise HTTPException(503, "Email password recovery is not configured. Contact the site owner, or sign in and change your password.")
    return key, sender, base


def check_origin(request):
    origin = request.headers.get("origin")
    allowed = {x.strip().rstrip("/") for x in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")}
    allowed.add(os.getenv("APP_PUBLIC_URL", "").rstrip("/"))
    if origin and origin.rstrip("/") not in allowed:
        raise HTTPException(403, "This request origin is not allowed.")


def throttle(db, scope, subject, limit, seconds):
    now = datetime.now(timezone.utc)
    bucket = int(now.timestamp()) // seconds
    key = hashlib.sha256(f"{scope}:{subject}:{bucket}".encode()).hexdigest()
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise HTTPException(503, "Recovery requires a supported database.")
    stmt = insert(AuthThrottle).values(key=key, attempts=1, expires_at=now + timedelta(seconds=seconds * 2))
    stmt = stmt.on_conflict_do_update(index_elements=[AuthThrottle.key], set_={"attempts": AuthThrottle.attempts + 1}).returning(AuthThrottle.attempts)
    attempts = db.scalar(stmt)
    db.execute(delete(AuthThrottle).where(AuthThrottle.expires_at < now))
    db.commit()
    if attempts > limit:
        raise HTTPException(429, "Too many requests. Please wait before trying again.", headers={"Retry-After": str(seconds - int(now.timestamp()) % seconds)})


def send_email(recipient, subject, text):
    key, sender, _ = mail_settings()
    with httpx.Client(timeout=15) as client:
        response = client.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {key}"}, json={"from": sender, "to": [recipient], "subject": subject, "text": text})
        response.raise_for_status()


def deliver_reset(email):
    # Background work keeps account existence/email provider timing out of the response.
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if not user:
            return
        token = secrets.token_urlsafe(32)
        row = PasswordReset(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(minutes=20))
        db.add(row)
        db.commit()
        try:
            _, _, base = mail_settings()
            # Fragment keeps the raw token out of HTTP request URLs and access logs.
            link = base + "/account#" + urlencode({"reset_token": token})
            send_email(user.email, "Reset your CropGrid password", f"Use this link to choose a new password:\n{link}\n\nThis link expires in 20 minutes and can be used once. If you did not request it, ignore this email. Your current password has not changed.")
        except Exception:
            row.used_at = datetime.now(timezone.utc)
            db.commit()
            # Do not log provider bodies, recipient addresses, URLs or tokens.
            logger.warning("Password recovery email delivery failed; check provider configuration and delivery logs.")


def notify_changed(email):
    try:
        send_email(email, "Your CropGrid password was changed", "Your CropGrid password was changed and existing sessions were signed out. If you did not make this change, request a new reset link and contact support.")
    except Exception:
        logger.warning("Password-change notification delivery failed.")


def validate_new_password(payload):
    if payload.new_password != payload.confirm_password:
        raise HTTPException(422, "The new passwords do not match.")
    if not payload.new_password.strip():
        raise HTTPException(422, "Choose a password containing more than spaces.")


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: ForgotPassword, request: Request, response: Response, background: BackgroundTasks, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    check_origin(request)
    email = payload.email.strip().lower()
    host = request.client.host if request.client else "unknown"
    throttle(db, "forgot-ip", host, 30, 3600)
    throttle(db, "forgot-email", email, 3, 3600)
    throttle(db, "forgot-global", "all", 100, 3600)
    mail_settings()
    background.add_task(deliver_reset, email)
    return {"message": RESET_MESSAGE}


@router.post("/reset-password")
def reset_password(payload: ResetPassword, request: Request, response: Response, background: BackgroundTasks, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    check_origin(request)
    throttle(db, "reset-ip", request.client.host if request.client else "unknown", 20, 600)
    validate_new_password(payload)
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(payload.token.encode()).hexdigest()
    row = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == digest))
    if not row:
        raise HTTPException(400, "This reset link is invalid or expired. Request a new one.")
    # Serialize recovery/change operations per user on PostgreSQL.
    user = db.scalar(select(User).where(User.id == row.user_id).with_for_update())
    if not user or not user.is_active:
        raise HTTPException(400, "This reset link is invalid or expired. Request a new one.")
    claimed = db.execute(update(PasswordReset).where(PasswordReset.id == row.id, PasswordReset.used_at.is_(None), PasswordReset.expires_at > now).values(used_at=now).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, "This reset link is invalid or expired. Request a new one.")
    user.password_hash = hash_password(payload.new_password)
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(used_at=now))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}, samesite="lax")
    background.add_task(notify_changed, user.email)
    return {"message": "Password updated. Sign in with your new password."}


@router.post("/change-password")
def change_password(payload: ChangePassword, request: Request, response: Response, background: BackgroundTasks, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    check_origin(request)
    throttle(db, "change-user", str(current.id), 10, 600)
    validate_new_password(payload)
    user = db.scalar(select(User).where(User.id == current.id).with_for_update().execution_options(populate_existing=True))
    # A concurrent password change invalidates this session's authorization.
    raw = request.cookies.get(COOKIE_NAME, "")
    valid_session = db.scalar(select(UserSession.id).where(UserSession.user_id == user.id, UserSession.token_hash == hashlib.sha256(raw.encode()).hexdigest(), UserSession.expires_at > datetime.now(timezone.utc)))
    if not valid_session:
        raise HTTPException(401, "Please sign in again.")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Your current password is incorrect.")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(422, "Choose a password different from your current password.")
    user.password_hash = hash_password(payload.new_password)
    now = datetime.now(timezone.utc)
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(used_at=now))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}, samesite="lax")
    if os.getenv("RESEND_API_KEY", "").strip():
        background.add_task(notify_changed, user.email)
    return {"message": "Password updated. Sign in again with your new password."}
