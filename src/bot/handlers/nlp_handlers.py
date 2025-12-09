"""
NLP message handlers for NoTocBot.

Handles natural language message parsing and processing.
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from decimal import Decimal
from datetime import datetime

from src.database.config import AsyncSessionLocal
from src.services.user_service import get_or_create_user
from src.services.debtor_service import resolve_debtor
from src.utils.formatters import parse_amount
from src.bot.nlp_engine import NLPEngine
from src.bot.date_parser_vi import extract_due_date_from_note

from .shared import (
    record_transaction,
    record_transaction_with_debtor_id,
    show_summary,
    show_individual_balance,
    show_history,
)


async def nlp_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle natural language messages for debt/credit recording and inquiries.
    Uses resolve_debtor with priority: Alias Exact > Name Exact > Fuzzy
    
    Supported patterns:
    - Debt: "Name nợ/vay/muộn Amount [Note]"
    - Credit: "Name trả/đưa/bù Amount [Note]"
    - Balance inquiry: "Duy nợ bao nhiêu", "xem nợ Duy"
    - Summary: "tổng nợ", "ai đang nợ tôi"
    
    Example:
    - "Tuấn nợ 50k tiền cơm"
    - "Béo trả 20000" (where Béo is alias of Tuấn)
    - "Duy nợ bao nhiêu"
    - "tổng nợ"
    - "lịch sử Tuan"
    """
    text = update.message.text.strip()
    user = update.effective_user
    
    # First, try to parse inquiry (balance/summary/history)
    inquiry_result = NLPEngine.parse_inquiry(text)
    if inquiry_result:
        inquiry_type, name = inquiry_result
        if inquiry_type == "SUMMARY":
            await show_summary(update, user)
            return
        elif inquiry_type == "BALANCE" and name:
            await show_individual_balance(update, user, name)
            return
        elif inquiry_type == "HISTORY" and name:
            await show_history(update, user, name)
            return
    
    # Try to parse transaction message (debt/credit)
    parse_result = NLPEngine.parse_message(text)
    
    if not parse_result:
        # No match - do nothing (fallback)
        return
    
    transaction_type, debtor_name, amount_str, note = parse_result
    
    # Extract due date from note if present
    due_date = None
    if note:
        clean_note, due_date = extract_due_date_from_note(note, datetime.now())
        note = clean_note if clean_note else None
    
    # Parse and validate amount
    try:
        amount = parse_amount(amount_str)
    except ValueError as e:
        error_msg = f"❌ Không hiểu số tiền: {amount_str}\n\nHỗ trợ: `50k`, `50.000`, `50,000`"
        await update.message.reply_text(error_msg)
        return
    
    try:
        async with AsyncSessionLocal() as session:
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
            )
            
            # Resolve debtor using priority: Alias Exact > Name Exact > Fuzzy
            exact_match, candidates, match_type = await resolve_debtor(
                session,
                user_id=db_user.id,
                name_query=debtor_name,
                threshold=60
            )
            
            if exact_match:
                # Found exact match (by alias or name) - proceed directly
                response = await record_transaction_with_debtor_id(
                    telegram_id=user.id,
                    telegram_name=user.first_name or "Unknown",
                    debtor_id=exact_match.id,
                    debtor_name=exact_match.name,
                    amount=amount,
                    transaction_type=transaction_type,
                    note=note,
                    username=user.username,
                    bot=context.bot,
                    due_date=due_date,
                )
                # If matched by alias, show which real name was used
                if match_type == "alias":
                    response = f"(Alias \"{debtor_name}\" → {exact_match.name})\n\n{response}"
                await update.message.reply_text(response)
                
            elif len(candidates) > 0:
                # Found fuzzy matches - show buttons for user to choose
                buttons = []
                candidates_dict = {}
                
                for idx, (debtor, score) in enumerate(candidates[:5], 1):
                    buttons.append([
                        InlineKeyboardButton(
                            f"{idx}. {debtor.name} ({score}%)",
                            callback_data=f"debtor_{debtor.id}"
                        )
                    ])
                    candidates_dict[str(debtor.id)] = {
                        "name": debtor.name,
                        "score": score
                    }
                
                buttons.append([
                    InlineKeyboardButton(
                        f"➕ Tạo mới \"{debtor_name}\"",
                        callback_data="new_debtor"
                    )
                ])
                
                keyboard = InlineKeyboardMarkup(buttons)
                
                context.user_data["pending_transaction"] = {
                    "telegram_id": user.id,
                    "telegram_name": user.first_name or "Unknown",
                    "username": user.username,
                    "name_query": debtor_name,
                    "amount": str(amount),
                    "transaction_type": transaction_type,
                    "note": note,
                    "candidates": candidates_dict,
                    "due_date": due_date.isoformat() if due_date else None,
                }
                
                action_text = "ghi nợ" if transaction_type == "DEBT" else "ghi nhận trả tiền"
                msg = f"🔍 Tôi tìm thấy những tên gần giống \"{debtor_name}\":\n\nBạn muốn {action_text} cho ai?"
                await update.message.reply_text(msg, reply_markup=keyboard)
                
            else:
                # No matches - create new debtor directly
                response = await record_transaction(
                    telegram_id=user.id,
                    telegram_name=user.first_name or "Unknown",
                    debtor_name=debtor_name,
                    amount=amount,
                    transaction_type=transaction_type,
                    note=note,
                    username=user.username,
                    bot=context.bot,
                    due_date=due_date,
                )
                await update.message.reply_text(response)
                
    except Exception as e:
        error_msg = f"❌ Lỗi: {str(e)}"
        await update.message.reply_text(error_msg)


__all__ = [
    "nlp_message_handler",
]
