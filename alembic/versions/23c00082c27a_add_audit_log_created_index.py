"""add audit log created_at index

Revision ID: 23c00082c27a
Revises: 997a9a2fb56d
Create Date: 2026-10-21 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '23c00082c27a'
down_revision: Union[str, None] = '997a9a2fb56d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_audit_log_created', 'audit_log', ['created_at', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_audit_log_created', table_name='audit_log')
