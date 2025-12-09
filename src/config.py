"""
Configuration module - Load environment variables safely.
"""

import os
from dotenv import load_dotenv

# Load .env file if exists
load_dotenv()

# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_TOKEN in environment variables")

# Database URL (optional for now)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# Webhook URL (for Render deployment)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000")

# Server configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

# Rate limiting configuration
RATE_LIMIT_MAX_TOKENS = int(os.getenv("RATE_LIMIT_MAX_TOKENS", "60"))  # requests per minute
RATE_LIMIT_REFILL_SECONDS = int(os.getenv("RATE_LIMIT_REFILL_SECONDS", "60"))  # refill interval

# Webhook secret token for Telegram webhook verification
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN", "")

__all__ = [
    "TELEGRAM_TOKEN",
    "DATABASE_URL",
    "WEBHOOK_URL",
    "HOST",
    "PORT",
    "RATE_LIMIT_MAX_TOKENS",
    "RATE_LIMIT_REFILL_SECONDS",
    "WEBHOOK_SECRET_TOKEN",
]
