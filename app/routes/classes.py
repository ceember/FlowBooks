# ============================================================================
# Classes — CRUD for the QB-style tracking dimension.
#
# The system-default "Uncategorized" row is immutable: no rename, no
# archive, no delete — by-class reports rely on it always existing as the
# bucket for untagged activity. Classes referenced by any document or
# transaction can be archived (hidden from dropdowns) but never deleted,
# so historical reports stay stable.
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.classes import TxnClass
from app.models.transactions import Transaction
from app.schemas.classes import ClassCreate, ClassResponse, ClassUpdate
from app.services.classes_service import uncategorized_class_id

router = APIRouter(prefix="/api/classes", tags=["classes"])


@router.get("", response_model=list[ClassResponse])
def list_classes(include_archived: bool = False, db: Session = Depends(get_db)):
    # Ensure the default row exists before the first listing renders.
    uncategorized_class_id(db)
    db.commit()
    q = db.query(TxnClass)
    if not include_archived:
        q = q.filter(TxnClass.is_archived.is_(False))
    # System default first, then alphabetical — matches dropdown order.
    return q.order_by(TxnClass.is_system_default.desc(), TxnClass.name).all()


@router.post("", response_model=ClassResponse, status_code=201)
def create_class(data: ClassCreate, db: Session = Depends(get_db)):
    existing = db.query(TxnClass).filter(TxnClass.name.ilike(data.name)).first()
    if existing:
        raise HTTPException(
            status_code=409, detail=f"Class '{existing.name}' already exists"
        )
    row = TxnClass(
        name=data.name,
        restriction=data.restriction,
        default_function=data.default_function,
        donor_name=data.donor_name,
        purpose=data.purpose,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{class_id}", response_model=ClassResponse)
def update_class(class_id: int, data: ClassUpdate, db: Session = Depends(get_db)):
    row = db.get(TxnClass, class_id)
    if not row:
        raise HTTPException(status_code=404, detail="Class not found")
    if row.is_system_default and (
        data.name is not None or data.is_archived is not None
    ):
        raise HTTPException(
            status_code=400,
            detail="The system default class cannot be renamed or archived",
        )
    if data.name is not None:
        clash = (
            db.query(TxnClass)
            .filter(TxnClass.name.ilike(data.name), TxnClass.id != class_id)
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=409, detail=f"Class '{clash.name}' already exists"
            )
        row.name = data.name
    if data.is_archived is not None:
        row.is_archived = data.is_archived
    # Fund fields: the system default stays unrestricted (it is the bucket
    # for untagged activity) but may carry a default function.
    if data.restriction is not None:
        if row.is_system_default and data.restriction != "unrestricted":
            raise HTTPException(
                status_code=400, detail="The system default class is unrestricted"
            )
        row.restriction = data.restriction
    if "default_function" in data.model_fields_set:
        row.default_function = data.default_function
    if "donor_name" in data.model_fields_set:
        row.donor_name = data.donor_name
    if "purpose" in data.model_fields_set:
        row.purpose = data.purpose
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{class_id}")
def delete_class(class_id: int, db: Session = Depends(get_db)):
    row = db.get(TxnClass, class_id)
    if not row:
        raise HTTPException(status_code=404, detail="Class not found")
    if row.is_system_default:
        raise HTTPException(
            status_code=400, detail="The system default class cannot be deleted"
        )
    in_use = (
        db.query(Transaction).filter(Transaction.class_id == class_id).first()
        is not None
    )
    if in_use:
        raise HTTPException(
            status_code=400,
            detail="Class is used by posted transactions — archive it instead",
        )
    db.delete(row)
    db.commit()
    return {"message": "Class deleted"}
