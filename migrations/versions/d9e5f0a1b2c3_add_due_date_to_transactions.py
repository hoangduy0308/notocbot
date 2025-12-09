"""Add due_date column to transactions table

Revision ID: d9e5f0a1b2c3
Revises: c8d4e5f6a7b8
Create Date: 2025-12-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e5f0a1b2c3'
down_revision: Union[str, Sequence[str], None] = 'c8d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('due_date', sa.DateTime(), nullable=True))
    op.create_index('ix_transactions_due_date', 'transactions', ['due_date'])


def downgrade() -> None:
    op.drop_index('ix_transactions_due_date', table_name='transactions')
    op.drop_column('transactions', 'due_date')
