"""Add ON DELETE CASCADE to foreign keys

Revision ID: c8d4e5f6a7b8
Revises: b7c3e8f9d1a2
Create Date: 2025-12-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b7c3e8f9d1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ON DELETE CASCADE to foreign keys."""
    # Drop existing foreign keys and recreate with CASCADE
    
    # transactions.debtor_id -> debtors.id
    op.drop_constraint('transactions_debtor_id_fkey', 'transactions', type_='foreignkey')
    op.create_foreign_key(
        'transactions_debtor_id_fkey',
        'transactions', 'debtors',
        ['debtor_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # aliases.debtor_id -> debtors.id
    op.drop_constraint('aliases_debtor_id_fkey', 'aliases', type_='foreignkey')
    op.create_foreign_key(
        'aliases_debtor_id_fkey',
        'aliases', 'debtors',
        ['debtor_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # debtors.user_id -> users.id
    op.drop_constraint('debtors_user_id_fkey', 'debtors', type_='foreignkey')
    op.create_foreign_key(
        'debtors_user_id_fkey',
        'debtors', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Remove CASCADE from foreign keys."""
    # Revert to original constraints without CASCADE
    
    op.drop_constraint('transactions_debtor_id_fkey', 'transactions', type_='foreignkey')
    op.create_foreign_key(
        'transactions_debtor_id_fkey',
        'transactions', 'debtors',
        ['debtor_id'], ['id']
    )
    
    op.drop_constraint('aliases_debtor_id_fkey', 'aliases', type_='foreignkey')
    op.create_foreign_key(
        'aliases_debtor_id_fkey',
        'aliases', 'debtors',
        ['debtor_id'], ['id']
    )
    
    op.drop_constraint('debtors_user_id_fkey', 'debtors', type_='foreignkey')
    op.create_foreign_key(
        'debtors_user_id_fkey',
        'debtors', 'users',
        ['user_id'], ['id']
    )
