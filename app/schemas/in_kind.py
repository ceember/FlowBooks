from datetime import date as dt_date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator
from app.schemas.common import StrictModel


class InKindLineCreate(StrictModel):
    description: str
    quantity: Decimal = Decimal("1")
    fair_value: Decimal = Decimal("0")  # per unit, the donor's estimate
    debit_account_id: int  # the asset or expense the gift is
    credit_account_id: Optional[int] = None  # default: In-Kind Contributions
    class_id: Optional[int] = None
    job_id: Optional[int] = None

    @field_validator("description")
    @classmethod
    def _desc(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Describe the property given")
        return v

    @model_validator(mode="after")
    def _amounts(self):
        if self.quantity <= 0 or self.fair_value < 0:
            raise ValueError(
                "Quantity must be positive and fair value cannot be negative"
            )
        return self


class InKindLineResponse(BaseModel):
    id: int
    description: str
    quantity: Decimal
    fair_value: Decimal
    amount: Decimal
    debit_account_id: int
    debit_account_name: Optional[str] = None
    credit_account_id: int
    credit_account_name: Optional[str] = None
    class_id: Optional[int] = None
    job_id: Optional[int] = None
    line_order: int = 0
    model_config = {"from_attributes": True}


class InKindGiftCreate(StrictModel):
    customer_id: int
    date: dt_date
    memo: Optional[str] = None
    class_id: Optional[int] = None
    job_id: Optional[int] = None
    lines: list[InKindLineCreate]

    @field_validator("lines")
    @classmethod
    def _lines(cls, v):
        if not v:
            raise ValueError("An in-kind gift needs at least one line")
        return v


class InKindGiftResponse(BaseModel):
    id: int
    number: str
    customer_id: int
    customer_name: Optional[str] = None
    date: dt_date
    memo: Optional[str] = None
    status: str
    transaction_id: Optional[int] = None
    total: Decimal
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    job_id: Optional[int] = None
    lines: list[InKindLineResponse] = []
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}
