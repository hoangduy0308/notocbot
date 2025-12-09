"""
Webhook authentication utilities for Telegram bot.
"""

import hmac
from fastapi import Request


def get_telegram_secret_from_headers(request: Request) -> str | None:
    """Read X-Telegram-Bot-Api-Secret-Token header from request."""
    return request.headers.get("X-Telegram-Bot-Api-Secret-Token")


def is_valid_telegram_secret(secret: str | None, expected: str) -> bool:
    """
    Validate Telegram secret token using timing-safe comparison.
    
    Returns True if:
    - expected is empty (webhook secret not configured)
    - secret matches expected using hmac.compare_digest
    """
    if not expected:
        return True
    if secret is None:
        return False
    return hmac.compare_digest(secret, expected)


def extract_user_id_from_update_dict(data: dict) -> int | None:
    """
    Extract user_id from Telegram update dictionary.
    
    Checks in order:
    - message.from.id
    - edited_message.from.id
    - callback_query.from.id
    """
    if "message" in data and "from" in data["message"]:
        return data["message"]["from"].get("id")
    
    if "edited_message" in data and "from" in data["edited_message"]:
        return data["edited_message"]["from"].get("id")
    
    if "callback_query" in data and "from" in data["callback_query"]:
        return data["callback_query"]["from"].get("id")
    
    return None
