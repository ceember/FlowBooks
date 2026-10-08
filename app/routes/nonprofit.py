"""Nonprofit mode — setup and the documents only a nonprofit posts.

Everything here is gated by Settings -> company_type = nonprofit on the
SPA side; the API itself answers for any company (a business that calls
setup-accounts simply gets four extra system accounts)."""

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.accounts import Account
from app.models.classes import TxnClass
from app.models.jobs import Job
from app.models.nonprofit import (
    AllocationRule,
    AllocationRuleTarget,
    FunctionalAllocation,
    FunctionalAllocationLine,
    RestrictionRelease,
)
from app.schemas.accounts import AccountResponse
from app.schemas.nonprofit import (
    AllocationPreview,
    AllocationRuleCreate,
    AllocationRuleResponse,
    AllocationRuleUpdate,
    AllocationTargetResponse,
    FunctionalAllocationCreate,
    FunctionalAllocationLineResponse,
    FunctionalAllocationResponse,
    ReleaseCreate,
    ReleaseResponse,
    ReleaseSuggestion,
    SplitResponse,
)
from app.services.accounting import NONPROFIT_ACCOUNTS, ensure_nonprofit_accounts
from app.services.closing_date import check_closing_date
from app.services.nonprofit import (
    allocation_pool,
    post_functional_allocation,
    post_release,
    split_amount,
    suggested_release,
    void_functional_allocation,
    void_release,
)

router = APIRouter(prefix="/api/nonprofit", tags=["nonprofit"])


@router.post("/setup-accounts", response_model=list[AccountResponse])
def setup_accounts(db: Session = Depends(get_db)):
    """Create the net-asset, in-kind and bad-debt accounts if missing
    (3300, 3400, 4400, 6960; numbers yield to an existing chart). Safe to
    call any number of times — the Settings page calls it when a company
    switches to nonprofit."""
    accounts = ensure_nonprofit_accounts(db)
    db.commit()
    return [accounts[number] for number, _name, _type in NONPROFIT_ACCOUNTS]


# ── Release from restriction ─────────────────────────────────────────────


def _release_response(rel: RestrictionRelease) -> ReleaseResponse:
    data = ReleaseResponse.model_validate(rel)
    data.class_name = rel.fund.name if rel.fund else ""
    return data


def _release_get(db: Session, rel_id: int) -> RestrictionRelease:
    rel = (
        db.query(RestrictionRelease)
        .options(joinedload(RestrictionRelease.fund))
        .filter(RestrictionRelease.id == rel_id)
        .first()
    )
    if not rel:
        raise HTTPException(status_code=404, detail="Release not found")
    return rel


