"""add_fixed_assets

Fixed-asset register: types (with the three account mappings) and
assets. Both are new tables, but existing desktop files upgrade via
this revision since the launcher runs `alembic upgrade head`.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-08-01

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fixed_asset_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "asset_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id"),
            nullable=True,
        ),
        sa.Column(
            "accumulated_depreciation_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id"),
            nullable=True,
        ),
        sa.Column(
            "depreciation_expense_account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id"),
            nullable=True,
        ),
        sa.Column(
            "depreciation_method",
            sa.Enum("STRAIGHT_LINE", "DECLINING_BALANCE", name="depreciationmethod"),
            nullable=False,
            server_default="STRAIGHT_LINE",
        ),
        sa.Column("effective_life_years", sa.Numeric(8, 2), nullable=True),
        sa.Column("annual_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_table(
        "fixed_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_number", sa.String(length=40), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "asset_type_id",
            sa.Integer(),
            sa.ForeignKey("fixed_asset_types.id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("REGISTERED", "DISPOSED", name="fixedassetstatus"),
            nullable=False,
            server_default="REGISTERED",
        ),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column(
            "purchase_price", sa.Numeric(12, 2), nullable=False, server_default="0"
        ),
        sa.Column(
            "salvage_value", sa.Numeric(12, 2), nullable=False, server_default="0"
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "accumulated_depreciation",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_depreciation_date", sa.Date(), nullable=True),
        sa.Column("disposal_date", sa.Date(), nullable=True),
        sa.Column("disposal_proceeds", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_fixed_assets_asset_type_id", "fixed_assets", ["asset_type_id"])


def downgrade() -> None:
    op.drop_index("ix_fixed_assets_asset_type_id", table_name="fixed_assets")
    op.drop_table("fixed_assets")
    op.drop_table("fixed_asset_types")
