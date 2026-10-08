# ============================================================================
# QBO type correspondences and QBOMapping helpers shared by qbo_import.py
# and qbo_export.py (both previously carried private copies).
#
# Import collapses QBO's account-type vocabulary onto our six AccountType
# enums; export emits one representative (qbo_type, qbo_subtype) pair per
# enum. tests/test_interchange_roundtrip.py asserts the two directions
# stay consistent.
#
# Known-lossy round trips (inherent to the QBO vocabulary, not bugs):
#   ItemType.LABOR exports as "Service" and re-imports as ItemType.SERVICE.
# ============================================================================

from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.accounts import AccountType
from app.models.items import ItemType
from app.models.qbo_mapping import QBOMapping
from app.services import qbo_progress

QBO_TO_ACCOUNT_TYPE = {
    "Bank": AccountType.ASSET,
    "Accounts Receivable": AccountType.ASSET,
    "Other Current Asset": AccountType.ASSET,
    "Fixed Asset": AccountType.ASSET,
    "Other Asset": AccountType.ASSET,
    "Accounts Payable": AccountType.LIABILITY,
    "Credit Card": AccountType.LIABILITY,
    "Other Current Liability": AccountType.LIABILITY,
    "Long Term Liability": AccountType.LIABILITY,
    "Equity": AccountType.EQUITY,
    "Income": AccountType.INCOME,
    "Other Income": AccountType.INCOME,
    "Expense": AccountType.EXPENSE,
    "Other Expense": AccountType.EXPENSE,
    "Cost of Goods Sold": AccountType.COGS,
}

# AccountType -> (QBO AccountType, QBO AccountSubType)
ACCOUNT_TYPE_TO_QBO = {
    AccountType.ASSET: ("Other Current Asset", "Other Current Asset"),
    AccountType.LIABILITY: ("Other Current Liability", "Other Current Liability"),
    AccountType.EQUITY: ("Equity", "Opening Balance Equity"),
    AccountType.INCOME: ("Income", "Sales of Product Income"),
    AccountType.EXPENSE: ("Expense", "Other Miscellaneous Service Cost"),
    AccountType.COGS: ("Cost of Goods Sold", "Supplies and Materials - COGS"),
}

QBO_TO_ITEM_TYPE = {
    "Service": ItemType.SERVICE,
    "Inventory": ItemType.PRODUCT,
    "Group": ItemType.PRODUCT,
    "NonInventory": ItemType.MATERIAL,
}

ITEM_TYPE_TO_QBO = {
    ItemType.SERVICE: "Service",
    ItemType.PRODUCT: "Inventory",
    ItemType.MATERIAL: "NonInventory",
    ItemType.LABOR: "Service",
}


def get_mapping_by_slowbooks_id(
    db: Session, entity_type: str, slowbooks_id: int
) -> QBOMapping:
    """Look up existing mapping by FlowBooks ID."""
    return (
        db.query(QBOMapping)
        .filter(
            QBOMapping.entity_type == entity_type,
            QBOMapping.slowbooks_id == slowbooks_id,
        )
        .first()
    )


def get_mapping_by_qbo_id(db: Session, entity_type: str, qbo_id: str) -> QBOMapping:
    """Look up existing mapping by QBO ID."""
    mapping = (
        db.query(QBOMapping)
        .filter(
            QBOMapping.entity_type == entity_type,
            QBOMapping.qbo_id == str(qbo_id),
        )
        .first()
    )
    if mapping:
        qbo_progress.existing(entity_type, qbo_id)
    return mapping


def create_mapping(
    db: Session,
    entity_type: str,
    slowbooks_id: int,
    qbo_id: str,
    sync_token: str = None,
):
    """Create a new QBO <-> FlowBooks mapping."""
    m = QBOMapping(
        entity_type=entity_type,
        slowbooks_id=slowbooks_id,
        qbo_id=str(qbo_id),
        qbo_sync_token=sync_token,
    )
    db.add(m)
    qbo_progress.mapped(entity_type, qbo_id)


def is_journal_entry_type(txn_type: str) -> bool:
    """QBO reports label the JournalEntry resource as General Journal."""
    return txn_type.lower().replace(" ", "") in {
        "journalentry",
        "generaljournal",
        "journal",
    }


def _posting_totals(rows):
    result = defaultdict(Decimal)
    for account_id, debit, credit in rows:
        result[account_id] += debit - credit
    return {key: value for key, value in result.items() if value}


def journal_posting_matches(txn, txn_date, lines) -> bool:
    """Compare account postings when API and report lines group differently."""
    if txn is None or txn.date != txn_date:
        return False
    return _posting_totals(
        (line.account_id, line.debit, line.credit) for line in txn.lines
    ) == _posting_totals(
        (line["account_id"], line["debit"], line["credit"]) for line in lines
    )


