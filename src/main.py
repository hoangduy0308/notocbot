"""
Main entry point for NoTocBot.
Supports both Polling (local) and Webhook (production) modes.

Mode selection based on WEBHOOK_URL environment variable:
- If WEBHOOK_URL is set -> Webhook mode (Production on Render)
- If WEBHOOK_URL is empty/not set -> Polling mode (Local development)
"""

import logging
import asyncio
import sys
import os
from contextlib import asynccontextmanager

from alembic.config import Config
from alembic import command

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from src.config import TELEGRAM_TOKEN, WEBHOOK_URL, HOST, PORT, WEBHOOK_SECRET_TOKEN
from src.security.webhook_auth import (
    get_telegram_secret_from_headers,
    is_valid_telegram_secret,
    extract_user_id_from_update_dict
)
from src.security.rate_limiter import is_allowed
from src.database.config import AsyncSessionLocal
from src.bot.handlers import (
    start_command, help_command, add_command, paid_command, 
    nlp_message_handler, button_callback_handler, alias_command,
    balance_command, summary_command, balance_callback_handler,
    history_command, history_callback_handler, link_command,
    delete_transaction_command, delete_debtor_command, delete_all_command,
    delete_callback_handler
)
from src.web.dashboard_router import router as dashboard_router

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Global application instance
ptb_app: Application = None


def run_migrations():
    """Run Alembic migrations automatically on startup."""
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("✅ Database migrations completed successfully")
    except Exception as e:
        logger.error(f"❌ Migration error: {e}")
        raise


def create_application() -> Application:
    """Create and configure the Telegram Bot application."""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("paid", paid_command))
    app.add_handler(CommandHandler("tra", paid_command))  # Vietnamese alias for /paid
    app.add_handler(CommandHandler("alias", alias_command))  # Story 2.3: Alias management
    app.add_handler(CommandHandler("link", link_command))    # Story 4.2: Link debtor to Telegram user
    app.add_handler(CommandHandler("balance", balance_command))  # Story 3.1: Balance inquiry
    app.add_handler(CommandHandler("summary", summary_command))  # Story 3.1: Summary
    app.add_handler(CommandHandler("history", history_command))  # Story 3.2: Transaction history
    app.add_handler(CommandHandler("log", history_command))  # Alias for /history
    
    # Delete commands
    app.add_handler(CommandHandler("xoagiaodich", delete_transaction_command))  # Delete single transaction
    app.add_handler(CommandHandler("xoano", delete_debtor_command))  # Delete debtor and all history
    app.add_handler(CommandHandler("xoatatca", delete_all_command))  # Delete all data
    
    # Register callback handlers for inline buttons
    app.add_handler(CallbackQueryHandler(balance_callback_handler, pattern=r"^bal_"))
    app.add_handler(CallbackQueryHandler(history_callback_handler, pattern=r"^hist_"))
    app.add_handler(CallbackQueryHandler(delete_callback_handler, pattern=r"^del_"))  # Delete confirmations
    app.add_handler(CallbackQueryHandler(button_callback_handler))  # Default for debtor selection
    
    # Register NLP message handler (natural language)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, nlp_message_handler))
    
    return app


# ==================== WEBHOOK MODE (Production) ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager - initialize and cleanup bot."""
    global ptb_app
    
    # Run migrations on startup
    run_migrations()
    
    ptb_app = create_application()
    await ptb_app.initialize()
    
    # Set webhook URL (must be HTTPS for Telegram)
    webhook_url = f"{WEBHOOK_URL}/webhook"
    
    try:
        await ptb_app.bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET_TOKEN if WEBHOOK_SECRET_TOKEN else None
        )
        logger.info(f"🚀 Bot started in WEBHOOK mode")
        logger.info(f"📡 Webhook URL: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Failed to set webhook: {e}")
        logger.info("⚠️ Bot will still accept webhook requests if URL is correct")
    
    await ptb_app.start()
    
    yield
    
    # Cleanup
    await ptb_app.stop()
    await ptb_app.shutdown()
    logger.info("Bot stopped.")


# Create FastAPI app (only used in webhook mode)
app = FastAPI(
    title="NoTocBot",
    description="Telegram Bot for debt management",
    lifespan=lifespan
)

# Include dashboard router and mount static files
app.include_router(dashboard_router)
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")


@app.post("/webhook")
async def webhook_handler(request: Request) -> Response:
    """Handle incoming Telegram updates via webhook."""
    try:
        # Step 1: Verify webhook secret (if configured)
        if WEBHOOK_SECRET_TOKEN:
            secret = get_telegram_secret_from_headers(request)
            if not is_valid_telegram_secret(secret, WEBHOOK_SECRET_TOKEN):
                logger.warning("Invalid or missing Telegram secret token on webhook")
                return Response(status_code=401)
        
        # Step 2: Parse update data
        data = await request.json()
        
        # Step 3: Check rate limit per user
        user_id = extract_user_id_from_update_dict(data)
        if user_id is not None:
            async with AsyncSessionLocal() as session:
                if not await is_allowed(user_id, session):
                    logger.info(f"Rate limit exceeded for user_id={user_id}")
                    return Response(status_code=429)
        
        # Step 4: Process the update
        update = Update.de_json(data, ptb_app.bot)
        await ptb_app.process_update(update)
        return Response(status_code=200)
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return Response(status_code=500)


@app.get("/health")
async def health_check():
    """Health check endpoint for Render."""
    return {"status": "healthy", "bot": "NoTocBot"}


@app.get("/api/bot-info")
async def get_bot_info():
    """Return bot username for Telegram Login Widget."""
    return {"bot_username": ptb_app.bot.username if ptb_app else None}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "NoTocBot is running!", "mode": "webhook"}


# ==================== POLLING MODE (Local Development) ====================

async def run_polling():
    """Run bot in polling mode for local development."""
    app = create_application()
    
    async with app:
        await app.initialize()
        await app.start()
        logger.info("🤖 Bot started in POLLING mode (local development)")
        logger.info("Press Ctrl+C to stop.")
        
        await app.updater.start_polling(
            allowed_updates=["message", "edited_message", "callback_query"]
        )
        
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Stopping bot...")
        finally:
            await app.updater.stop()
            await app.stop()


# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    # On Windows, use SelectorEventLoop for psycopg compatibility
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Check if WEBHOOK_URL is set (Production mode)
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    
    if webhook_url:
        # Production: Run with uvicorn (webhook mode)
        import uvicorn
        logger.info(f"Starting in WEBHOOK mode...")
        uvicorn.run(app, host=HOST, port=PORT)
    else:
        # Local: Run polling mode
        logger.info("Starting in POLLING mode (no WEBHOOK_URL set)...")
        asyncio.run(run_polling())
