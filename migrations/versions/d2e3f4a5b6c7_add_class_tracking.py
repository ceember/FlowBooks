"""add_class_tracking

QB-style class dimension: new `classes` table (with the immutable
"Uncategorized" system default) and a nullable class_id FK on
transactions and the classifiable source documents.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-01

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "transactions",
    "invoices",
    "bills",
    "credit_memos",
    "estimates",
    "recurring_invoices",
)


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_system_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    classes = sa.table(
        "classes", sa.column("name", sa.String), sa.column("is_system_default")
    )
    op.bulk_insert(classes, [{"name": "Uncategorized", "is_system_default": True}])

    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("class_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table}_class_id", "classes", ["class_id"], ["id"]
            )


def downgrade() -> None:
    for table in reversed(_TABLES):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_class_id", type_="foreignkey")
            batch_op.drop_column("class_id")
    op.drop_table("classes")
