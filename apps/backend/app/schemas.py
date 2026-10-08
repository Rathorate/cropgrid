from pydantic import BaseModel, ConfigDict, Field

class InventoryCreate(BaseModel):
    supplier_name: str = Field(default="CropGrid Supplier", min_length=2, max_length=120)
    crop_name: str = Field(min_length=2, max_length=80)
    quantity_tons: float = Field(gt=0, le=100000)
    moisture_percentage: float = Field(default=0, ge=0, le=100)
    location_state: str = Field(min_length=2, max_length=80)
    asking_price_per_ton_ngn: float = Field(gt=0, le=10_000_000_000)
    quality_grade: str = Field(default="GRADE_B", pattern="^GRADE_[ABC]$")
    is_export_ready: bool = False
    description: str = Field(default="", max_length=1000)

class InventoryOut(InventoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: str | None = None

class OrderCreate(BaseModel):
    inventory_id: int
    quantity_tons: float = Field(gt=0)
    buyer_name: str = Field(default="Demo Buyer", min_length=2, max_length=120)

class OrderOut(BaseModel):
    id: int
    inventory_id: int
    buyer_name: str
    quantity_tons: float
    total_amount_ngn: float
    status: str
    reference: str
