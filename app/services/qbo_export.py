# ============================================================================
# QBO Export Service — Push data from FlowBooks to QuickBooks Online
#
# Export order follows the same dependency chain as import:
#   accounts -> customers -> vendors -> items -> invoices (and sales
#   receipts) -> payments
#
# Each record goes the first time as a new QBO record; its mapping is marked
# as the export's own ("sent:" + a fingerprint of what went). Later exports
# send it again as an update to the same QBO record when it changed here
# since (its fingerprint differs; QBO's current copy is read first, for its
# SyncToken and the fields FlowBooks doesn't keep), void it in QBO when it
# was voided here, and leave it when nothing changed. A record the import
# brought in from QBO (or matched to one) is QBO's and is never touched, nor
# is one an earlier release sent, whose mapping can't be told from those.
# What QBO refuses goes in the result's notes, in words; the rest carries on.
# ============================================================================

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import logging

from sqlalchemy.orm import Session

from app.models.accounts import Account, AccountType
from app.models.contacts import Customer, Vendor
from app.models.items import Item
from app.models.invoices import Invoice, InvoiceLine, InvoiceStatus
from app.models.payments import Payment
from app.services.qbo_common import (
    ACCOUNT_TYPE_TO_QBO,
    ITEM_TYPE_TO_QBO,
    create_mapping,
    discount_mapping,
    get_mapping_by_qbo_id,
    get_mapping_by_slowbooks_id,
)
from app.services.qbo_service import get_qbo_client
from app.services.safe_errors import safe_message

logger = logging.getLogger(__name__)

# A mapping the export made: "sent:" and the fingerprint of what went, or
# SENT_VOID once the record is voided in QBO too.
SENT = "sent:"
SENT_VOID = "sent:void"


class _NotReady(Exception):
    """A record that can't go yet (its customer isn't in QBO), in words."""


def _result() -> dict:
    return {"exported": 0, "updated": 0, "voided": 0, "errors": [], "notes": []}


def _mark(fields: dict) -> str:
    """The mapping's mark for what goes: "sent:" and a fingerprint of the
    fields, so a record whose fields are the same is never sent again."""
    text = json.dumps(fields, sort_keys=True, default=str)
    return SENT + sha256(text.encode("utf-8")).hexdigest()[:16]


def _apply(obj, fields: dict):
    """Set the fields FlowBooks keeps on a QBO record, new or read from QBO;
    None clears a field (the SDK leaves it out, and a full update clears
    what it leaves out)."""
    for key, value in fields.items():
        setattr(obj, key, value)
    return obj


def _ours(mapping) -> bool:
    return mapping is not None and (mapping.qbo_sync_token or "").startswith(SENT)


def _refusal(exc) -> str:
    """Why QBO refused a change, in its own words and with its error code;
    anything else is ours, and says only what may be said."""
    from quickbooks.exceptions import QuickbooksException

    if isinstance(exc, QuickbooksException):
        logger.warning("QBO refused an export change: %s", exc)
        words = " ".join(str(exc.detail or exc.message or "").split())[:300]
        code = f" (QuickBooks Online error {exc.error_code})" if exc.error_code else ""
        return (words or "it gave no reason") + code
    return safe_message(exc, "QBO export")


def _note(result, entity, local_id, message) -> None:
    result["notes"].append({"entity": entity, "id": local_id, "message": message})


def _send(db, client, result, kind, local_id, label, qbo_class, fields, notes=()):
    """Send one record: create it in QBO the first time; update the same QBO
    record when it changed here since it went; leave it when it didn't, and
    leave one that isn't the export's own (QBO's, or sent by an earlier
    release). `notes` are the record's own notes, given when it goes."""
    mapping = get_mapping_by_slowbooks_id(db, kind, local_id)
    mark = _mark(fields)
    if mapping is None:
        saved = _apply(qbo_class(), fields).save(qb=client)
        create_mapping(db, kind, local_id, saved.Id, mark)
        result["exported"] += 1
        result["notes"].extend(notes)
        return
    if not _ours(mapping) or mapping.qbo_sync_token in (mark, SENT_VOID):
        return
    try:
        current = qbo_class.get(mapping.qbo_id, qb=client)
        _apply(current, fields).save(qb=client)
    except Exception as exc:
        _note(
            result,
            kind,
            local_id,
            f"{label} changed here since it went to QuickBooks Online, but "
            f"QuickBooks Online refused the update: {_refusal(exc)}. It is as it "
            "went there, and the next export tries again.",
        )
        return
    mapping.qbo_sync_token = mark
    mapping.last_synced_at = datetime.now(timezone.utc)
    result["updated"] += 1
    result["notes"].extend(notes)


