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

__all__ = [
    "TELEGRAM_TOKEN",
    "DATABASE_URL",
    "WEBHOOK_URL",
    "HOST",
    "PORT",
]
