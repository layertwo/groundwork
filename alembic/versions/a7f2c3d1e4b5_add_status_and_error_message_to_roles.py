"""add status and error_message to roles

Revision ID: a7f2c3d1e4b5
Revises: 0574c829b686
Create Date: 2026-02-08 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7f2c3d1e4b5"
down_revision: Union[str, None] = "0574c829b686"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="pending"
        ),
    )
    op.add_column(
        "roles",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    # Backfill: existing roles with a provisioned IAM role should be active
    op.execute("UPDATE roles SET status = 'active' WHERE role_arn != ''")


def downgrade() -> None:
    op.drop_column("roles", "error_message")
    op.drop_column("roles", "status")