def _void(db, client, result, kind, local_id, label, qbo_class) -> None:
    """A record voided here after it went: void it in QBO too, once. One
    that never went stays out; one that isn't the export's own is left."""
    mapping = get_mapping_by_slowbooks_id(db, kind, local_id)
    if not _ours(mapping) or mapping.qbo_sync_token == SENT_VOID:
        return
    try:
        qbo_class.get(mapping.qbo_id, qb=client).void(qb=client)
    except Exception as exc:
        _note(
            result,
            kind,
            local_id,
            f"{label} is voided here, but QuickBooks Online refused to void it: "
            f"{_refusal(exc)}. It stands there as it went, and the next export "
            "tries again.",
        )
        return
    mapping.qbo_sync_token = SENT_VOID
    mapping.last_synced_at = datetime.now(timezone.utc)
    result["voided"] += 1


def _ref(db, kind, local_id):
    """{"value": QBO id} of a mapped record, or None."""
    mapping = get_mapping_by_slowbooks_id(db, kind, local_id) if local_id else None
    return {"value": mapping.qbo_id} if mapping else None


def _address(line1, line2, city, state, postal):
    if not (line1 or city):
        return None
    return {
        "Line1": line1 or "",
        "Line2": line2 or "",
        "City": city or "",
        "CountrySubDivisionCode": state or "",
        "PostalCode": postal or "",
    }


def _phone(number):
    return {"FreeFormNumber": number} if number else None


# ============================================================================
# Export functions
# ============================================================================


def _account_fields(db: Session, acct) -> dict:
    kind, subtype = ACCOUNT_TYPE_TO_QBO.get(
        acct.account_type, ("Expense", "Other Miscellaneous Service Cost")
    )
    parent = _ref(db, "account", acct.parent_id)
    return {
        "Name": acct.name,
        "AccountType": kind,
        "AccountSubType": subtype,
        "AcctNum": acct.account_number or None,
        "Description": acct.description or None,
        "ParentRef": parent,
        "SubAccount": True if parent else None,
        "Active": acct.is_active is not False,
    }


def export_accounts(db: Session) -> dict:
    """Export FlowBooks accounts to QBO: new ones, and changes to ones the
    export sent."""
    from quickbooks.objects.account import Account as QBOAccount

    client = get_qbo_client(db)
    result = _result()

    # Sort by parent (null parent_id first)
    accounts = sorted(db.query(Account).all(), key=lambda a: (a.parent_id or 0, a.id))
    for acct in accounts:
        try:
            if not acct.is_active and not get_mapping_by_slowbooks_id(
                db, "account", acct.id
            ):
                continue  # an inactive one that never went stays out
            _send(
                db,
                client,
                result,
                "account",
                acct.id,
                f"Account {acct.name}",
                QBOAccount,
                _account_fields(db, acct),
            )
        except Exception as e:
            result["errors"].append(
                {
                    "entity": "account",
                    "id": acct.id,
                    "name": acct.name,
                    "message": safe_message(e, "QBO export"),
                }
            )

    return result


def _customer_fields(cust) -> dict:
    return {
        "DisplayName": cust.name,
        "CompanyName": cust.company or None,
        "BillAddr": _address(
            cust.bill_address1,
            cust.bill_address2,
            cust.bill_city,
            cust.bill_state,
            cust.bill_zip,
        ),
        "ShipAddr": _address(
            cust.ship_address1,
            cust.ship_address2,
            cust.ship_city,
            cust.ship_state,
            cust.ship_zip,
        ),
        "PrimaryEmailAddr": {"Address": cust.email} if cust.email else None,
        "PrimaryPhone": _phone(cust.phone),
        "Mobile": _phone(cust.mobile),
        "Fax": _phone(cust.fax),
        "Notes": cust.notes or None,
        "Active": cust.is_active is not False,
    }


