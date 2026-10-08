"""nonprofit_dimensions

Nonprofit mode, part one: a class becomes a fund. Every class gains a
restriction (unrestricted | temporarily_restricted | permanently_restricted,
ASU 2016-14 net-asset reporting collapses the last two into "with donor
restrictions"), a default function (program | management | fundraising —
the Form 990 Part IX columns), and the donor / purpose a restricted fund
came with. Posted lines and bill lines gain a nullable ``function`` so an
expense can be reported by what it was for, defaulted from its class at
posting time and reclassed by the shared-cost allocation document.

Field report: a community arts nonprofit running classes-as-funds could
not produce a Statement of Functional Expenses without a spreadsheet.

Revision ID: f1a2b3c4d5e6
Revises: e6f7a8b9c0d1
Create Date: 2026-09-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LINE_TABLES = ("transaction_lines", "bill_lines")


def upgrade() -> None:
    with op.batch_alter_table("classes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "restriction",
                sa.String(length=30),
                nullable=False,
                server_default="unrestricted",
            )
        )
        batch_op.add_column(
            sa.Column("default_function", sa.String(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column("donor_name", sa.String(length=200), nullable=True)
        )
        batch_op.add_column(sa.Column("purpose", sa.Text(), nullable=True))
    for table in _LINE_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(
                sa.Column("function", sa.String(length=20), nullable=True)
            )


def downgrade() -> None:
    for table in reversed(_LINE_TABLES):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("function")
    with op.batch_alter_table("classes") as batch_op:
        batch_op.drop_column("purpose")
        batch_op.drop_column("donor_name")
        batch_op.drop_column("default_function")
        batch_op.drop_column("restriction")
