"""
Debt service - Manage transactions (recording debts and credits).
"""

from decimal import Decimal
from typing import List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, text, delete
from src.database.models import Transaction, Debtor


async def add_transaction(
    session: AsyncSession,
    debtor_id: int,
    amount: Decimal,
    transaction_type: str,  # "DEBT" or "CREDIT"
    note: str = None,
    group_id: int = None
) -> Transaction:
    """
    Add a new transaction for a debtor.
    
    Args:
        session: AsyncSession instance
        debtor_id: ID of the debtor
        amount: Transaction amount (always positive)
        transaction_type: "DEBT" or "CREDIT"
        note: Optional note about the transaction
        group_id: Optional Telegram group/chat ID where transaction was recorded
        
    Returns:
        Transaction instance
    """
    transaction = Transaction(
        debtor_id=debtor_id,
        amount=amount,
        type=transaction_type,
        note=note,
        group_id=group_id
    )
    session.add(transaction)
    await session.flush()
    
    return transaction


async def get_balance(
    session: AsyncSession,
    debtor_id: int
) -> Decimal:
    """
    Calculate net balance for a debtor.
    Positive = owes us money, Negative = we owe them.
    
    Args:
        session: AsyncSession instance
        debtor_id: ID of the debtor
        
    Returns:
        Net balance as Decimal
    """
    result = await session.execute(
        select(func.sum(
            case(
                (Transaction.type == "DEBT", Transaction.amount),
                (Transaction.type == "CREDIT", -Transaction.amount),
                else_=0
            )
        )).where(Transaction.debtor_id == debtor_id)
    )
    balance = result.scalar()
    
    return balance or Decimal("0")


async def get_all_debtors_balance(
    session: AsyncSession,
    user_id: int
) -> List[Tuple[str, int, Decimal]]:
    """
    Get balance for all debtors of a user (optimized with GROUP BY).
    Only returns debtors with non-zero balance.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        
    Returns:
        List of (debtor_name, debtor_id, balance) tuples, sorted by balance descending.
        Positive balance = they owe us, Negative = we owe them.
    """
    # Optimized SQL with GROUP BY
    # SUM(CASE WHEN type='DEBT' THEN amount ELSE -amount END) as balance
    balance_expr = func.sum(
        case(
            (Transaction.type == "DEBT", Transaction.amount),
            (Transaction.type == "CREDIT", -Transaction.amount),
            else_=0
        )
    ).label("balance")
    
    result = await session.execute(
        select(
            Debtor.name,
            Debtor.id,
            balance_expr
        )
        .join(Transaction, Transaction.debtor_id == Debtor.id)
        .where(Debtor.user_id == user_id)
        .group_by(Debtor.id, Debtor.name)
        .having(balance_expr != 0)
        .order_by(balance_expr.desc())
    )
    
    rows = result.all()
    return [(row.name, row.id, row.balance) for row in rows]


async def get_transaction_history(
    session: AsyncSession,
    debtor_id: int,
    limit: int = 10
) -> List[Transaction]:
    """
    Get recent transaction history for a debtor.
    
    Args:
        session: AsyncSession instance
        debtor_id: ID of the debtor
        limit: Maximum number of transactions to return (default 10)
        
    Returns:
        List of Transaction objects, sorted by created_at DESC (newest first)
    """
    result = await session.execute(
        select(Transaction)
        .where(Transaction.debtor_id == debtor_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    
    return list(result.scalars().all())


async def get_transaction_with_owner_check(
    session: AsyncSession,
    user_id: int,
    transaction_id: int
) -> Optional[Transaction]:
    """
    Get a transaction with ownership verification.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        transaction_id: ID of the transaction
        
    Returns:
        Transaction if found and owned by user, None otherwise
    """
    result = await session.execute(
        select(Transaction)
        .join(Debtor, Transaction.debtor_id == Debtor.id)
        .where(
            (Transaction.id == transaction_id) &
            (Debtor.user_id == user_id)
        )
    )
    return result.scalar_one_or_none()


async def delete_transaction(
    session: AsyncSession,
    user_id: int,
    transaction_id: int
) -> bool:
    """
    Delete a single transaction with ownership verification.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        transaction_id: ID of the transaction to delete
        
    Returns:
        True if deleted, False if not found or not owned
    """
    transaction = await get_transaction_with_owner_check(session, user_id, transaction_id)
    
    if not transaction:
        return False
    
    await session.delete(transaction)
    return True


async def delete_debtor_and_history(
    session: AsyncSession,
    user_id: int,
    debtor_id: int
) -> bool:
    """
    Delete a debtor and all their transactions/aliases (via cascade).
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        debtor_id: ID of the debtor to delete
        
    Returns:
        True if deleted, False if not found or not owned
    """
    result = await session.execute(
        select(Debtor).where(
            (Debtor.id == debtor_id) &
            (Debtor.user_id == user_id)
        )
    )
    debtor = result.scalar_one_or_none()
    
    if not debtor:
        return False
    
    await session.delete(debtor)
    return True


async def delete_all_debt_for_user(
    session: AsyncSession,
    user_id: int
) -> int:
    """
    Delete all debtors (and their transactions/aliases) for a user.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        
    Returns:
        Number of debtors deleted
    """
    # First count how many will be deleted
    count_result = await session.execute(
        select(func.count(Debtor.id)).where(Debtor.user_id == user_id)
    )
    count = count_result.scalar() or 0
    
    if count > 0:
        # Delete all debtors for this user (cascade will handle transactions/aliases)
        await session.execute(
            delete(Debtor).where(Debtor.user_id == user_id)
        )
    
    return count


async def get_debtor_count_for_user(
    session: AsyncSession,
    user_id: int
) -> int:
    """
    Get the count of debtors for a user.
    
    Args:
        session: AsyncSession instance
        user_id: User ID
        
    Returns:
        Number of debtors
    """
    result = await session.execute(
        select(func.count(Debtor.id)).where(Debtor.user_id == user_id)
    )
    return result.scalar() or 0


__all__ = [
    "add_transaction",
    "get_balance",
    "get_all_debtors_balance",
    "get_transaction_history",
    "get_transaction_with_owner_check",
    "delete_transaction",
    "delete_debtor_and_history",
    "delete_all_debt_for_user",
    "get_debtor_count_for_user",
]