def export_customers(db: Session) -> dict:
    """Export FlowBooks customers to QBO: new ones, and changes to ones the
    export sent."""
    from quickbooks.objects.customer import Customer as QBOCustomer

    client = get_qbo_client(db)
    result = _result()

    for cust in db.query(Customer).all():
        try:
            if not cust.is_active and not get_mapping_by_slowbooks_id(
                db, "customer", cust.id
            ):
                continue
            _send(
                db,
                client,
                result,
                "customer",
                cust.id,
                f"Customer {cust.name}",
                QBOCustomer,
                _customer_fields(cust),
            )
        except Exception as e:
            result["errors"].append(
                {
                    "entity": "customer",
                    "id": cust.id,
                    "name": cust.name,
                    "message": safe_message(e, "QBO export"),
                }
            )

    return result


def _vendor_fields(vend) -> dict:
    return {
        "DisplayName": vend.name,
        "CompanyName": vend.company or None,
        "BillAddr": _address(
            vend.address1, vend.address2, vend.city, vend.state, vend.zip
        ),
        "PrimaryEmailAddr": {"Address": vend.email} if vend.email else None,
        "PrimaryPhone": _phone(vend.phone),
        "Fax": _phone(vend.fax),
        "Notes": vend.notes or None,
        "AcctNum": vend.account_number or None,
        "Active": vend.is_active is not False,
    }


def export_vendors(db: Session) -> dict:
    """Export FlowBooks vendors to QBO: new ones, and changes to ones the
    export sent."""
    from quickbooks.objects.vendor import Vendor as QBOVendor

    client = get_qbo_client(db)
    result = _result()

    for vend in db.query(Vendor).all():
        try:
            if not vend.is_active and not get_mapping_by_slowbooks_id(
                db, "vendor", vend.id
            ):
                continue
            _send(
                db,
                client,
                result,
                "vendor",
                vend.id,
                f"Vendor {vend.name}",
                QBOVendor,
                _vendor_fields(vend),
            )
        except Exception as e:
            result["errors"].append(
                {
                    "entity": "vendor",
                    "id": vend.id,
                    "name": vend.name,
                    "message": safe_message(e, "QBO export"),
                }
            )

    return result


def _item_fields(db: Session, item) -> dict:
    income = _ref(db, "account", item.income_account_id)
    if income is None:
        # QBO requires IncomeAccountRef for Service/NonInventory items:
        # a default income account in the QBO mappings
        default_income = (
            db.query(Account)
            .filter(Account.account_type == AccountType.INCOME, Account.is_active)
            .first()
        )
        income = _ref(db, "account", default_income.id if default_income else None)
    return {
        "Name": item.name,
        "Type": ITEM_TYPE_TO_QBO.get(item.item_type, "Service"),
        "Description": item.description or None,
        "UnitPrice": float(item.rate) if item.rate else None,
        "PurchaseCost": float(item.cost) if item.cost else None,
        "IncomeAccountRef": income,
        "ExpenseAccountRef": _ref(db, "account", item.expense_account_id),
        "Active": item.is_active is not False,
    }


def export_items(db: Session) -> dict:
    """Export FlowBooks items to QBO: new ones, and changes to ones the
    export sent."""
    from quickbooks.objects.item import Item as QBOItem

    client = get_qbo_client(db)
    result = _result()

    for item in db.query(Item).all():
        try:
            if not item.is_active and not get_mapping_by_slowbooks_id(
                db, "item", item.id
            ):
                continue
            _send(
                db,
                client,
                result,
                "item",
                item.id,
                f"Item {item.name}",
                QBOItem,
                _item_fields(db, item),
            )
        except Exception as e:
            result["errors"].append(
                {
                    "entity": "item",
                    "id": item.id,
                    "name": item.name,
                    "message": safe_message(e, "QBO export"),
                }
            )

    return result


def _discount_account(db: Session, item_id, discount) -> tuple[str, str]:
    """(QBO account id, words for it) of a Discount item: the QBO discount
    account it came in on, else its income account where that is mapped;
    ("", its name) when QBO has none for it."""
    account = discount.qbo_id
    item = db.get(Item, item_id)
    local = None
    if account:
        mapped = get_mapping_by_qbo_id(db, "account", account)
        local = db.get(Account, mapped.slowbooks_id) if mapped else None
    elif item is not None and item.income_account_id:
        local = db.get(Account, item.income_account_id)
        mapped = get_mapping_by_slowbooks_id(db, "account", item.income_account_id)
        account = mapped.qbo_id if mapped else ""
    name = local.name if local is not None else (item.name if item else "Discount")
    return account, f"{name} (QBO #{account})" if account else name