@router.get("/releases/suggest", response_model=ReleaseSuggestion)
def suggest_release(
    class_id: int,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
):
    """What the fund spent in the period less what was already released
    for it — the amount the release form fills in."""
    try:
        return suggested_release(db, class_id, start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/releases", response_model=list[ReleaseResponse])
def list_releases(
    class_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(RestrictionRelease).options(joinedload(RestrictionRelease.fund))
    if class_id is not None:
        q = q.filter(RestrictionRelease.class_id == class_id)
    if status:
        q = q.filter(RestrictionRelease.status == status)
    return [
        _release_response(r)
        for r in q.order_by(
            RestrictionRelease.date.desc(), RestrictionRelease.id.desc()
        ).all()
    ]


@router.get("/releases/{rel_id}", response_model=ReleaseResponse)
def get_release(rel_id: int, db: Session = Depends(get_db)):
    return _release_response(_release_get(db, rel_id))


@router.post("/releases", response_model=ReleaseResponse, status_code=201)
def create_release(data: ReleaseCreate, db: Session = Depends(get_db)):
    check_closing_date(db, data.date)
    try:
        rel = post_release(
            db,
            txn_date=data.date,
            class_id=data.class_id,
            amount=data.amount,
            period_start=data.period_start,
            period_end=data.period_end,
            memo=data.memo,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return _release_response(_release_get(db, rel.id))


@router.post("/releases/{rel_id}/void", response_model=ReleaseResponse)
def void_release_route(rel_id: int, db: Session = Depends(get_db)):
    rel = _release_get(db, rel_id)
    check_closing_date(db, rel.date)
    try:
        void_release(db, rel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _release_response(_release_get(db, rel.id))


# ── Allocation rules ─────────────────────────────────────────────────────


def _rule_response(rule: AllocationRule) -> AllocationRuleResponse:
    data = AllocationRuleResponse.model_validate(rule)
    data.source_account_name = rule.source_account.name if rule.source_account else None
    data.source_class_name = rule.source_class.name if rule.source_class else None
    data.targets = []
    for t in rule.targets:
        tr = AllocationTargetResponse.model_validate(t)
        tr.class_name = t.fund.name if t.fund else None
        tr.job_name = t.job.full_name if t.job else None
        data.targets.append(tr)
    return data


def _rule_query(db: Session):
    return db.query(AllocationRule).options(
        joinedload(AllocationRule.source_account),
        joinedload(AllocationRule.source_class),
        joinedload(AllocationRule.targets).joinedload(AllocationRuleTarget.fund),
        joinedload(AllocationRule.targets).joinedload(AllocationRuleTarget.job),
    )


def _rule_get(db: Session, rule_id: int) -> AllocationRule:
    rule = _rule_query(db).filter(AllocationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Allocation rule not found")
    return rule


def _check_rule_refs(db: Session, data: AllocationRuleCreate) -> None:
    if data.source_account_id and not db.get(Account, data.source_account_id):
        raise HTTPException(status_code=404, detail="Source account not found")
    if data.source_class_id and not db.get(TxnClass, data.source_class_id):
        raise HTTPException(status_code=404, detail="Source fund not found")
    for t in data.targets:
        if t.class_id and not db.get(TxnClass, t.class_id):
            raise HTTPException(status_code=404, detail="Target fund not found")
        if t.job_id and not db.get(Job, t.job_id):
            raise HTTPException(status_code=404, detail="Target job not found")


def _apply_rule(rule: AllocationRule, data: AllocationRuleCreate) -> None:
    rule.name = data.name
    rule.basis = data.basis
    rule.source_account_id = data.source_account_id
    rule.source_class_id = data.source_class_id
    rule.notes = data.notes
    rule.is_active = data.is_active
    rule.targets = [
        AllocationRuleTarget(
            class_id=t.class_id,
            function=t.function,
            job_id=t.job_id,
            weight=t.weight,
            line_order=i,
        )
        for i, t in enumerate(data.targets)
    ]


@router.get("/allocation-rules", response_model=list[AllocationRuleResponse])
def list_allocation_rules(
    include_inactive: bool = False, db: Session = Depends(get_db)
):
    q = _rule_query(db)
    if not include_inactive:
        q = q.filter(AllocationRule.is_active.is_(True))
    return [_rule_response(r) for r in q.order_by(AllocationRule.name).all()]


@router.post(
    "/allocation-rules", response_model=AllocationRuleResponse, status_code=201
)
def create_allocation_rule(data: AllocationRuleCreate, db: Session = Depends(get_db)):
    if db.query(AllocationRule).filter(AllocationRule.name.ilike(data.name)).first():
        raise HTTPException(status_code=409, detail="A rule with that name exists")
    _check_rule_refs(db, data)
    rule = AllocationRule()
    _apply_rule(rule, data)
    db.add(rule)
    db.commit()
    return _rule_response(_rule_get(db, rule.id))


@router.get("/allocation-rules/{rule_id}", response_model=AllocationRuleResponse)
def get_allocation_rule(rule_id: int, db: Session = Depends(get_db)):
    return _rule_response(_rule_get(db, rule_id))


@router.put("/allocation-rules/{rule_id}", response_model=AllocationRuleResponse)
def update_allocation_rule(
    rule_id: int, data: AllocationRuleUpdate, db: Session = Depends(get_db)
):
    rule = _rule_get(db, rule_id)
    clash = (
        db.query(AllocationRule)
        .filter(AllocationRule.name.ilike(data.name), AllocationRule.id != rule_id)
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="A rule with that name exists")
    _check_rule_refs(db, data)
    _apply_rule(rule, data)
    db.commit()
    return _rule_response(_rule_get(db, rule.id))


@router.delete("/allocation-rules/{rule_id}")
def delete_allocation_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = _rule_get(db, rule_id)
    used = (
        db.query(FunctionalAllocation.id)
        .filter(FunctionalAllocation.rule_id == rule_id)
        .first()
    )
    if used:
        raise HTTPException(
            status_code=409,
            detail="Rule has posted allocations — deactivate it instead",
        )
    db.delete(rule)
    db.commit()
    return {"message": "Rule deleted"}


@router.get("/allocation-rules/{rule_id}/split", response_model=SplitResponse)
def split_by_rule(
    rule_id: int,
    amount: float,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    class_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """One amount through the rule — what the Split button on an entry
    line expands into. `class_id` is the line's own fund, used for targets
    that name only a function."""
    rule = _rule_get(db, rule_id)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Amount must be positive")
    try:
        lines = split_amount(
            db, rule, amount, start_date, end_date, pool_class_id=class_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "amount": amount,
        "lines": lines,
    }


@router.get("/allocation-rules/{rule_id}/preview", response_model=AllocationPreview)
def preview_allocation(
    rule_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
):
    """What a period-end run would move: the unassigned pool on the
    rule's source and how it would split."""
    rule = _rule_get(db, rule_id)
    pool = allocation_pool(db, rule, start_date, end_date)
    total = sum((r["amount"] for r in pool), start=Decimal("0"))
    lines = []
    if total > 0:
        try:
            lines = split_amount(db, rule, total, start_date, end_date)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    # collapse pool rows by account for the preview table
    by_acct: dict[int, dict] = {}
    for r in pool:
        row = by_acct.setdefault(
            r["account_id"],
            {
                "account_id": r["account_id"],
                "account_name": r["account_name"],
                "account_number": r["account_number"],
                "amount": Decimal("0"),
            },
        )
        row["amount"] += r["amount"]
    return {
        "rule_id": rule.id,
        "period_start": start_date,
        "period_end": end_date,
        "pool": list(by_acct.values()),
        "total": total,
        "lines": lines,
    }


# ── Functional allocations (runs) ────────────────────────────────────────


def _fa_response(fa: FunctionalAllocation) -> FunctionalAllocationResponse:
    data = FunctionalAllocationResponse.model_validate(fa)
    data.rule_name = fa.rule.name if fa.rule else None
    data.lines = []
    for ln in fa.lines:
        lr = FunctionalAllocationLineResponse.model_validate(ln)
        lr.account_name = ln.account.name if ln.account else None
        lr.class_name = ln.fund.name if ln.fund else None
        data.lines.append(lr)
    return data


def _fa_query(db: Session):
    return db.query(FunctionalAllocation).options(
        joinedload(FunctionalAllocation.rule),
        joinedload(FunctionalAllocation.lines).joinedload(
            FunctionalAllocationLine.account
        ),
        joinedload(FunctionalAllocation.lines).joinedload(
            FunctionalAllocationLine.fund
        ),
    )


def _fa_get(db: Session, fa_id: int) -> FunctionalAllocation:
    fa = _fa_query(db).filter(FunctionalAllocation.id == fa_id).first()
    if not fa:
        raise HTTPException(status_code=404, detail="Allocation not found")
    return fa


@router.get("/allocations", response_model=list[FunctionalAllocationResponse])
def list_allocations(
    rule_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = _fa_query(db)
    if rule_id is not None:
        q = q.filter(FunctionalAllocation.rule_id == rule_id)
    if status:
        q = q.filter(FunctionalAllocation.status == status)
    return [
        _fa_response(fa)
        for fa in q.order_by(
            FunctionalAllocation.date.desc(), FunctionalAllocation.id.desc()
        ).all()
    ]


@router.get("/allocations/{fa_id}", response_model=FunctionalAllocationResponse)
def get_allocation(fa_id: int, db: Session = Depends(get_db)):
    return _fa_response(_fa_get(db, fa_id))


@router.post(
    "/allocations", response_model=FunctionalAllocationResponse, status_code=201
)
def create_allocation(data: FunctionalAllocationCreate, db: Session = Depends(get_db)):
    check_closing_date(db, data.date)
    rule = _rule_get(db, data.rule_id)
    try:
        fa = post_functional_allocation(
            db,
            rule=rule,
            txn_date=data.date,
            start=data.period_start,
            end=data.period_end,
            memo=data.memo,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return _fa_response(_fa_get(db, fa.id))


@router.post("/allocations/{fa_id}/void", response_model=FunctionalAllocationResponse)
def void_allocation(fa_id: int, db: Session = Depends(get_db)):
    fa = _fa_get(db, fa_id)
    check_closing_date(db, fa.date)
    try:
        void_functional_allocation(db, fa)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _fa_response(_fa_get(db, fa.id))
