"""
User service - Manage user creation and retrieval.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.models import User


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    full_name: str,
    username: Optional[str] = None
) -> User:
    """
    Get existing user or create new one.
    Updates username if changed.
    
    Args:
        session: AsyncSession instance
        telegram_id: Telegram user ID
        full_name: User's full name
        username: Telegram @username (optional)
        
    Returns:
        User instance (new or existing)
    """
    # Try to find existing user
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Update username if changed
        if username and user.username != username:
            user.username = username
        # Update full_name if changed
        if user.full_name != full_name:
            user.full_name = full_name
        return user
    
    # Create new user
    user = User(
        telegram_id=telegram_id,
        full_name=full_name,
        username=username
    )
    session.add(user)
    await session.flush()  # Get ID without committing
    
    return user


async def get_user_by_username(
    session: AsyncSession,
    username: str
) -> Optional[User]:
    """
    Find user by Telegram username.
    
    Args:
        session: AsyncSession instance
        username: Telegram username (without @)
        
    Returns:
        User instance or None
    """
    # Remove @ if present
    clean_username = username.lstrip('@')
    
    result = await session.execute(
        select(User).where(User.username == clean_username)
    )
    return result.scalar_one_or_none()


__all__ = ["get_or_create_user", "get_user_by_username"]