def _discount_line(db: Session, parts, document, notes) -> dict:
    """An invoice's lines on Discount items (qbo_common.discount_mapping) as
    QBO's own discount, not negative sales lines with no item: ONE
    DiscountLineDetail, as QBO takes one discount on a transaction, for
    their total, on the discount account of the item with the most of it.
    A note names any other discount account whose amount went into it.
    `parts` is [(invoice line, its item's mapping)], in order; `document`
    names the invoice as it prints ("Invoice 2004")."""
    by_item = {}
    for inv_line, discount in parts:
        amount = -Decimal(str(inv_line.amount or 0))
        was = by_item.get(inv_line.item_id, (Decimal("0"), discount, inv_line))
        by_item[inv_line.item_id] = (was[0] + amount, discount, was[2])
    total = sum((amount for amount, _, _ in by_item.values()), Decimal("0"))
    largest = max(by_item, key=lambda item_id: by_item[item_id][0])
    _, discount, first = by_item[largest]
    account, words = _discount_account(db, largest, discount)
    others = [
        (amount, _discount_account(db, item_id, mapping)[1])
        for item_id, (amount, mapping, _) in by_item.items()
        if item_id != largest
    ]
    if others:
        named = "; ".join(f"{amount:,.2f} on {label}" for amount, label in others)
        notes.append(
            {
                "entity": "invoice",
                "id": first.invoice_id,
                "message": (
                    f"{document} went to QuickBooks Online with one discount "
                    f"of {total:,.2f} on {words}, as QuickBooks Online takes one "
                    f"discount on a transaction. It includes {named}."
                ),
            }
        )
    detail = {"PercentBased": False}
    if account:
        detail["DiscountAccountRef"] = {"value": account}
    return {
        "DetailType": "DiscountLineDetail",
        "Amount": float(total),
        "Description": first.description or "",
        "DiscountLineDetail": detail,
    }


def _face(inv, terms) -> str:
    """ "Invoice 2004", "Sales Receipt 2005": a document as it prints."""
    from app.services.donor_documents import document_label

    return f"{document_label(inv, terms)} {inv.invoice_number}"


def _sales_lines(db: Session, inv, notes, label) -> tuple[list, bool]:
    """A document's lines as QBO takes them, and whether its tax is worked
    out after its discount: each sales line with its item and tax code (QBO
    taxes the lines this document taxes, at its own rate; a document that
    charges no tax taxes none of its lines), and its lines on Discount items
    as QBO's one discount (_discount_line)."""
    lines, discounts, after = [], [], False
    charges_tax = Decimal(str(inv.tax_amount or 0)) != 0
    inv_lines = (
        db.query(InvoiceLine)
        .filter(InvoiceLine.invoice_id == inv.id)
        .order_by(InvoiceLine.line_order)
        .all()
    )
    for inv_line in inv_lines:
        discount = discount_mapping(db, inv_line.item_id)
        if discount is not None and (inv_line.amount or 0) < 0:
            if not discounts:
                lines.append(None)  # where QBO's discount goes
            discounts.append((inv_line, discount))
            # the discount comes off the taxable amount, as QBO's does when
            # it works the tax out after the discount
            after = after or bool(inv_line.is_taxable)
            continue
        taxed = charges_tax and inv_line.is_taxable is not False
        detail = {
            "Qty": float(inv_line.quantity or 1),
            "UnitPrice": float(inv_line.rate or 0),
            "TaxCodeRef": {"value": "TAX" if taxed else "NON"},
        }
        item = _ref(db, "item", inv_line.item_id)
        if item:
            detail["ItemRef"] = item
        lines.append(
            {
                "DetailType": "SalesItemLineDetail",
                "Amount": float(inv_line.amount or 0),
                "Description": inv_line.description or "",
                "SalesItemLineDetail": detail,
            }
        )
    if discounts:
        lines[lines.index(None)] = _discount_line(db, discounts, label, notes)
    return lines, after


