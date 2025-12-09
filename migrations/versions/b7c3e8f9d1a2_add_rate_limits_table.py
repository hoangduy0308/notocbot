"""Add rate_limits table for rate limiting

Revision ID: b7c3e8f9d1a2
Revises: a31859debf80
Create Date: 2025-01-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c3e8f9d1a2'
down_revision: Union[str, Sequence[str], None] = 'a31859debf80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'rate_limits',
        sa.Column('user_id', sa.BigInteger(), primary_key=True),
        sa.Column('tokens', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('last_refill_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('rate_limits')
