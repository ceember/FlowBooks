"""document tax rates to four decimal places of a percent

A document's tax rate is a fraction of its taxable lines (0.0825 = 8.25%),
and it was Numeric(5, 4): four places of a fraction, two of a percent. New
York City's 8.875% (0.08875) and rates like 7.0625% could not be kept.
PostgreSQL rounded 0.08875 to 0.0888 and SQLite read it back as 0.0887, so
an invoice at 8.875% on $1,000.00 was saved with $88.75 of tax, and the
next edit, duplicate or re-post worked it out again from the stored rate:
$88.80 on one engine, $88.70 on the other.

Numeric(7, 6) keeps the one integer digit Numeric(5, 4) has and adds two
decimal places: a fraction to six places is a percent to four. Every
stored value fits and none changes. PostgreSQL alters each column in
place; SQLite rewrites the table (batch_alter_table), as 6f57f762f464
does. SQLite kept the rate it was given all along and read it back at four
places, so a rate an API client sent with up to six places reads back as
it was sent once the column says six.

The downgrade takes the columns back to Numeric(5, 4). PostgreSQL rounds a
rate with more than four places as it converts it (0.08875 becomes
0.0888); SQLite keeps the stored value and reads it at four places again.

Revision ID: d3d40d716684
Revises: 4c7e2a9d1b05
Create Date: 2026-09-26

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3d40d716684"
down_revision: Union[str, None] = "4c7e2a9d1b05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every document that carries a tax rate. Sales receipts are invoices.
TABLES = (
    "invoices",
    "estimates",
    "credit_memos",
    "recurring_invoices",
    "bills",
    "purchase_orders",
    "vendor_credits",
)


def _set_tax_rate(new: sa.Numeric, old: sa.Numeric) -> None:
    present = set(sa.inspect(op.get_bind()).get_table_names())
    for table in TABLES:
        if table not in present:
            continue
        with op.batch_alter_table(table) as batch:
            batch.alter_column("tax_rate", existing_type=old, type_=new)


def upgrade() -> None:
    _set_tax_rate(sa.Numeric(7, 6), sa.Numeric(5, 4))


def downgrade() -> None:
    _set_tax_rate(sa.Numeric(5, 4), sa.Numeric(7, 6))
