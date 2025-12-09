"""
Web authentication service for Telegram Login Widget and JWT sessions.
"""

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Optional

import os

import jwt


@dataclass
class TelegramLoginData:
    """Data structure for Telegram Login Widget payload."""
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int = 0
    hash: str = ""


class TelegramLoginError(Exception):
    """Raised when Telegram login verification fails."""
    pass


class SessionTokenError(Exception):
    """Raised when session token verification fails."""
    pass


def verify_telegram_login(
    data: dict,
    bot_token: str | None = None,
    max_age_seconds: int = 300
) -> TelegramLoginData:
    """
    Verify Telegram Login Widget data.
    
    Algorithm:
    1. Build data_check_string from sorted key=value pairs (excluding 'hash')
    2. secret_key = SHA256(bot_token)
    3. computed_hash = HMAC_SHA256(secret_key, data_check_string).hexdigest()
    4. Compare computed_hash with data.hash
    5. Check auth_date is not expired
    
    Returns TelegramLoginData if valid.
    Raises ValueError if invalid.
    """
    if bot_token is None:
        bot_token = os.getenv("TELEGRAM_TOKEN", "")
    
    if "id" not in data:
        raise ValueError("Missing required field: id")
    
    if "first_name" not in data:
        raise ValueError("Missing required field: first_name")
    
    if "auth_date" not in data:
        raise ValueError("Missing required field: auth_date")
    
    if "hash" not in data:
        raise ValueError("Missing required field: hash")
    
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"
    )
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(computed_hash, data["hash"]):
        raise ValueError("Invalid hash - data verification failed")
    
    auth_date = int(data["auth_date"])
    current_time = int(time.time())
    if current_time - auth_date > max_age_seconds:
        raise ValueError("Expired auth_date - login data too old")
    
    return TelegramLoginData(
        id=int(data["id"]),
        first_name=data["first_name"],
        last_name=data.get("last_name"),
        username=data.get("username"),
        photo_url=data.get("photo_url"),
        auth_date=auth_date,
        hash=data["hash"],
    )


def create_session_token(
    user_data: TelegramLoginData,
    secret_key: str | None = None,
    expires_in_seconds: int = 86400
) -> str:
    """
    Create JWT token for web session.
    
    Args:
        user_data: Telegram user data
        secret_key: JWT secret key (defaults to JWT_SECRET from config)
        expires_in_seconds: Token expiry time in seconds (default 24 hours)
    
    Returns:
        JWT token string
    """
    if secret_key is None:
        secret_key = os.getenv("JWT_SECRET", "your-default-secret-key-change-in-production")
    
    payload = {
        "user_id": user_data.id,
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        "username": user_data.username,
        "photo_url": user_data.photo_url,
        "exp": int(time.time()) + expires_in_seconds,
        "iat": int(time.time()),
    }
    
    return jwt.encode(payload, secret_key, algorithm="HS256")


def verify_session_token(token: str, secret_key: str | None = None) -> dict:
    """
    Verify and decode JWT token.
    
    Args:
        token: JWT token string
        secret_key: JWT secret key (defaults to JWT_SECRET from config)
    
    Returns:
        Payload dict with user_id, first_name, username, etc.
    
    Raises:
        ValueError if invalid or expired.
    """
    if secret_key is None:
        secret_key = os.getenv("JWT_SECRET", "your-default-secret-key-change-in-production")
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Expired token")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
