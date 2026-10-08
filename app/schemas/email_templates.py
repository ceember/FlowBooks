from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from app.schemas.common import StrictModel


class EmailTemplateCreate(StrictModel):
    name: str
    subject_template: str
    body_template: str
    template_type: str


class EmailTemplateUpdate(StrictModel):
    name: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    template_type: Optional[str] = None


class EmailTemplateResponse(BaseModel):
    id: int
    name: str
    subject_template: str
    body_template: str
    template_type: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
