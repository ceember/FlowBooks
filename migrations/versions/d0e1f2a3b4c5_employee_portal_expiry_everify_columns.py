"""add employee portal-expiry and e-verify lifecycle columns

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-05 12:00:00.000000

The Employee model declares portal_token_last_used / portal_token_expires_at
(token idle + hard expiry windows) and the E-Verify lifecycle columns
(everify_status / everify_submitted_at / everify_closed_at / everify_notes),
but the tier3 migration only created portal_token and everify_case_number.
On a properly-migrated database (create_all only creates missing tables —
it never ALTERs the existing employees table) every employee create, portal
access, and E-Verify update crashed with UndefinedColumn.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("portal_token_last_used", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "employees",
        sa.Column("portal_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "employees", sa.Column("everify_status", sa.String(30), nullable=True)
    )
    op.add_column(
        "employees",
        sa.Column("everify_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "employees",
        sa.Column("everify_closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("employees", sa.Column("everify_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "everify_notes")
    op.drop_column("employees", "everify_closed_at")
    op.drop_column("employees", "everify_submitted_at")
    op.drop_column("employees", "everify_status")
    op.drop_column("employees", "portal_token_expires_at")
    op.drop_column("employees", "portal_token_last_used")
