"""
Dashboard stats service - Statistics and analytics for web dashboard.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from src.database.models import Transaction, Debtor


@dataclass
class UserSummary:
    total_net_balance: Decimal
    total_positive: Decimal  # sum of balances > 0 (they owe us)
    total_negative: Decimal  # sum of balances < 0 (we owe them)
    debtor_count: int
    transaction_count: int


@dataclass
class DebtByPerson:
    debtor_id: int
    name: str
    balance: Decimal


@dataclass
class MonthlyTrend:
    month: str  # format: YYYY-MM
    net_change: Decimal


async def get_user_summary(session: AsyncSession, user_id: int) -> UserSummary:
    """Get complete debt summary for a user."""
    balance_expr = func.sum(
        case(
            (Transaction.type == "DEBT", Transaction.amount),
            (Transaction.type == "CREDIT", -Transaction.amount),
            else_=0
        )
    )

    debtor_balances_query = (
        select(
            Debtor.id,
            balance_expr.label("balance")
        )
        .outerjoin(Transaction, Transaction.debtor_id == Debtor.id)
        .where(Debtor.user_id == user_id)
        .group_by(Debtor.id)
    )

    result = await session.execute(debtor_balances_query)
    rows = result.all()

    total_net_balance = Decimal("0")
    total_positive = Decimal("0")
    total_negative = Decimal("0")
    debtor_count = len(rows)

    for row in rows:
        balance = row.balance or Decimal("0")
        total_net_balance += balance
        if balance > 0:
            total_positive += balance
        elif balance < 0:
            total_negative += abs(balance)

    transaction_count_result = await session.execute(
        select(func.count(Transaction.id))
        .join(Debtor, Transaction.debtor_id == Debtor.id)
        .where(Debtor.user_id == user_id)
    )
    transaction_count = transaction_count_result.scalar() or 0

    return UserSummary(
        total_net_balance=total_net_balance,
        total_positive=total_positive,
        total_negative=total_negative,
        debtor_count=debtor_count,
        transaction_count=transaction_count,
    )


async def get_debt_by_person(session: AsyncSession, user_id: int) -> List[DebtByPerson]:
    """Get debt breakdown by person (only non-zero balances, sorted by balance desc)."""
    balance_expr = func.sum(
        case(
            (Transaction.type == "DEBT", Transaction.amount),
            (Transaction.type == "CREDIT", -Transaction.amount),
            else_=0
        )
    ).label("balance")

    result = await session.execute(
        select(
            Debtor.id,
            Debtor.name,
            balance_expr
        )
        .join(Transaction, Transaction.debtor_id == Debtor.id)
        .where(Debtor.user_id == user_id)
        .group_by(Debtor.id, Debtor.name)
        .having(balance_expr != 0)
        .order_by(balance_expr.desc())
    )

    rows = result.all()
    return [
        DebtByPerson(debtor_id=row.id, name=row.name, balance=row.balance)
        for row in rows
    ]


async def get_transaction_history_for_user(
    session: AsyncSession,
    user_id: int,
    debtor_id: Optional[int] = None,
    limit: int = 50
) -> List[Transaction]:
    """Get transaction history for user, optionally filtered by debtor."""
    query = (
        select(Transaction)
        .join(Debtor, Transaction.debtor_id == Debtor.id)
        .where(Debtor.user_id == user_id)
    )

    if debtor_id is not None:
        query = query.where(Transaction.debtor_id == debtor_id)

    query = query.order_by(Transaction.created_at.desc()).limit(limit)

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_monthly_trends(
    session: AsyncSession,
    user_id: int,
    months: int = 12
) -> List[MonthlyTrend]:
    """Get monthly net changes for the last N months."""
    month_expr = func.strftime('%Y-%m', Transaction.created_at).label("month")
    
    net_change_expr = func.sum(
        case(
            (Transaction.type == "DEBT", Transaction.amount),
            (Transaction.type == "CREDIT", -Transaction.amount),
            else_=0
        )
    ).label("net_change")

    result = await session.execute(
        select(month_expr, net_change_expr)
        .join(Debtor, Transaction.debtor_id == Debtor.id)
        .where(Debtor.user_id == user_id)
        .group_by(month_expr)
        .order_by(month_expr.desc())
        .limit(months)
    )

    rows = result.all()
    return [
        MonthlyTrend(month=row.month, net_change=row.net_change)
        for row in rows
    ]


__all__ = [
    "UserSummary",
    "DebtByPerson",
    "MonthlyTrend",
    "get_user_summary",
    "get_debt_by_person",
    "get_transaction_history_for_user",
    "get_monthly_trends",
]
