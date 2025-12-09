"""
Security module for NoTocBot.
Provides webhook authentication and rate limiting.
"""

from src.security.webhook_auth import (
    get_telegram_secret_from_headers,
    is_valid_telegram_secret,
    extract_user_id_from_update_dict,
)
from src.security.rate_limiter import is_allowed

__all__ = [
    "get_telegram_secret_from_headers",
    "is_valid_telegram_secret",
    "extract_user_id_from_update_dict",
    "is_allowed",
]
