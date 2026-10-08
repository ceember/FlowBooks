"""add_provider_checkout_fields

Provider-agnostic checkout tracking for the payment-provider abstraction:
which provider minted the most recent checkout, and its session/order id.
checkout_external_id is indexed because providers without metadata
passthrough (Square) resolve the invoice by this id on webhook/poll.

Revision ID: c1d2e3f4a5b6
Revises: bc3c3c5fd0a6
Create Date: 2026-08-01

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "bc3c3c5fd0a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(
            sa.Column("checkout_provider", sa.String(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column("checkout_external_id", sa.String(length=255), nullable=True)
        )
        batch_op.create_index(
            "ix_invoices_checkout_external_id", ["checkout_external_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_index("ix_invoices_checkout_external_id")
        batch_op.drop_column("checkout_external_id")
        batch_op.drop_column("checkout_provider")
