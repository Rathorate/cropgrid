import os
import secrets
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import Base, SessionLocal, engine, get_db
from .models import Inventory, Order
from .schemas import InventoryCreate, OrderCreate

Base.metadata.create_all(bind=engine)
app = FastAPI(title="CropGrid API", version="0.1.0", description="Development MVP API. Payment and compliance actions are simulations.")
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
