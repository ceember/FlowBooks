# ============================================================================
# FX rates — thin wrapper over the Bank of Canada Valet fetcher so the
# SPA can prefill exchange-rate fields on foreign-currency documents.
# ============================================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.currency import home_currency
from app.services.fx_service import get_rate

router = APIRouter(prefix="/api/fx", tags=["fx"])


@router.get("/rate")
def fx_rate(from_currency: str, to_currency: str = None, db: Session = Depends(get_db)):
    """Latest available rate from one currency to another (default: home).

    Degrades gracefully: rate is null when the feed can't provide one,
    and the UI asks the operator for an explicit rate instead.
    """
    target = to_currency or home_currency(db)
    result = get_rate(from_currency, target)
    return {
        "from_currency": (from_currency or "").upper(),
        "to_currency": target.upper(),
        "rate": str(result["rate"]) if result.get("rate") else None,
        "observation_date": result.get("observation_date"),
        "source": result.get("source"),
        "error": result.get("error"),
    }
