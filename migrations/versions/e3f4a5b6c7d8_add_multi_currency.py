"""add_multi_currency

Currency + booked exchange rate on invoices, bills, and payments; adds
the home_currency setting default separately (settings are row-based).
The GL stays home-currency — these columns record what the document was
denominated in and the rate its journal was converted at.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-08-01

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("invoices", "bills", "payments")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(
                sa.Column("currency", sa.String(length=3), nullable=True)
            )
            batch_op.add_column(
                sa.Column("exchange_rate", sa.Numeric(18, 8), nullable=True)
            )


def downgrade() -> None:
    for table in reversed(_TABLES):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("exchange_rate")
            batch_op.drop_column("currency")
