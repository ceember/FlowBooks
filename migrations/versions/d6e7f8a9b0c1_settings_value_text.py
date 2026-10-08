"""widen settings.value to Text

The settings table was created with value VARCHAR(500); the model has said
Text for a long time. SQLite ignores the length, so every desktop file was
fine; PostgreSQL enforces it, and the SimpleFIN access URL a bank feed
stores in settings is longer than 500 characters — saving it failed on the
Docker / Server install (kycrna, fork branch feature/codex-oauth).

Contributed by @kycrna; re-homed at the head of the chain here because the
original revision id collided with b2c3d4e5f6a7_add_user_preferences, and
written with batch_alter_table so it runs on SQLite too (a no-op there in
effect, but the chain must apply everywhere).

Revision ID: d6e7f8a9b0c1
Revises: c4d5e6f7a8b9
Create Date: 2026-09-07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("settings") as batch:
        batch.alter_column(
            "value",
            existing_type=sa.String(length=500),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("settings") as batch:
        batch.alter_column(
            "value",
            existing_type=sa.Text(),
            type_=sa.String(length=500),
            existing_nullable=True,
        )
