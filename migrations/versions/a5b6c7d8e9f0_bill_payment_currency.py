"""bill_payment_currency

Currency + settlement rate on bill payments — closes the multi-currency
v1 gap: A/P now realizes FX gain/loss the same way A/R does.

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-08-01

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bill_payments") as batch_op:
        batch_op.add_column(sa.Column("currency", sa.String(length=3), nullable=True))
        batch_op.add_column(
            sa.Column("exchange_rate", sa.Numeric(18, 8), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("bill_payments") as batch_op:
        batch_op.drop_column("exchange_rate")
        batch_op.drop_column("currency")
