"""
Callback handlers for NoTocBot.

Handles inline keyboard button callbacks.
"""

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select
from decimal import Decimal
from datetime import timedelta

from src.database.config import AsyncSessionLocal
from src.database.models import Debtor
from src.services.user_service import get_or_create_user
from src.services.debt_service import get_balance, get_transaction_history
from src.utils.formatters import format_currency

from .shared import (
    record_transaction,
    record_transaction_with_debtor_id,
)


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle callback queries from fuzzy search inline buttons.
    
    Callback data format:
    - For existing debtor: "debtor_{debtor_id}"
    - For creating new: "new_debtor"
    """
    query = update.callback_query
    await query.answer()
    
    pending = context.user_data.get("pending_transaction")
    if not pending:
        await query.edit_message_text(text="❌ Hết phiên làm việc, vui lòng thử lại.")
        return
    
    telegram_id = pending["telegram_id"]
    telegram_name = pending["telegram_name"]
    username = pending.get("username")
    amount = Decimal(pending["amount"])
    transaction_type = pending["transaction_type"]
    note = pending["note"]
    
    callback_data = query.data

    try:
        if callback_data.startswith("debtor_"):
            debtor_id = int(callback_data.split("_")[1])
            
            # Security: Verify debtor ownership before proceeding
            async with AsyncSessionLocal() as session:
                db_user = await get_or_create_user(
                    session,
                    telegram_id=telegram_id,
                    full_name=telegram_name
                )
                
                result = await session.execute(
                    select(Debtor).where(
                        (Debtor.id == debtor_id) &
                        (Debtor.user_id == db_user.id)
                    )
                )
                debtor = result.scalar_one_or_none()
                
                if not debtor:
                    await query.edit_message_text("❌ Không tìm thấy thông tin người nợ.")
                    context.user_data.pop("pending_transaction", None)
                    return
                
                debtor_name = debtor.name
            
            response = await record_transaction_with_debtor_id(
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                debtor_id=debtor_id,
                debtor_name=debtor_name,
                amount=amount,
                transaction_type=transaction_type,
                note=note,
                username=username,
                bot=context.bot
            )
            
        elif callback_data == "new_debtor":
            debtor_name = pending["name_query"]
            response = await record_transaction(
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                debtor_name=debtor_name,
                amount=amount,
                transaction_type=transaction_type,
                note=note,
                username=username,
                bot=context.bot
            )
        else:
            response = "❌ Lựa chọn không hợp lệ."
        
        await query.edit_message_text(text=response)
        context.user_data.pop("pending_transaction", None)
        
    except Exception as e:
        error_msg = f"❌ Lỗi: {str(e)}"
        await query.edit_message_text(text=error_msg)
        context.user_data.pop("pending_transaction", None)


async def balance_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle callback queries for balance inquiry buttons (bal_{debtor_id}).
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    if not callback_data.startswith("bal_"):
        return
    
    debtor_id = int(callback_data.split("_")[1])
    user = query.from_user
    
    try:
        async with AsyncSessionLocal() as session:
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
            )
            
            # Security: Verify ownership
            result = await session.execute(
                select(Debtor).where(
                    (Debtor.id == debtor_id) &
                    (Debtor.user_id == db_user.id)
                )
            )
            debtor = result.scalar_one_or_none()
            
            if not debtor:
                await query.edit_message_text("❌ Không tìm thấy thông tin.")
                return
            
            balance = await get_balance(session, debtor_id)
            
            if balance > 0:
                emoji = "🔴"
                msg = f"{emoji} **{debtor.name}** đang nợ bạn: **{format_currency(balance)}**"
            elif balance < 0:
                emoji = "🟢"
                msg = f"{emoji} Bạn đang nợ **{debtor.name}**: **{format_currency(-balance)}**"
            else:
                emoji = "✅"
                msg = f"{emoji} **{debtor.name}** không còn khoản nợ nào (0đ)"
            
            await query.edit_message_text(msg, parse_mode="Markdown")
            
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}")


async def history_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle callback queries for history inquiry buttons (hist_{debtor_id}).
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    if not callback_data.startswith("hist_"):
        return
    
    debtor_id = int(callback_data.split("_")[1])
    user = query.from_user
    
    try:
        async with AsyncSessionLocal() as session:
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
            )
            
            # Security: Verify ownership
            result = await session.execute(
                select(Debtor).where(
                    (Debtor.id == debtor_id) &
                    (Debtor.user_id == db_user.id)
                )
            )
            debtor = result.scalar_one_or_none()
            
            if not debtor:
                await query.edit_message_text("❌ Không tìm thấy thông tin.")
                return
            
            transactions = await get_transaction_history(session, debtor_id, limit=10)
            
            if not transactions:
                msg = f"📭 Chưa có giao dịch nào với **{debtor.name}**."
                await query.edit_message_text(msg, parse_mode="Markdown")
                return
            
            lines = [f"📜 **LỊCH SỬ GIAO DỊCH - {debtor.name}**\n"]
            
            for tx in transactions:
                tx_date = tx.created_at + timedelta(hours=7)
                date_str = tx_date.strftime("%d/%m/%Y %H:%M")
                
                if tx.type == "DEBT":
                    emoji = "🔴"
                    amount_str = f"+{format_currency(tx.amount)}"
                else:
                    emoji = "🟢"
                    amount_str = f"-{format_currency(tx.amount)}"
                
                note_str = f" ({tx.note})" if tx.note else ""
                lines.append(f"{emoji} `{date_str}` {amount_str}{note_str}")
            
            balance = await get_balance(session, debtor_id)
            lines.append("\n" + "─" * 25)
            if balance > 0:
                lines.append(f"💰 **Dư nợ hiện tại: {format_currency(balance)}**")
            elif balance < 0:
                lines.append(f"💸 **Bạn đang nợ: {format_currency(-balance)}**")
            else:
                lines.append(f"✅ **Hết nợ!**")
            
            msg = "\n".join(lines)
            await query.edit_message_text(msg, parse_mode="Markdown")
            
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi: {str(e)}")


__all__ = [
    "button_callback_handler",
    "balance_callback_handler",
    "history_callback_handler",
]
