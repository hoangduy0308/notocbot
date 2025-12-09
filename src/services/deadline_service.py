"""
Deadline service - Manage transaction due dates.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.models import Transaction, Debtor
from src.services.debt_service import get_transaction_with_owner_check


async def update_transaction_due_date(
    session: AsyncSession,
    user_id: int,
    transaction_id: int,
    due_date: Optional[datetime]
) -> Optional[Transaction]:
    """
    Update the due_date of a transaction with ownership verification.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (creditor)
        transaction_id: Transaction ID to update
        due_date: New due date (None to clear)
    
    Returns:
        Updated Transaction or None if not found/not owned
    """
    transaction = await get_transaction_with_owner_check(session, user_id, transaction_id)
    
    if not transaction:
        return None
    
    transaction.due_date = due_date
    await session.flush()
    
    return transaction


async def list_upcoming_deadlines(
    session: AsyncSession,
    user_id: int,
    limit: int = 20,
    days: Optional[int] = None
) -> List[Transaction]:
    """
    Get transactions with due dates for a user.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (creditor)
        limit: Maximum number of results
        days: Optional filter - only return due dates within X days from now
    
    Returns:
        List of Transactions with due_date set, sorted by due_date ASC
    
    Note:
        - Only returns transactions where due_date IS NOT NULL
        - Includes overdue transactions (past due_date)
        - Sorted by due_date ASC, then created_at ASC
    """
    query = (
        select(Transaction)
        .join(Debtor, Transaction.debtor_id == Debtor.id)
        .where(
            (Debtor.user_id == user_id) &
            (Transaction.due_date.isnot(None))
        )
    )
    
    if days is not None:
        deadline = datetime.utcnow() + timedelta(days=days)
        query = query.where(Transaction.due_date <= deadline)
    
    query = (
        query
        .order_by(Transaction.due_date.asc(), Transaction.created_at.asc())
        .limit(limit)
    )
    
    result = await session.execute(query)
    return list(result.scalars().all())


__all__ = [
    "update_transaction_due_date",
    "list_upcoming_deadlines",
]
