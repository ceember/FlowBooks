"""api_tokens table (was create_all-only)

The last table that only Base.metadata.create_all() created. After this,
`alembic upgrade head` alone produces the full schema, so a Docker start no
longer depends on the app's own create_all pass for anything (the advisory
lock around that pass stays as a belt to this brace). Idempotent: every
desktop file already has the table from create_all.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "api_tokens" in sa.inspect(bind).get_table_names():
        return
    # Mirrors app/models/api_tokens.py; keep the two in step.
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=12), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("label", name="uq_api_tokens_label"),
    )
    op.create_index("ix_api_tokens_id", "api_tokens", ["id"])
    op.create_index(
        "ix_api_tokens_token_hash", "api_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_api_tokens_token_hash", table_name="api_tokens")
    op.drop_index("ix_api_tokens_id", table_name="api_tokens")
    op.drop_table("api_tokens")
