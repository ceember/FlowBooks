from pydantic import BaseModel
from pydantic import Field
from typing import Literal

from app.schemas.common import StrictModel


class QBOImportRunRequest(StrictModel):
    entities: (
        list[
            Literal[
                "accounts",
                "customers",
                "vendors",
                "items",
                "invoices",
                "payments",
                "sales_receipts",
                "journal_entries",
                "ledger",
            ]
        ]
        | None
    ) = Field(default=None, min_length=1, max_length=9)


class QBOImportResult(BaseModel):
    accounts: int = 0
    customers: int = 0
    vendors: int = 0
    items: int = 0
    invoices: int = 0
    payments: int = 0
    sales_receipts: int = 0
    journal_entries: int = 0
    ledger: int = 0
    errors: list[dict] = []


class QBOExportResult(BaseModel):
    accounts: int = 0
    customers: int = 0
    vendors: int = 0
    items: int = 0
    invoices: int = 0
    sales_receipts: int = 0
    payments: int = 0
    # records sent before that changed here since (updated in QBO), and ones
    # voided here after they went (voided in QBO)
    updated: int = 0
    voided: int = 0
    errors: list[dict] = []
    # what went differently from how it reads here, and why (an invoice's
    # discounts on several accounts went as QBO's one discount)
    notes: list[dict] = []


class QBOConnectionStatus(BaseModel):
    connected: bool = False
    company_name: str = ""
    realm_id: str = ""
