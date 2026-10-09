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

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventories.id"), index=True)
    buyer_name: Mapped[str] = mapped_column(String(120))
    buyer_email: Mapped[str] = mapped_column(String(254), index=True)
    quantity_tons: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="NGN")
    amount_subunit: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    authorization_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
