from typing import Type, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import Base

T = TypeVar("T", bound=Base)


def clamp_pagination(skip: int, limit: int, max_limit: int = 1000) -> tuple[int, int]:
    """Normalize list-endpoint paging params: skip >= 0, 1 <= limit <= max_limit."""
    return max(0, skip or 0), max(1, min(limit or max_limit, max_limit))


def get_or_404(db: Session, model: Type[T], obj_id: int, name: str = None) -> T:
    obj = db.query(model).filter(model.id == obj_id).first()
    if not obj:
        label = name or model.__name__
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj
