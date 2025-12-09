"""
Rate limiter using token bucket algorithm.
"""

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.models import RateLimit
from src.config import RATE_LIMIT_MAX_TOKENS, RATE_LIMIT_REFILL_SECONDS


async def is_allowed(user_id: int, session: AsyncSession) -> bool:
    """
    Check if user is allowed to make a request using token bucket algorithm.
    
    - Get or create bucket for user_id
    - Refill tokens based on elapsed time
    - If tokens > 0: decrement and return True
    - If tokens <= 0: return False (rate limited)
    """
    stmt = select(RateLimit).where(RateLimit.user_id == user_id)
    result = await session.execute(stmt)
    bucket = result.scalar_one_or_none()
    
    now = datetime.utcnow()
    
    if bucket is None:
        bucket = RateLimit(
            user_id=user_id,
            tokens=RATE_LIMIT_MAX_TOKENS - 1,
            last_refill_at=now,
        )
        session.add(bucket)
        await session.commit()
        return True
    
    elapsed_seconds = (now - bucket.last_refill_at).total_seconds()
    refills = int(elapsed_seconds // RATE_LIMIT_REFILL_SECONDS)
    
    if refills > 0:
        bucket.tokens = min(RATE_LIMIT_MAX_TOKENS, bucket.tokens + refills * RATE_LIMIT_MAX_TOKENS)
        bucket.last_refill_at = now
    
    if bucket.tokens > 0:
        bucket.tokens -= 1
        await session.commit()
        return True
    
    await session.commit()
    return False
