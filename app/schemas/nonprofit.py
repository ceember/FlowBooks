from datetime import date as dt_date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from app.schemas.common import StrictModel

from app.models.classes import FUNCTIONS
from app.models.nonprofit import ALLOCATION_BASES


def _function_ok(v):
    if v in (None, ""):
        return None
    if v not in FUNCTIONS:
        raise ValueError(f"function must be one of: {', '.join(FUNCTIONS)}")
    return v


# ── Release from restriction ─────────────────────────────────────────────


class ReleaseCreate(StrictModel):
    date: dt_date
    class_id: int
    # None = release what the fund spent in the period (the suggestion)
    amount: Optional[Decimal] = None
    period_start: Optional[dt_date] = None
    period_end: Optional[dt_date] = None
    memo: Optional[str] = None


class ReleaseResponse(BaseModel):
    id: int
    number: str
    date: dt_date
    class_id: int
    class_name: str = ""
    amount: Decimal
    period_start: Optional[dt_date] = None
    period_end: Optional[dt_date] = None
    memo: Optional[str] = None
    status: str
    transaction_id: Optional[int] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class ReleaseSuggestion(BaseModel):
    class_id: int
    class_name: str
    period_start: dt_date
    period_end: dt_date
    expenses: Decimal
    released: Decimal
    suggested: Decimal


# ── Allocation rules ─────────────────────────────────────────────────────


class AllocationTargetIn(StrictModel):
    class_id: Optional[int] = None
    function: Optional[str] = None
    job_id: Optional[int] = None
    weight: Decimal = Decimal("1")

    _f = field_validator("function")(_function_ok)

    @model_validator(mode="after")
    def _somewhere(self):
        if self.class_id is None and self.function is None:
            raise ValueError("A target needs a fund, a function, or both")
        if self.weight < 0:
            raise ValueError("weight cannot be negative")
        return self


class AllocationTargetResponse(BaseModel):
    id: int
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    function: Optional[str] = None
    job_id: Optional[int] = None
    job_name: Optional[str] = None
    weight: Decimal
    line_order: int = 0
    model_config = {"from_attributes": True}


class AllocationRuleCreate(StrictModel):
    name: str = Field(..., max_length=100)
    basis: str = "percent"
    source_account_id: Optional[int] = None
    source_class_id: Optional[int] = None
    notes: Optional[str] = None
    is_active: bool = True
    targets: list[AllocationTargetIn] = []

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Rule name is required")
        return v

    @field_validator("basis")
    @classmethod
    def _basis(cls, v):
        v = (v or "").strip().lower()
        if v not in ALLOCATION_BASES:
            raise ValueError(f"basis must be one of {', '.join(ALLOCATION_BASES)}")
        return v

    @model_validator(mode="after")
    def _targets(self):
        if not self.targets:
            raise ValueError("A rule needs at least one target")
        if self.basis == "hours" and any(t.job_id is None for t in self.targets):
            raise ValueError(
                "Hours basis: every target names the job whose time weights it"
            )
        return self


class AllocationRuleUpdate(AllocationRuleCreate):
    pass


class AllocationRuleResponse(BaseModel):
    id: int
    name: str
    basis: str
    source_account_id: Optional[int] = None
    source_account_name: Optional[str] = None
    source_class_id: Optional[int] = None
    source_class_name: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True
    targets: list[AllocationTargetResponse] = []
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class SplitLine(BaseModel):
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    function: Optional[str] = None
    weight: Decimal
    amount: Decimal


class SplitResponse(BaseModel):
    rule_id: int
    rule_name: str
    amount: Decimal
    lines: list[SplitLine]


class PoolRow(BaseModel):
    account_id: int
    account_name: str
    account_number: Optional[str] = None
    amount: Decimal


class AllocationPreview(BaseModel):
    rule_id: int
    period_start: dt_date
    period_end: dt_date
    pool: list[PoolRow]
    total: Decimal
    lines: list[SplitLine]


# ── Functional allocation (a run of a rule) ──────────────────────────────


class FunctionalAllocationCreate(StrictModel):
    date: dt_date
    rule_id: int
    period_start: dt_date
    period_end: dt_date
    memo: Optional[str] = None

    @model_validator(mode="after")
    def _period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end is before period_start")
        return self


class FunctionalAllocationLineResponse(BaseModel):
    id: int
    account_id: int
    account_name: Optional[str] = None
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    function: Optional[str] = None
    weight: Optional[Decimal] = None
    amount: Decimal
    description: Optional[str] = None
    line_order: int = 0
    model_config = {"from_attributes": True}


class FunctionalAllocationResponse(BaseModel):
    id: int
    number: str
    date: dt_date
    rule_id: Optional[int] = None
    rule_name: Optional[str] = None
    period_start: dt_date
    period_end: dt_date
    memo: Optional[str] = None
    status: str
    transaction_id: Optional[int] = None
    total: Decimal
    lines: list[FunctionalAllocationLineResponse] = []
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}
