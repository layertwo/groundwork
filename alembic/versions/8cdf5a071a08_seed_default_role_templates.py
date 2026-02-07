"""seed default role templates

Revision ID: 8cdf5a071a08
Revises: 43c0d3d8cf4d
Create Date: 2026-02-07 10:46:39.334601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8cdf5a071a08'
down_revision: Union[str, None] = '43c0d3d8cf4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


role_templates = sa.table(
    "role_templates",
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
    sa.column("managed_policy_arns", sa.ARRAY(sa.String)),
)

DEFAULTS = [
    {
        "name": "Admin",
        "description": "Full administrative access",
        "managed_policy_arns": ["arn:aws:iam::aws:policy/AdministratorAccess"],
    },
    {
        "name": "ReadOnly",
        "description": "Read-only access to all resources",
        "managed_policy_arns": ["arn:aws:iam::aws:policy/ReadOnlyAccess"],
    },
    {
        "name": "PowerUser",
        "description": "Full access except IAM and Organizations management",
        "managed_policy_arns": ["arn:aws:iam::aws:policy/PowerUserAccess"],
    },
]


def upgrade() -> None:
    op.bulk_insert(role_templates, DEFAULTS)


def downgrade() -> None:
    for tpl in DEFAULTS:
        op.execute(
            role_templates.delete().where(role_templates.c.name == tpl["name"])
        )