def legacy_rollup_repair(txn, txn_date, lines, accounts):
    """Recognize the old report walker assigning child rows to parent accounts.

    Only reassign existing managed lines when dates and every monetary line
    match exactly after folding source accounts onto their saved ancestors.
    Preserve transaction/line IDs, amounts, and any reconciliation links.
    """
    if (
        txn is None
        or txn.date != txn_date
        or txn.source_type not in {"qbo_ledger", "qbo_journal"}
    ):
        return None
    by_id = {account.id: account for account in accounts.values() if account}
    saved_accounts = {line.account_id for line in txn.lines}
    targets = defaultdict(list)
    moved = False
    for line in lines:
        source_id = line["account_id"]
        folded_id = source_id
        seen = set()
        while folded_id not in saved_accounts:
            account = by_id.get(folded_id)
            if account is None or account.parent_id is None or folded_id in seen:
                return None
            seen.add(folded_id)
            folded_id = account.parent_id
        key = (folded_id, line["debit"], line["credit"])
        targets[key].append(source_id)
        moved |= folded_id != source_id
    if not moved or len(lines) != len(txn.lines):
        return None
    repair = []
    for line in txn.lines:
        possible = targets.get((line.account_id, line.debit, line.credit), [])
        # Ambiguous equal amounts on different child accounts need review.
        if not possible or len(set(possible)) != 1:
            return None
        target = possible.pop()
        if target != line.account_id:
            # A line that is cleared, in a reconciliation, or deposited
            # belongs to its account's statement or deposit: moving it
            # would leave a finished reconciliation that no longer adds up
            # (a reconciled entry cannot be voided either). Report it.
            if line.reconciliation_id or line.cleared or line.deposit_transaction_id:
                qbo_progress.emit(
                    "verify",
                    f"Local transaction #{txn.id}, line #{line.id} is cleared, "
                    "reconciled or deposited; its account was not changed",
                    level="warning",
                    code="IMPORT_REPAIR_REFUSED",
                )
                return None
            repair.append((line, target))
    return repair if not any(targets.values()) else None


def apply_rollup_repair(txn, repair, accounts):
    """Apply only the preflighted account changes and report every affected ID."""
    by_id = {account.id: qbo_id for qbo_id, account in accounts.items() if account}
    for line, account_id in repair:
        old_id = line.account_id
        line.account_id = account_id
        qbo_progress.emit(
            "repair",
            f"Local transaction #{txn.id}, line #{line.id}: corrected parent account "
            f"QBO #{by_id.get(old_id, 'unmapped')} / local #{old_id} to child account "
            f"QBO #{by_id.get(account_id, 'unmapped')} / local #{account_id}; "
            f"debit {line.debit:.2f}, credit {line.credit:.2f} unchanged; pending commit",
            code="IMPORT_ACCOUNT_ROLLUP_REPAIRED",
        )


def rebase_account_balances(db: Session, accounts) -> None:
    """Replace QBO's cached current balances with actual local postings."""
    from app.services.bank_register import gl_balances

    accounts = {account.id: account for account in accounts if account is not None}
    balances = gl_balances(db, accounts)
    for account_id, account in accounts.items():
        account.balance = balances[account_id]
    db.flush()


# QBOMapping.qbo_sync_token of an import posting (a "ledger" or
# "journal_entry" mapping) that the import no longer owns. Otherwise it
# holds QBO's SyncToken (journals) or the posting's fingerprint (ledger).
CHANGED_HERE = "changed-in-slowbooks"  # voided or replaced here: kept as is
KEPT_HERE = "kept-in-slowbooks"  # the same, once an import's log said so
HERE = (CHANGED_HERE, KEPT_HERE)
VOIDED_IN_QBO = "voided-in-qbo"  # reversed by the import: QBO voided it
DELETED_IN_QBO = "deleted-in-qbo"  # reversed by the import: QBO deleted it
NOT_OWNED = (CHANGED_HERE, KEPT_HERE, VOIDED_IN_QBO, DELETED_IN_QBO)
KEPT_MESSAGE = "Changed in FlowBooks; kept as it is here"


def kept_here(key, mappings) -> None:
    """An import leaves a transaction changed in FlowBooks as it is here.
    The run's log counts it in one line for the run (qbo_progress.kept);
    the first run to keep it also gives it a line of its own, and marks
    its mappings KEPT_HERE so that later runs only count it. `key` names
    the transaction once however many steps of a run keep it."""
    first = [m for m in mappings if m is not None and m.qbo_sync_token == CHANGED_HERE]
    if qbo_progress.kept(key, KEPT_MESSAGE if first else None):
        for mapping in first:
            mapping.qbo_sync_token = KEPT_HERE


# The item a QuickBooks Online discount comes in on (qbo_import._discount_item):
# a mapping of this entity type, keyed by QBO's discount account, names it.
DISCOUNT_ITEM = "discount_item"


def discount_mapping(db: Session, item_id) -> QBOMapping | None:
    """The mapping of a local item a QuickBooks Online discount came in on;
    its qbo_id is QBO's discount account (empty when QBO named none)."""
    if not item_id:
        return None
    return (
        db.query(QBOMapping)
        .filter(
            QBOMapping.entity_type == DISCOUNT_ITEM,
            QBOMapping.slowbooks_id == item_id,
        )
        .first()
    )


def discount_item_ids(db: Session) -> set[int]:
    """Every local item a QuickBooks Online discount came in on."""
    return {
        sid
        for (sid,) in db.query(QBOMapping.slowbooks_id).filter(
            QBOMapping.entity_type == DISCOUNT_ITEM
        )
    }


def is_discount_item(db: Session, item_id) -> bool:
    """Whether a local item is one a QuickBooks Online discount came in on:
    a line on it may carry a negative price (routes/invoices/helpers.py,
    refuse_negative_lines), and exports as QBO's discount (qbo_export)."""
    return discount_mapping(db, item_id) is not None


def ledger_posting(db: Session, txn_type: str, qbo_id) -> QBOMapping | None:
    """The QBO ledger import's mapping for QBO transaction `txn_type` #qbo_id
    ("Invoice", "Sales Receipt"), when it has posted that transaction. The
    report names types with spaces ("Sales Receipt"); either spelling
    matches."""
    wanted = txn_type.lower().replace(" ", "")
    qbo_id = str(qbo_id)
    for mapping in db.query(QBOMapping).filter(
        QBOMapping.entity_type == "ledger",
        QBOMapping.qbo_id.endswith(f":{qbo_id}", autoescape=True),
    ):
        kind, _, mapped_id = mapping.qbo_id.partition(":")
        if mapped_id == qbo_id and kind.lower().replace(" ", "") == wanted:
            return mapping
    return None
