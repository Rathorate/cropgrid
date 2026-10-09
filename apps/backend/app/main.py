import os
import secrets
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
import httpx
from .database import Base, SessionLocal, engine, get_db
from .models import Inventory, Order, PaymentTransaction
from .schemas import InventoryCreate, OrderCreate, PaymentInitialize

Base.metadata.create_all(bind=engine)
app = FastAPI(title="CropGrid API", version="0.2.0", description="CropGrid MVP API. Paystack checkout is available when configured; escrow and export compliance are not provided.")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

def seed_demo_inventory():
    """Keep the local demo usable while still permitting an empty production database."""
    if os.getenv("CROPGRID_SEED_DEMO", "true").lower() not in {"1", "true", "yes"}:
        return
    with SessionLocal() as db:
        if db.scalar(select(Inventory.id).limit(1)) is not None:
            return
        samples = [
            ("Northern Harvest Co.", "Ginger", 120, 8.2, "Kaduna", 1850000, "GRADE_A", True, "Cleaned and sun-dried. Ready for export."),
            ("Greenfield Aggregators", "Cashew nuts", 85, 7.4, "Kogi", 2420000, "GRADE_A", True, "Raw cashew nuts with consistent kernel outturn."),
            ("Savanna Produce Ltd.", "Sesame seed", 240, 6.8, "Niger", 1960000, "GRADE_B", True, "Natural white sesame, cleaned and bagged."),
            ("Oke-Ogun Farmers Union", "Cocoa beans", 64, 7.1, "Ondo", 3180000, "GRADE_A", False, "Fermented, dried cocoa beans from this season."),
            ("Benue Grain Partners", "Soybeans", 310, 9.5, "Benue", 875000, "GRADE_B", False, "Yellow soybeans, bulk supply available."),
            ("Arewa Botanicals", "Hibiscus flower", 48, 8.0, "Kano", 1320000, "GRADE_A", True, "Deep red dried hibiscus calyces, export packed."),
        ]
        db.add_all([Inventory(supplier_name=a, crop_name=b, quantity_tons=c, moisture_percentage=d, location_state=e,
                              asking_price_per_ton_ngn=f, quality_grade=g, is_export_ready=h, description=i)
                    for a, b, c, d, e, f, g, h, i in samples])
        db.commit()

seed_demo_inventory()

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "cropgrid-api", "mode": "development-mvp"}

@app.get("/api/v1/inventories")
def list_inventories(q: str = Query(default="", max_length=100), crop: str = Query(default="", max_length=80), db: Session = Depends(get_db)):
    stmt = select(Inventory).order_by(Inventory.created_at.desc())
    if q:
        stmt = stmt.where((Inventory.crop_name.ilike(f"%{q}%")) | (Inventory.location_state.ilike(f"%{q}%")))
    if crop:
        stmt = stmt.where(Inventory.crop_name.ilike(f"%{crop}%"))
    return db.scalars(stmt.limit(100)).all()

@app.post("/api/v1/inventories", status_code=201)
def create_inventory(payload: InventoryCreate, db: Session = Depends(get_db)):
    row = Inventory(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@app.post("/api/v1/orders/escrow-initiate", status_code=201)
def initiate_demo_order(payload: OrderCreate, db: Session = Depends(get_db)):
    inventory = db.get(Inventory, payload.inventory_id)
    if not inventory:
        raise HTTPException(404, "Listing not found")
    if payload.quantity_tons > inventory.quantity_tons:
        raise HTTPException(422, "Requested quantity exceeds available inventory")
    order = Order(inventory_id=inventory.id, buyer_name=payload.buyer_name, quantity_tons=payload.quantity_tons,
                  total_amount_ngn=round(payload.quantity_tons * inventory.asking_price_per_ton_ngn, 2),
                  status="DEMO_PENDING", reference="CG-DEMO-" + secrets.token_hex(5).upper())
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"demo_only": True, "message": "No payment was initiated or collected.", "order": order}

