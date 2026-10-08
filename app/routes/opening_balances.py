# ============================================================================
# Opening-balance wizard — guided opening balances without manual
# journal-entry knowledge (joelmacklow spec: spec-opening-balance-wizard).
#
# Posting rules (per spec):
#   positive asset amounts DEBIT the account
#   positive liability/equity amounts CREDIT the account
#   negative amounts invert the normal side; zero lines are ignored
#   unbalanced entries are rejected unless auto-balance posts the
#   difference to a chosen equity account
# ============================================================================

from datetime import date as dt_date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from app.schemas.common import StrictModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.accounts import Account, AccountType
from app.services.accounting import _q, create_journal_entry
from app.services.settings_service import get_all_settings

router = APIRouter(prefix="/api/opening-balances", tags=["opening_balances"])

_BALANCE_SHEET_TYPES = (AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY)


class OpeningBalanceLine(StrictModel):
    account_id: int
    amount: Decimal


class OpeningBalanceCreate(StrictModel):
    date: dt_date
    description: str = "Opening balances"
    reference: Optional[str] = None
    lines: list[OpeningBalanceLine] = []
    auto_balance_account_id: Optional[int] = None


def _chart_ready(db: Session) -> bool:
    return (
        db.query(Account)
        .filter(
            Account.account_type.in_(_BALANCE_SHEET_TYPES), Account.is_active.is_(True)
        )
        .first()
        is not None
    )


@router.get("/status")
def status(db: Session = Depends(get_db)):
    settings = get_all_settings(db)
    accounts = (
        db.query(Account)
        .filter(
            Account.account_type.in_(_BALANCE_SHEET_TYPES), Account.is_active.is_(True)
        )
        .order_by(Account.account_type, Account.account_number)
        .all()
    )
    return {
        "ready": len(accounts) > 0,
        "chart_setup_source": settings.get("chart_setup_source") or None,
        "chart_setup_ready_at": settings.get("chart_setup_ready_at") or None,
        "accounts": [
            {
                "id": a.id,
                "name": a.name,
                "account_number": a.account_number,
                "account_type": a.account_type.value,
            }
            for a in accounts
        ],
    }


@router.post("")
def create_opening_balances(data: OpeningBalanceCreate, db: Session = Depends(get_db)):
    if not _chart_ready(db):
        raise HTTPException(
            status_code=400,
            detail=(
                "Chart of accounts is not ready — load a chart or run a "
                "Xero import first"
            ),
        )

    journal_lines = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for line in data.lines:
        amount = _q(Decimal(str(line.amount)))
        if amount == 0:
            continue
        account = db.get(Account, line.account_id)
        if not account or account.account_type not in _BALANCE_SHEET_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Account {line.account_id} is not an active balance-sheet account",
            )
        debit_normal = account.account_type == AccountType.ASSET
        # positive amount goes to the account's normal side; negative inverts
        debit_side = debit_normal if amount > 0 else not debit_normal
        magnitude = abs(amount)
        journal_lines.append(
            {
                "account_id": account.id,
                "debit": magnitude if debit_side else Decimal("0"),
                "credit": Decimal("0") if debit_side else magnitude,
                "description": f"Opening balance — {account.name}",
            }
        )
        total_debit += magnitude if debit_side else Decimal("0")
        total_credit += Decimal("0") if debit_side else magnitude

    if not journal_lines:
        raise HTTPException(
            status_code=400, detail="No non-zero opening balances given"
        )

    difference = total_debit - total_credit
    if difference != 0:
        if not data.auto_balance_account_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Opening balances are unbalanced by {abs(difference)} — "
                    f"correct the amounts or choose an equity account to "
                    f"auto-balance against"
                ),
            )
        equity = db.get(Account, data.auto_balance_account_id)
        if not equity or equity.account_type != AccountType.EQUITY:
            raise HTTPException(
                status_code=400,
                detail="Auto-balance account must be an equity account",
            )
        journal_lines.append(
            {
                "account_id": equity.id,
                "debit": -difference if difference < 0 else Decimal("0"),
                "credit": difference if difference > 0 else Decimal("0"),
                "description": f"Opening balance equity adjustment — {equity.name}",
            }
        )

    txn = create_journal_entry(
        db,
        data.date,
        data.description,
        journal_lines,
        source_type="opening_balance",
        reference=data.reference,
    )
    db.commit()
    return {
        "transaction_id": txn.id,
        "lines": len(journal_lines),
        "auto_balanced": difference != 0,
    }
