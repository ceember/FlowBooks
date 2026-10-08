"""Default fixed-asset type, so depreciation works on a fresh company.

A fixed asset needs an asset type, and a type needs three account
mappings (asset, accumulated depreciation, depreciation expense) before
`run-depreciation` will post anything. The seed chart has 1500 Equipment
and 1510 Accumulated Depreciation but, until 2.9.0, no depreciation
expense account and no type at all — so the first thing every new company
hit on the Fixed Assets page was "missing account mappings" (2.9.0 gate,
both platforms). One general-purpose type, mapped to the seed accounts,
straight-line over five years, is enough to get a first asset posted; the
user edits or adds types from there.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.accounts import Account, AccountType
from app.models.fixed_assets import DepreciationMethod, FixedAssetType

DEFAULT_ASSET_TYPE_NAME = "Equipment"


def ensure_default_asset_type(db: Session) -> FixedAssetType | None:
    """Create the default type when the company has no asset types at all.

    Idempotent; returns the type that exists (or was created), or None when
    the chart lacks the accounts to map (an imported chart with no
    Equipment account — the user picks their own on the form). Flushes;
    the caller commits."""
    existing = db.query(FixedAssetType).order_by(FixedAssetType.id).first()
    if existing is not None:
        return existing

    from app.services.accounting import ensure_account

    def _by_name(name: str, kind: AccountType) -> Account | None:
        return (
            db.query(Account)
            .filter(Account.name == name, Account.account_type == kind)
            .first()
        )

    asset = _by_name("Equipment", AccountType.ASSET)
    accumulated = _by_name("Accumulated Depreciation", AccountType.ASSET)
    if asset is None or accumulated is None:
        return None
    expense = ensure_account(db, "6810", "Depreciation Expense", AccountType.EXPENSE)
    atype = FixedAssetType(
        name=DEFAULT_ASSET_TYPE_NAME,
        description="General equipment, straight-line over five years",
        asset_account_id=asset.id,
        accumulated_depreciation_account_id=accumulated.id,
        depreciation_expense_account_id=expense.id,
        depreciation_method=DepreciationMethod.STRAIGHT_LINE,
        effective_life_years=Decimal("5"),
    )
    db.add(atype)
    db.flush()
    return atype
