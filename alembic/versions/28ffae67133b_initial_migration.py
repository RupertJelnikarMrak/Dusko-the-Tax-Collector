"""Initial migration

Revision ID: 28ffae67133b
Revises: 
Create Date: 2024-08-14 14:15:51.796229

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '28ffae67133b'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    op.execute('DROP SCHEMA railway CASCADE;')
    op.execute('CREATE SCHEMA railway;')
