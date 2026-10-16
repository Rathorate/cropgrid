"""Listing media, private conversations and delivery tracking.

Delivery records never assert that money is held in escrow or paid to a seller.
"""
import io
import hashlib
import re
import warnings
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from PIL import Image, ImageOps, UnidentifiedImageError
from .auth import get_current_user, require_roles
from .database import get_db
from .models import ChatMessage, Conversation, Fulfillment, Inventory, ListingMedia, PaymentTransaction, User

router = APIRouter(prefix="/api/v1")
Image.MAX_IMAGE_PIXELS = 20_000_000

def media_summary(row):
    return {"id": row.id, "kind": row.kind, "url": f"/api/v1/media/{row.id}"}

def listing_response(row, db):
    result = jsonable_encoder(row)
    # Listing queries must never fetch large media blobs into their JSON response.
    media = db.execute(select(ListingMedia.id, ListingMedia.kind).where(ListingMedia.inventory_id == row.id).order_by(ListingMedia.id)).all()
    result["media"] = [media_summary(item) for item in media]
    return result

@router.post("/inventories/{inventory_id}/media", status_code=201)
async def upload_media(inventory_id: int, file: UploadFile = File(...), seller: User = Depends(require_roles("SELLER", "ADMIN")), db: Session = Depends(get_db)):
    listing = db.get(Inventory, inventory_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.seller_user_id != seller.id:
        raise HTTPException(403, "Only the listing owner can upload media.")
    # Read with a hard bound before storing. User filenames are never used as paths.
    data = await file.read(30_000_001)
    if not data:
        raise HTTPException(422, "The upload is empty.")
    if len(data) > 30_000_000:
        raise HTTPException(413, "Videos must be no larger than 30 MB.")
    if (file.content_type or "").startswith("image/"):
        if len(data) > 8_000_000:
            raise HTTPException(413, "Photos must be no larger than 8 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP"}:
                        raise ValueError("Unsupported photo format")
                    image.load()
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((2400, 2400))
                    output = io.BytesIO()
                    image.convert("RGB").save(output, format="JPEG", quality=88)
                    data = output.getvalue()
            kind, mime = "image", "image/jpeg"
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise HTTPException(415, "Choose a valid JPEG, PNG or WebP photo, under 20 megapixels.") from exc
    elif file.content_type == "video/mp4" and data[4:8] == b"ftyp":
        kind, mime = "video", "video/mp4"
    elif file.content_type == "video/webm" and data[:4] == b"\x1aE\xdf\xa3":
        kind, mime = "video", "video/webm"
    else:
        raise HTTPException(415, "Choose JPEG, PNG, WebP, MP4 or WebM media. Convert other formats first.")
    listing = db.scalar(select(Inventory).where(Inventory.id == inventory_id).with_for_update())
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.seller_user_id != seller.id:
        raise HTTPException(403, "Only the listing owner can upload media.")
    content_hash = hashlib.sha256(data).hexdigest()
    duplicate_query = select(ListingMedia.id, ListingMedia.kind).where(ListingMedia.inventory_id == inventory_id, ListingMedia.content_hash == content_hash)
    duplicate = db.execute(duplicate_query).first()
    if duplicate:
        return media_summary(duplicate)
    if db.scalar(select(func.count()).select_from(ListingMedia).where(ListingMedia.inventory_id == inventory_id)) >= 6:
        raise HTTPException(422, "Each listing can have at most six photos and videos.")
    row = ListingMedia(inventory_id=inventory_id, kind=kind, mime_type=mime, content=data, content_hash=content_hash)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.execute(duplicate_query).first()
        if duplicate:
            return media_summary(duplicate)
        raise
    return media_summary(row)

@router.get("/media/{media_id}")
def read_media(media_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.get(ListingMedia, media_id)
    if not row:
        raise HTTPException(404, "Media not found")
    data = row.content
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=86400", "Accept-Ranges": "bytes"}
    requested = request.headers.get("range")
    if requested:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
        if not match or not any(match.groups()):
            return Response(status_code=416, headers={"Content-Range": f"bytes */{len(data)}"})
        start, end = match.groups()
        if start:
            start, end = int(start), min(int(end), len(data) - 1) if end else len(data) - 1
        else:
            start, end = max(0, len(data) - int(end)), len(data) - 1
        if start > end or start >= len(data):
            return Response(status_code=416, headers={"Content-Range": f"bytes */{len(data)}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
        return Response(data[start:end + 1], status_code=206, media_type=row.mime_type, headers=headers)
    return Response(data, media_type=row.mime_type, headers=headers)

class StartChat(BaseModel):
    inventory_id: int = Field(gt=0)

class MessageInput(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

def private_thread(thread_id, user, db):
    thread = db.get(Conversation, thread_id)
    if not thread or (user.role != "ADMIN" and user.id not in {thread.buyer_user_id, thread.seller_user_id}):
        raise HTTPException(404, "Conversation not found")
    return thread

@router.post("/conversations", status_code=201)
def start_chat(payload: StartChat, buyer: User = Depends(require_roles("BUYER")), db: Session = Depends(get_db)):
    listing = db.get(Inventory, payload.inventory_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    if not listing.seller_user_id:
        raise HTTPException(409, "This sample listing has no seller account. Choose a real seller listing.")
    if listing.seller_user_id == buyer.id:
        raise HTTPException(422, "You cannot start a conversation with yourself.")
    statement = select(Conversation).where(Conversation.inventory_id == listing.id, Conversation.buyer_user_id == buyer.id)
    thread = db.scalar(statement)
    if not thread:
        thread = Conversation(inventory_id=listing.id, buyer_user_id=buyer.id, seller_user_id=listing.seller_user_id)
        db.add(thread)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            thread = db.scalar(statement)
    return {"id": thread.id}

@router.get("/conversations")
def conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Conversation, Inventory).join(Inventory, Conversation.inventory_id == Inventory.id)
    # Admin access for support is explicit, never available to other accounts.
    if user.role != "ADMIN":
        stmt = stmt.where((Conversation.buyer_user_id == user.id) | (Conversation.seller_user_id == user.id))
    return [{"id": thread.id, "crop_name": listing.crop_name,
             "buyer_name": db.get(User, thread.buyer_user_id).full_name,
             "seller_name": db.get(User, thread.seller_user_id).full_name}
            for thread, listing in db.execute(stmt.order_by(Conversation.id.desc()).limit(100))]

@router.get("/conversations/{thread_id}/messages")
def messages(thread_id: int, after_id: int = Query(0, ge=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    private_thread(thread_id, user, db)
    rows = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == thread_id, ChatMessage.id > after_id).order_by(ChatMessage.id).limit(100)).all()
    return [{"id": row.id, "body": row.body, "mine": row.sender_user_id == user.id,
             "sender_name": db.get(User, row.sender_user_id).full_name, "created_at": row.created_at.isoformat()} for row in rows]

@router.post("/conversations/{thread_id}/messages", status_code=201)
def send_message(thread_id: int, payload: MessageInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    private_thread(thread_id, user, db)
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, "Enter a message.")
    count = db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.sender_user_id == user.id, ChatMessage.created_at >= datetime.now(timezone.utc) - timedelta(minutes=1)))
    if count >= 30:
        raise HTTPException(429, "Please wait a minute before sending more messages.")
    row = ChatMessage(conversation_id=thread_id, sender_user_id=user.id, body=body)
    db.add(row)
    db.commit()
    return {"id": row.id}

class DeliveryAction(BaseModel):
    action: str = Field(pattern="^(DISPATCH|CONFIRM_RECEIPT|DISPUTE)$")
    details: str = Field(default="", max_length=1000)

@router.post("/orders/{reference}/delivery")
def delivery_action(reference: str, payload: DeliveryAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.scalar(select(PaymentTransaction).where(PaymentTransaction.reference == reference).with_for_update())
    if not payment:
        raise HTTPException(404, "Order not found")
    listing = db.get(Inventory, payment.inventory_id)
    if user.id not in {payment.buyer_user_id, listing.seller_user_id}:
        raise HTTPException(404, "Order not found")
    if payment.status != "SUCCESS":
        raise HTTPException(409, "Delivery updates require a verified successful payment.")
    row = db.get(Fulfillment, payment.id)
    if not row:
        row = Fulfillment(payment_id=payment.id, status="AWAITING_DISPATCH")
        db.add(row)
    if payload.action == "DISPATCH":
        if user.id != listing.seller_user_id:
            raise HTTPException(403, "Only the seller can confirm dispatch.")
        if row.status != "AWAITING_DISPATCH":
            raise HTTPException(409, "This order cannot be dispatched in its current state.")
        if not payload.details.strip():
            raise HTTPException(422, "Add delivery or tracking information.")
        row.status, row.tracking_details = "DISPATCHED", payload.details.strip()[:500]
    elif payload.action == "CONFIRM_RECEIPT":
        if user.id != payment.buyer_user_id:
            raise HTTPException(403, "Only the buyer can confirm receipt.")
        if row.status != "DISPATCHED":
            raise HTTPException(409, "Receipt can only be confirmed after dispatch, with no open dispute.")
        row.status = "RECEIVED"
    else:
        if row.status not in {"AWAITING_DISPATCH", "DISPATCHED"}:
            raise HTTPException(409, "This delivery cannot be disputed in its current state.")
        if not payload.details.strip():
            raise HTTPException(422, "Describe the delivery problem.")
        row.status, row.dispute_reason = "DISPUTED", payload.details.strip()
    db.commit()
    return {"status": row.status, "funds_released": False, "message": "Delivery updated. No seller payout was initiated."}

@router.post("/orders/{reference}/release")
def release_disabled(reference: str, _: User = Depends(require_roles("ADMIN"))):
    raise HTTPException(409, "Fund release is unavailable. An approved payment holding and payout provider must be integrated first.")
