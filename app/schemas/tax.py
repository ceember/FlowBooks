from typing import Optional
from pydantic import BaseModel
from app.schemas.common import StrictModel


class TaxMappingCreate(StrictModel):
    account_id: int
    tax_line: str


class TaxMappingResponse(BaseModel):
    id: int
    account_id: int
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    tax_line: str
    model_config = {"from_attributes": True}