@app.get("/api/v1/export/form-nxp/{order_id}")
def export_document_draft(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    inventory = db.get(Inventory, order.inventory_id)
    return {"document_type": "FORM_NXP_DRAFT_CHECKLIST", "official_document": False,
            "notice": "Draft planning checklist only. Submit through the applicable official Nigerian channels.",
            "order_reference": order.reference, "commodity": inventory.crop_name if inventory else None,
            "exporter": "To be verified", "destination_port": "To be supplied", "hs_code": "Requires customs verification",
            "fob_value_ngn": order.total_amount_ngn, "required_follow_up": ["Verify exporter registration", "Confirm HS code with licensed customs professional", "Obtain applicable phytosanitary inspection", "Complete official CBN Form NXP process"]}

async def paystack_request(path: str, *, method: str = "GET", payload: dict | None = None):
    secret = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    if not secret:
        raise HTTPException(503, "Payments are not configured. Add a Paystack test secret key to the backend environment.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(method, f"https://api.paystack.co{path}", headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}, json=payload)
    except httpx.RequestError as exc:
        raise HTTPException(502, "Could not connect to the payment provider. Please retry.") from exc
    if response.status_code >= 400:
        raise HTTPException(502, "The payment provider could not process this request.")
    result = response.json()
    if not result.get("status"):
        raise HTTPException(502, "The payment provider rejected this request.")
    return result.get("data", {})

@app.post("/api/v1/payments/initialize", status_code=201)
async def initialize_payment(payload: PaymentInitialize, db: Session = Depends(get_db)):
    if not os.getenv("PAYSTACK_SECRET_KEY", "").strip():
        raise HTTPException(503, "Payments are not configured. Add a Paystack test secret key to the backend environment.")
    inventory = db.scalar(select(Inventory).where(Inventory.id == payload.inventory_id).with_for_update())
    if not inventory:
        raise HTTPException(404, "Listing not found")
    now = datetime.now(timezone.utc)
    pending_payments = db.scalars(select(PaymentTransaction).where(PaymentTransaction.status == "PENDING")).all()
    active_reserved = 0.0
    expired_any = False
    for pending in pending_payments:
        created = pending.created_at.replace(tzinfo=timezone.utc) if pending.created_at.tzinfo is None else pending.created_at.astimezone(timezone.utc)
        if created < now - timedelta(minutes=20):
            pending.status = "EXPIRED"
            expired_any = True
        elif pending.inventory_id == inventory.id:
            active_reserved += pending.quantity_tons
    db.flush()
    if expired_any:
        db.commit()
        inventory = db.scalar(select(Inventory).where(Inventory.id == payload.inventory_id).with_for_update())
    if payload.quantity_tons > inventory.quantity_tons - active_reserved:
        raise HTTPException(422, "Requested quantity exceeds available inventory")
    total_ngn = (Decimal(str(inventory.asking_price_per_ton_ngn)) * Decimal(str(payload.quantity_tons))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    amount_subunit = int(total_ngn * 100)
    if amount_subunit < 5000:
        raise HTTPException(422, "Paystack NGN transactions must be at least ₦50")
    reference = "CG-" + uuid.uuid4().hex
    payment = PaymentTransaction(inventory_id=inventory.id, buyer_name=payload.buyer_name.strip(), buyer_email=payload.buyer_email.lower(),
        quantity_tons=payload.quantity_tons, currency="NGN", amount_subunit=amount_subunit, status="PENDING", reference=reference)
    db.add(payment)
    db.commit()
    callback_url = os.getenv("PAYSTACK_CALLBACK_URL", "http://localhost:3000/payment/return")
    try:
        checkout = await paystack_request("/transaction/initialize", method="POST", payload={
            "email": payment.buyer_email, "amount": amount_subunit, "currency": "NGN", "reference": reference,
            "callback_url": callback_url, "metadata": {"inventory_id": inventory.id, "quantity_tons": payload.quantity_tons},
        })
    except HTTPException:
        payment.status = "FAILED"
        db.commit()
        raise
    authorization_url = checkout.get("authorization_url")
    if not authorization_url or not authorization_url.startswith("https://checkout.paystack.com/"):
        payment.status = "FAILED"
        db.commit()
        raise HTTPException(502, "The payment provider returned an invalid checkout URL.")
    payment.authorization_url = authorization_url
    db.commit()
    return {"reference": reference, "authorization_url": authorization_url, "currency": "NGN", "amount": str(total_ngn), "status": payment.status}

async def verify_and_record_payment(reference: str, db: Session):
    payment = db.scalar(select(PaymentTransaction).where(PaymentTransaction.reference == reference).with_for_update())
    if not payment:
        raise HTTPException(404, "Payment reference not found")
    if payment.status in {"SUCCESS", "PAID_REVIEW", "FAILED"}:
        return payment
    provider = await paystack_request(f"/transaction/verify/{reference}")
    try:
        provider_amount = int(provider.get("amount", -1))
    except (TypeError, ValueError):
        provider_amount = -1
    provider_succeeded = provider.get("status") == "success"
    verified = (provider.get("reference") == payment.reference
        and provider_succeeded
        and provider.get("currency") == payment.currency
        and provider_amount == payment.amount_subunit)
    if provider_succeeded:
        if not verified or payment.status == "EXPIRED":
            payment.status = "PAID_REVIEW"
            payment.provider_transaction_id = str(provider.get("id", "")) or None
            db.commit()
            return payment
        inventory = db.scalar(select(Inventory).where(Inventory.id == payment.inventory_id).with_for_update())
        if inventory and inventory.quantity_tons >= payment.quantity_tons:
            inventory.quantity_tons = round(inventory.quantity_tons - payment.quantity_tons, 4)
            payment.status = "SUCCESS"
        else:
            # Provider has captured a valid payment but the stock is gone. Do
            # not mark it as fulfilled; it needs a manual refund/reconciliation.
            payment.status = "PAID_REVIEW"
        payment.provider_transaction_id = str(provider.get("id", "")) or None
        db.commit()
    elif provider.get("status") in {"failed", "abandoned"}:
        payment.status = "FAILED"
        payment.provider_transaction_id = str(provider.get("id", "")) or None
        db.commit()
    return payment

@app.get("/api/v1/payments/verify/{reference}")
async def verify_payment(reference: str, db: Session = Depends(get_db)):
    payment = await verify_and_record_payment(reference, db)
    return {"reference": payment.reference, "status": payment.status, "currency": payment.currency,
        "amount": str(Decimal(payment.amount_subunit) / 100), "quantity_tons": payment.quantity_tons,
        "message": "Payment confirmed." if payment.status == "SUCCESS" else "Payment needs manual review." if payment.status == "PAID_REVIEW" else "Payment is still pending." if payment.status == "PENDING" else "Payment was not successful."}

@app.post("/api/v1/payments/webhook")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    secret = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    if not secret:
        raise HTTPException(503, "Payment webhook is not configured")
    raw = await request.body()
    supplied = request.headers.get("x-paystack-signature", "")
    expected = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid payment webhook signature")
    try:
        event = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Malformed webhook payload") from exc
    if event.get("event") == "charge.success":
        reference = str((event.get("data") or {}).get("reference", ""))
        if reference:
            await verify_and_record_payment(reference, db)
    return {"received": True}

@app.post("/api/v1/ai/parse-audio")
async def parse_audio(file: UploadFile = File(...)):
    allowed = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/webm", "audio/ogg", "audio/mpga"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Upload an MP3, MP4, WAV, WebM, or OGG audio file")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(503, "Voice parsing is not configured. Add OPENAI_API_KEY to enable this optional AI feature.")
    data = await file.read(20_000_001)
    if len(data) > 20_000_000:
        raise HTTPException(413, "Audio file exceeds 20 MB")
    if not data:
        raise HTTPException(422, "Audio file is empty")
    try:
        from openai import OpenAI
        client = OpenAI()
        transcript = client.audio.transcriptions.create(model="whisper-1", file=(file.filename or "voice.webm", data, file.content_type)).text
        parsed = client.chat.completions.create(model=os.getenv("OPENAI_LISTING_MODEL", "gpt-4o-mini"), response_format={"type": "json_object"},
            messages=[{"role":"system","content":"Extract a crop marketplace listing from the transcription. Return JSON keys crop_name, quantity_tons, location_state, asking_price_per_ton_ngn, moisture_percentage, description. Use null where uncertain. Never invent values."}, {"role":"user","content":transcript}])
        import json
        return {"transcript": transcript, "draft": json.loads(parsed.choices[0].message.content or "{}"), "requires_human_review": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "AI transcription is temporarily unavailable") from exc
