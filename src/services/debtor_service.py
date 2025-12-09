"""
Debtor service - Manage debtor creation and retrieval with fuzzy search.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.database.models import Debtor, Alias
from thefuzz import fuzz
from typing import List, Tuple, Optional


async def get_or_create_debtor(
    session: AsyncSession,
    user_id: int,
    debtor_name: str
) -> Debtor:
    """
    Get existing debtor or create new one for a specific user.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        debtor_name: Name of the debtor
        
    Returns:
        Debtor instance (new or existing)
    """
    # Try to find existing debtor
    result = await session.execute(
        select(Debtor).where(
            (Debtor.user_id == user_id) &
            (Debtor.name == debtor_name)
        )
    )
    debtor = result.scalar_one_or_none()
    
    if debtor:
        return debtor
    
    # Create new debtor
    debtor = Debtor(
        user_id=user_id,
        name=debtor_name
    )
    session.add(debtor)
    await session.flush()  # Get ID without committing
    
    return debtor


async def get_or_create_debtor_by_telegram_id(
    session: AsyncSession,
    user_id: int,
    debtor_telegram_id: int,
    debtor_name: str,
    threshold: int = 80
) -> Debtor:
    """
    Get or create debtor by Telegram ID for group chat mentions.
    
    Priority order:
    1. Find by exact telegram_id match
    2. Find by fuzzy name match and update telegram_id if NULL
    3. Create new debtor with telegram_id
    
    Args:
        session: AsyncSession instance
        user_id: User ID (creditor)
        debtor_telegram_id: Telegram user ID of the mentioned person
        debtor_name: Display name from Telegram (first_name)
        threshold: Fuzzy match threshold (default 80% for stricter matching)
        
    Returns:
        Debtor instance (new or existing, with telegram_id set)
    """
    # Step 1: Find by telegram_id (most reliable)
    result = await session.execute(
        select(Debtor).where(
            (Debtor.user_id == user_id) &
            (Debtor.telegram_id == debtor_telegram_id)
        )
    )
    debtor = result.scalar_one_or_none()
    
    if debtor:
        # Update name if changed
        if debtor.name != debtor_name:
            debtor.name = debtor_name
        return debtor
    
    # Step 2: Try fuzzy match by name (for linking existing debtor to telegram_id)
    fuzzy_result = await search_debtors_fuzzy(
        session, user_id, debtor_name, threshold=threshold
    )
    
    if fuzzy_result:
        # Take the best match if score is high enough
        best_debtor, score = fuzzy_result[0]
        
        # Only link if the existing debtor doesn't have a telegram_id
        # (to avoid overwriting another person's ID)
        if best_debtor.telegram_id is None:
            best_debtor.telegram_id = debtor_telegram_id
            # Optionally update name to match Telegram display name
            # best_debtor.name = debtor_name
            return best_debtor
    
    # Step 3: Create new debtor with telegram_id
    debtor = Debtor(
        user_id=user_id,
        name=debtor_name,
        telegram_id=debtor_telegram_id
    )
    session.add(debtor)
    await session.flush()
    
    return debtor


async def search_debtors_fuzzy(
    session: AsyncSession,
    user_id: int,
    name_query: str,
    threshold: int = 60
) -> List[Tuple[Debtor, int]]:
    """
    Search for debtors using fuzzy matching.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        name_query: Name to search for
        threshold: Minimum similarity score (0-100), default 60%
        
    Returns:
        List of (Debtor, similarity_score) tuples, sorted by score descending.
        Only returns debtors with score >= threshold.
    """
    # Fetch all debtors for this user
    result = await session.execute(
        select(Debtor).where(Debtor.user_id == user_id)
    )
    debtors = result.scalars().all()
    
    # Apply fuzzy matching using multiple algorithms for better accuracy
    candidates = []
    query_lower = name_query.lower()
    for debtor in debtors:
        debtor_name_lower = debtor.name.lower()
        # Use multiple fuzz algorithms and take the highest score
        # fuzz.ratio: Standard Levenshtein distance ratio
        # fuzz.partial_ratio: Better for substring matching (e.g., "Tun" in "Tuan")
        # fuzz.token_sort_ratio: Good for reordered words (e.g., "Duy Khanh" vs "Khanh Duy")
        ratio_score = fuzz.ratio(query_lower, debtor_name_lower)
        partial_score = fuzz.partial_ratio(query_lower, debtor_name_lower)
        token_sort_score = fuzz.token_sort_ratio(query_lower, debtor_name_lower)
        
        # Take the maximum score from all algorithms
        score = max(ratio_score, partial_score, token_sort_score)
        
        if score >= threshold:
            candidates.append((debtor, score))
    
    # Sort by score (descending)
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    return candidates


async def add_alias(
    session: AsyncSession,
    user_id: int,
    alias_name: str,
    real_name: str
) -> Tuple[bool, str, Optional[Debtor]]:
    """
    Add an alias for a debtor.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        alias_name: The nickname to add
        real_name: The real debtor name (must exist)
        
    Returns:
        Tuple of (success, message, debtor_or_none)
    """
    # Check if debtor with real_name exists
    result = await session.execute(
        select(Debtor).where(
            (Debtor.user_id == user_id) &
            (Debtor.name.ilike(real_name))
        )
    )
    debtor = result.scalar_one_or_none()
    
    if not debtor:
        return (False, f"Không tìm thấy người tên \"{real_name}\" trong danh bạ.", None)
    
    # Check if alias already exists for this user
    existing_alias = await session.execute(
        select(Alias).join(Debtor).where(
            (Debtor.user_id == user_id) &
            (Alias.alias_name.ilike(alias_name))
        )
    )
    existing = existing_alias.scalar_one_or_none()
    
    if existing:
        return (False, f"Biệt danh \"{alias_name}\" đã được dùng cho người khác.", None)
    
    # Create new alias
    new_alias = Alias(
        debtor_id=debtor.id,
        alias_name=alias_name
    )
    session.add(new_alias)
    await session.flush()
    
    return (True, f"✅ Đã gán: \"{alias_name}\" là biệt danh của \"{debtor.name}\"", debtor)


async def get_debtor_by_alias(
    session: AsyncSession,
    user_id: int,
    alias_name: str
) -> Optional[Debtor]:
    """
    Find debtor by exact alias match.
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        alias_name: Alias to search for
        
    Returns:
        Debtor if found, None otherwise
    """
    result = await session.execute(
        select(Debtor).join(Alias).where(
            (Debtor.user_id == user_id) &
            (Alias.alias_name.ilike(alias_name))
        )
    )
    return result.scalar_one_or_none()


async def resolve_debtor(
    session: AsyncSession,
    user_id: int,
    name_query: str,
    threshold: int = 60
) -> Tuple[Optional[Debtor], List[Tuple[Debtor, int]], str]:
    """
    Resolve a name query to a debtor with priority:
    1. Exact alias match
    2. Exact debtor name match
    3. Fuzzy search (both aliases and names)
    
    Args:
        session: AsyncSession instance
        user_id: User ID (who is lending)
        name_query: Name/alias to search for
        threshold: Minimum fuzzy similarity score (0-100)
        
    Returns:
        Tuple of (exact_match_debtor, fuzzy_candidates, match_type)
        - If exact match found: (debtor, [], "alias"|"name")
        - If fuzzy matches found: (None, [(debtor, score)...], "fuzzy")
        - If no matches: (None, [], "none")
    """
    query_lower = name_query.lower().strip()
    
    # Step 1: Check exact alias match
    alias_result = await session.execute(
        select(Debtor).join(Alias).where(
            (Debtor.user_id == user_id) &
            (Alias.alias_name.ilike(name_query))
        )
    )
    alias_match = alias_result.scalar_one_or_none()
    if alias_match:
        return (alias_match, [], "alias")
    
    # Step 2: Check exact debtor name match
    name_result = await session.execute(
        select(Debtor).where(
            (Debtor.user_id == user_id) &
            (Debtor.name.ilike(name_query))
        )
    )
    name_match = name_result.scalar_one_or_none()
    if name_match:
        return (name_match, [], "name")
    
    # Step 3: Fuzzy search on both names and aliases
    # Fetch all debtors with their aliases
    result = await session.execute(
        select(Debtor)
        .options(selectinload(Debtor.aliases))
        .where(Debtor.user_id == user_id)
    )
    debtors = result.scalars().all()
    
    candidates = []
    seen_debtor_ids = set()
    
    for debtor in debtors:
        best_score = 0
        
        # Score against debtor name
        debtor_name_lower = debtor.name.lower()
        ratio_score = fuzz.ratio(query_lower, debtor_name_lower)
        partial_score = fuzz.partial_ratio(query_lower, debtor_name_lower)
        token_sort_score = fuzz.token_sort_ratio(query_lower, debtor_name_lower)
        name_score = max(ratio_score, partial_score, token_sort_score)
        best_score = max(best_score, name_score)
        
        # Score against aliases
        for alias in debtor.aliases:
            alias_lower = alias.alias_name.lower()
            ratio_score = fuzz.ratio(query_lower, alias_lower)
            partial_score = fuzz.partial_ratio(query_lower, alias_lower)
            token_sort_score = fuzz.token_sort_ratio(query_lower, alias_lower)
            alias_score = max(ratio_score, partial_score, token_sort_score)
            best_score = max(best_score, alias_score)
        
        if best_score >= threshold and debtor.id not in seen_debtor_ids:
            candidates.append((debtor, best_score))
            seen_debtor_ids.add(debtor.id)
    
    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    if candidates:
        return (None, candidates, "fuzzy")
    
    return (None, [], "none")


async def update_debtor_telegram_id(
    session: AsyncSession,
    debtor_id: int,
    telegram_id: int
) -> bool:
    """
    Update debtor's telegram_id for linking.
    
    Args:
        session: AsyncSession instance
        debtor_id: ID of the debtor
        telegram_id: Telegram ID to link
        
    Returns:
        True if successful, False if debtor not found
    """
    result = await session.execute(
        select(Debtor).where(Debtor.id == debtor_id)
    )
    debtor = result.scalar_one_or_none()
    
    if debtor:
        debtor.telegram_id = telegram_id
        return True
    return False


__all__ = [
    "get_or_create_debtor",
    "get_or_create_debtor_by_telegram_id",
    "search_debtors_fuzzy",
    "add_alias",
    "get_debtor_by_alias",
    "resolve_debtor",
    "update_debtor_telegram_id"
]
