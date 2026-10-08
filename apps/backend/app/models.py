from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class Inventory(Base):
    __tablename__ = "inventories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_name: Mapped[str] = mapped_column(String(120), default="CropGrid Supplier")
    crop_name: Mapped[str] = mapped_column(String(80), index=True)
    quantity_tons: Mapped[float] = mapped_column(Float)
    moisture_percentage: Mapped[float] = mapped_column(Float, default=0)
    location_state: Mapped[str] = mapped_column(String(80), index=True)
    asking_price_per_ton_ngn: Mapped[float] = mapped_column(Float)
    quality_grade: Mapped[str] = mapped_column(String(12), default="GRADE_B")
    is_export_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventories.id"))
    buyer_name: Mapped[str] = mapped_column(String(120), default="Demo Buyer")
    quantity_tons: Mapped[float] = mapped_column(Float)
    total_amount_ngn: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
