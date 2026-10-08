from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from app.schemas.common import StrictModel

from app.models.classes import FUNCTIONS, RESTRICTIONS


def _check_restriction(v):
    if v is None:
        return v
    if v not in RESTRICTIONS:
        raise ValueError(f"restriction must be one of: {', '.join(RESTRICTIONS)}")
    return v


def _check_function(v):
    if v in (None, ""):
        return None
    if v not in FUNCTIONS:
        raise ValueError(f"default_function must be one of: {', '.join(FUNCTIONS)}")
    return v


class ClassCreate(StrictModel):
    name: str
    restriction: str = "unrestricted"
    default_function: Optional[str] = None
    donor_name: Optional[str] = Field(None, max_length=200)
    purpose: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Class name is required")
        return v

    _r = field_validator("restriction")(_check_restriction)
    _f = field_validator("default_function")(_check_function)


class ClassUpdate(StrictModel):
    name: Optional[str] = None
    is_archived: Optional[bool] = None
    restriction: Optional[str] = None
    default_function: Optional[str] = None
    donor_name: Optional[str] = Field(None, max_length=200)
    purpose: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Class name cannot be blank")
        return v

    _r = field_validator("restriction")(_check_restriction)
    _f = field_validator("default_function")(_check_function)


class ClassResponse(BaseModel):
    id: int
    name: str
    is_archived: bool
    is_system_default: bool
    restriction: str = "unrestricted"
    default_function: Optional[str] = None
    donor_name: Optional[str] = None
    purpose: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
