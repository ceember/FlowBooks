"""vendor credits (issue #129)

The AP-side counterpart of a customer credit memo. A supplier issuing a
credit for returned or short-shipped materials had nowhere correct to go:
bills and expenses both reject a negative amount and both point at credit
memos, which only accept a customer. A manual journal entry against
Accounts Payable moves the general ledger but not the vendor sub-ledger,
so A/P aging and the vendor balance stop agreeing with account 2000 —
the same split #119 was about.

Three tables, mirroring credit_memos / credit_memo_lines /
credit_applications:

- vendor_credits: header, with the running amount_applied and
  balance_remaining that make an unapplied credit a real open item.
- vendor_credit_lines: carries account_id (the expense account being
  credited back) because bill lines do, where a credit-memo line takes
  its account from the item's income side because invoice lines do.
- vendor_credit_applications: which bill a credit settled, and for how
  much. Applying posts nothing — the credit already moved A/P when it
  was issued.

Data-only note: nothing is backfilled. There is no earlier
representation of a vendor credit to migrate from; that absence is the
issue.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-09-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_credits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("credit_number", sa.String(length=50), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "ISSUED",
                "APPLIED",
                "VOID",
                name="vendorcreditstatus",
            ),
            nullable=True,
        ),
        sa.Column("original_bill_id", sa.Integer(), nullable=True),
        sa.Column("ref_number", sa.String(length=100), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=True),
        sa.Column("tax_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("total", sa.Numeric(12, 2), nullable=True),
        sa.Column("amount_applied", sa.Numeric(12, 2), nullable=True),
        sa.Column("balance_remaining", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendors.id"], name="fk_vendor_credits_vendor_id"
        ),
        sa.ForeignKeyConstraint(
            ["original_bill_id"], ["bills.id"], name="fk_vendor_credits_bill_id"
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name="fk_vendor_credits_transaction_id",
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name="fk_vendor_credits_class_id"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_vendor_credits_job_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credit_number", name="uq_vendor_credits_credit_number"),
    )
    op.create_index(
        "ix_vendor_credits_vendor_id", "vendor_credits", ["vendor_id"], unique=False
    )
    op.create_index("ix_vendor_credits_id", "vendor_credits", ["id"], unique=False)

    op.create_table(
        "vendor_credit_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vendor_credit_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("cost_code_id", sa.Integer(), nullable=True),
        sa.Column("line_order", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["vendor_credit_id"],
            ["vendor_credits.id"],
            name="fk_vendor_credit_lines_vendor_credit_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name="fk_vendor_credit_lines_item_id"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_vendor_credit_lines_account_id"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_vendor_credit_lines_job_id"
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name="fk_vendor_credit_lines_class_id"
        ),
        sa.ForeignKeyConstraint(
            ["cost_code_id"],
            ["cost_codes.id"],
            name="fk_vendor_credit_lines_cost_code_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vendor_credit_lines_vendor_credit_id",
        "vendor_credit_lines",
        ["vendor_credit_id"],
        unique=False,
    )
    op.create_index(
        "ix_vendor_credit_lines_id", "vendor_credit_lines", ["id"], unique=False
    )

    op.create_table(
        "vendor_credit_applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vendor_credit_id", sa.Integer(), nullable=False),
        sa.Column("bill_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["vendor_credit_id"],
            ["vendor_credits.id"],
            name="fk_vendor_credit_applications_vendor_credit_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bill_id"], ["bills.id"], name="fk_vendor_credit_applications_bill_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vendor_credit_applications_vendor_credit_id",
        "vendor_credit_applications",
        ["vendor_credit_id"],
        unique=False,
    )
    op.create_index(
        "ix_vendor_credit_applications_bill_id",
        "vendor_credit_applications",
        ["bill_id"],
        unique=False,
    )
    op.create_index(
        "ix_vendor_credit_applications_id",
        "vendor_credit_applications",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("vendor_credit_applications")
    op.drop_table("vendor_credit_lines")
    op.drop_table("vendor_credits")
    # The Enum is a real type on PostgreSQL and must be dropped by name;
    # on SQLite it is a CHECK constraint that went with the table.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="vendorcreditstatus").drop(bind, checkfirst=True)
