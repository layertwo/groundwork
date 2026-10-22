"""drop stored oidc tokens from sessions

Revision ID: 08e66daf7971
Revises: 23c00082c27a
Create Date: 2026-10-22 02:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '08e66daf7971'
down_revision: Union[str, None] = '23c00082c27a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('sessions', 'access_token')
    op.drop_column('sessions', 'refresh_token')
    op.drop_column('sessions', 'id_token')


def downgrade() -> None:
    op.add_column('sessions', sa.Column('id_token', sa.Text(), nullable=True))
    op.add_column('sessions', sa.Column('refresh_token', sa.Text(), nullable=True))
    op.add_column('sessions', sa.Column('access_token', sa.Text(), nullable=True))
