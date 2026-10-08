"""Server Edition: per-user audit attribution — username column on audit_log

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-08-12
"""

import sqlalchemy as sa
from alembic import op

revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode for SQLite compatibility (desktop company files)
    with op.batch_alter_table("audit_log") as batch_op:
        batch_op.add_column(sa.Column("username", sa.String(100), nullable=True))
        batch_op.create_index("ix_audit_log_username", ["username"])


def downgrade() -> None:
    with op.batch_alter_table("audit_log") as batch_op:
        batch_op.drop_index("ix_audit_log_username")
        batch_op.drop_column("username")
