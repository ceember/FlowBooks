"""users table (was create_all-only)

The users table was only ever created by Base.metadata.create_all() at app
startup, never by a migration. On the desktop (SQLite) nobody noticed: the
launcher runs `alembic upgrade head` and SQLite accepts a foreign key to a
table that does not exist yet. On Postgres it is fatal: docker-entrypoint.sh
runs `alembic upgrade head` BEFORE the app starts, so when
b2c3d4e5f6a7_add_user_preferences (v2.8.0) declared
`REFERENCES users (id)` there was no users table to reference and
`docker compose up` died in a restart loop — every fresh Linux/Intel-Mac
install since 2.8.0 (2.9.0 Linux gate, devbase1).

This revision sits BETWEEN a1b2c3d4e5f6 and b2c3d4e5f6a7 so a fresh
database creates users before anything references it. Installs already
past b2c3 (every desktop file) never run it; they got the table from
create_all and stay at head. Idempotent on purpose.

Revision ID: a0b1c2d3e4f5
Revises: a1b2c3d4e5f6
Create Date: 2026-09-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "users" in sa.inspect(bind).get_table_names():
        return
    # Mirrors app/models/users.py exactly; keep the two in step.
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
