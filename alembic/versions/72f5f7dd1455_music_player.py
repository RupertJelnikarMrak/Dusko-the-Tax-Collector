"""Music player

Revision ID: 72f5f7dd1455
Revises: 28ffae67133b
Create Date: 2024-08-14 14:21:10.306871

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72f5f7dd1455'
down_revision: Union[str, None] = '28ffae67133b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('music_players',
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('channel_id', sa.BigInteger(), nullable=False),
    sa.Column('message_id', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('guild_id')
    )


def downgrade() -> None:
    op.drop_table('music_players')