def _customer_ref(db: Session, doc) -> dict:
    ref = _ref(db, "customer", doc.customer_id)
    if ref is None:
        raise _NotReady(f"Customer {doc.customer_id} not mapped to QBO")
    return ref


def _invoice_fields(db: Session, inv, notes, label) -> dict:
    lines, after = _sales_lines(db, inv, notes, label)
    return {
        "CustomerRef": _customer_ref(db, inv),
        "DocNumber": inv.invoice_number or None,
        "TxnDate": inv.date.isoformat() if inv.date else None,
        "DueDate": inv.due_date.isoformat() if inv.due_date else None,
        "Line": lines,
        "ApplyTaxAfterDiscount": after,
        # no tax detail: QBO works its tax out itself from the tax codes (on
        # an update, the one it read back would hold the old tax as its own)
        "TxnTaxDetail": None,
        "CustomerMemo": {"value": inv.notes} if inv.notes else None,
    }


def _receipt_payment(receipt):
    """The payment half of a sales receipt written here."""
    for alloc in receipt.payment_allocations:
        if alloc.payment is not None and not alloc.payment.is_voided:
            return alloc.payment
    return None


def _sales_receipt_fields(db: Session, receipt, notes, label) -> dict:
    """A sales receipt written here, as QBO's own SalesReceipt: its lines,
    tax codes and discount, and the account its money went to."""
    lines, after = _sales_lines(db, receipt, notes, label)
    payment = _receipt_payment(receipt)
    return {
        "CustomerRef": _customer_ref(db, receipt),
        "DocNumber": receipt.invoice_number or None,
        "TxnDate": receipt.date.isoformat() if receipt.date else None,
        "Line": lines,
        "ApplyTaxAfterDiscount": after,
        "TxnTaxDetail": None,
        "CustomerMemo": {"value": receipt.notes} if receipt.notes else None,
        "DepositToAccountRef": (
            _ref(db, "account", payment.deposit_to_account_id) if payment else None
        ),
        "PaymentRefNum": (
            (payment.reference or payment.check_number or None) if payment else None
        ),
    }


def _sent_as_invoice(db: Session, receipt) -> bool:
    """A sales receipt an earlier release sent as an invoice and a payment:
    it stays as it went, and is not sent again as a sales receipt."""
    return get_mapping_by_slowbooks_id(db, "invoice", receipt.id) is not None


def export_invoices(db: Session) -> dict:
    """Export FlowBooks invoices and sales receipts to QBO: new ones, changes
    to ones the export sent, and voids of them. A sales receipt goes as a
    QBO SalesReceipt ("sales_receipts" counts them). A document the import
    brought in from QBO is QBO's, and stays as it is there."""
    from quickbooks.objects.invoice import Invoice as QBOInvoice
    from quickbooks.objects.salesreceipt import SalesReceipt as QBOSalesReceipt

    from app.services.terminology import terms_from_db

    client = get_qbo_client(db)
    result = _result()
    receipts = _result()
    terms = terms_from_db(db)

    for inv in db.query(Invoice).all():
        try:
            receipt = bool(inv.is_sales_receipt) and not _sent_as_invoice(db, inv)
            kind = "sales_receipt" if receipt else "invoice"
            qbo_class = QBOSalesReceipt if receipt else QBOInvoice
            counts = receipts if receipt else result
            label = _face(inv, terms)
            mapping = get_mapping_by_slowbooks_id(db, kind, inv.id)
            if mapping is not None and not _ours(mapping):
                continue  # QBO's own, or sent before 2.18: as it is there
            if inv.status == InvoiceStatus.VOID:
                # voided before it went: stays out; after: voided there
                _void(db, client, counts, kind, inv.id, label, qbo_class)
                continue
            notes = []
            try:
                fields = (
                    _sales_receipt_fields(db, inv, notes, label)
                    if receipt
                    else _invoice_fields(db, inv, notes, label)
                )
            except _NotReady as exc:
                if mapping is None:
                    result["errors"].append(
                        {"entity": kind, "id": inv.id, "message": str(exc)}
                    )
                continue
            _send(db, client, counts, kind, inv.id, label, qbo_class, fields, notes)
        except Exception as e:
            result["errors"].append(
                {
                    "entity": "invoice",
                    "id": inv.id,
                    "message": safe_message(e, "QBO export"),
                }
            )

    result["exported"] += receipts["exported"]
    result["sales_receipts"] = receipts["exported"]
    for key in ("updated", "voided"):
        result[key] += receipts[key]
    result["notes"].extend(receipts["notes"])
    return result


