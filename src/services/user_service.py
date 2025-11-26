"""
User service - Manage user creation and retrieval.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.models import User


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    full_name: str
) -> User:
    """
    Get existing user or create new one.
    
    Args:
        session: AsyncSession instance
        telegram_id: Telegram user ID
        full_name: User's full name
        
    Returns:
        User instance (new or existing)
    """
    # Try to find existing user
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        return user
    
    # Create new user
    user = User(
        telegram_id=telegram_id,
        full_name=full_name
    )
    session.add(user)
    await session.flush()  # Get ID without committing
    
    return user


__all__ = ["get_or_create_user"]
