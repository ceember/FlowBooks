from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: int
    table_name: str
    record_id: int
    action: str
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    changed_fields: Optional[list] = None
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    # Server Edition: who made the change. Response models STRIP undeclared
    # fields silently — this line missing was a field-debugged display bug
    # (the DB had the value all along; the API filtered it out).
    username: Optional[str] = None

    model_config = {"from_attributes": True}