def _payment_fields(db: Session, pmt) -> dict:
    lines = []
    for alloc in pmt.allocations:
        invoice = _ref(db, "invoice", alloc.invoice_id)
        if invoice:
            lines.append(
                {
                    "Amount": float(alloc.amount),
                    "LinkedTxn": [{"TxnId": invoice["value"], "TxnType": "Invoice"}],
                }
            )
    return {
        "CustomerRef": _customer_ref(db, pmt),
        "TotalAmt": float(pmt.amount),
        "TxnDate": pmt.date.isoformat() if pmt.date else None,
        "PaymentRefNum": pmt.reference or None,
        "DepositToAccountRef": _ref(db, "account", pmt.deposit_to_account_id),
        "Line": lines,
    }


def _in_a_receipt(db: Session, pmt) -> bool:
    """The payment half of a sales receipt, which is in QBO with its receipt:
    one the import brought in from QBO, or one that goes as a QBO
    SalesReceipt. (The half of a receipt an earlier release sent as an
    invoice and a payment goes as a payment, as it did.)"""
    for alloc in pmt.allocations:
        invoice = alloc.invoice
        if invoice is None:
            continue
        if get_mapping_by_slowbooks_id(db, "sales_receipt", invoice.id):
            return True
        if invoice.is_sales_receipt and not _sent_as_invoice(db, invoice):
            return True
    return False


def export_payments(db: Session) -> dict:
    """Export FlowBooks payments to QBO: new ones, changes to ones the export
    sent, and voids of them."""
    from quickbooks.objects.payment import Payment as QBOPayment

    client = get_qbo_client(db)
    result = _result()

    for pmt in db.query(Payment).all():
        try:
            if _in_a_receipt(db, pmt):
                continue
            mapping = get_mapping_by_slowbooks_id(db, "payment", pmt.id)
            if mapping is not None and not _ours(mapping):
                continue  # QBO's own, or sent before 2.18: as it is there
            payer = pmt.customer.name if pmt.customer else "A customer"
            label = (
                f"{payer}'s payment of {Decimal(str(pmt.amount)):,.2f} on {pmt.date}"
            )
            if pmt.is_voided:
                _void(db, client, result, "payment", pmt.id, label, QBOPayment)
                continue
            try:
                fields = _payment_fields(db, pmt)
            except _NotReady as exc:
                if mapping is None:
                    result["errors"].append(
                        {"entity": "payment", "id": pmt.id, "message": str(exc)}
                    )
                continue
            _send(db, client, result, "payment", pmt.id, label, QBOPayment, fields)
        except Exception as e:
            result["errors"].append(
                {
                    "entity": "payment",
                    "id": pmt.id,
                    "message": safe_message(e, "QBO export"),
                }
            )

    return result


# ============================================================================
# Master export orchestrator
# ============================================================================


def export_all(db: Session) -> dict:
    """Export all entity types to QBO in dependency order.

    Returns counts of records sent for the first time, of ones updated or
    voided in QBO, and any errors and notes.
    """
    result = {
        "accounts": 0,
        "customers": 0,
        "vendors": 0,
        "items": 0,
        "invoices": 0,
        "sales_receipts": 0,
        "payments": 0,
        "updated": 0,
        "voided": 0,
        "errors": [],
        "notes": [],
    }
    for entity, export in (
        ("accounts", export_accounts),
        ("customers", export_customers),
        ("vendors", export_vendors),
        ("items", export_items),
        ("invoices", export_invoices),
        ("payments", export_payments),
    ):
        r = export(db)
        result[entity] = r["exported"]
        if entity == "invoices":
            result["sales_receipts"] = r.get("sales_receipts", 0)
            result["invoices"] -= result["sales_receipts"]
        for key in ("updated", "voided"):
            result[key] += r.get(key, 0)
        result["errors"].extend(r["errors"])
        result["notes"].extend(r.get("notes", []))

    db.commit()
    return result
