"""
Shared utilities for bot handlers.

Contains transaction recording logic and display helpers used across
commands, callbacks, and NLP handlers.
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from datetime import datetime, timedelta

from src.database.config import AsyncSessionLocal
from src.database.models import Debtor
from src.services.user_service import get_or_create_user
from src.services.debtor_service import (
    get_or_create_debtor,
    search_debtors_fuzzy,
    resolve_debtor,
)
from src.services.debt_service import (
    add_transaction,
    get_balance,
    get_all_debtors_balance,
    get_transaction_history,
)
from src.utils.formatters import format_currency, format_due_date_relative
from typing import List, Tuple


def format_debt_summary(balances: List[Tuple[str, int, Decimal]]) -> str:
    """
    Format a debt summary from balance data.
    
    Args:
        balances: List of (debtor_name, debtor_id, balance) tuples
        
    Returns:
        Formatted summary string
    """
    if not balances:
        return ""
    
    lines = ["📊 **TỔNG KẾT NỢ**\n"]
    total_owed_to_us = Decimal("0")
    total_we_owe = Decimal("0")
    
    for name, debtor_id, balance in balances:
        if balance > 0:
            emoji = "🔴"
            total_owed_to_us += balance
            lines.append(f"{emoji} {name}: {format_currency(balance)}")
        else:
            emoji = "🟢"
            total_we_owe += abs(balance)
            lines.append(f"{emoji} {name}: -{format_currency(abs(balance))}")
    
    lines.append("\n" + "─" * 25)
    if total_owed_to_us > 0:
        lines.append(f"🔴 Tổng người khác nợ bạn: **{format_currency(total_owed_to_us)}**")
    if total_we_owe > 0:
        lines.append(f"🟢 Tổng bạn nợ người khác: **{format_currency(total_we_owe)}**")
    
    net = total_owed_to_us - total_we_owe
    if net > 0:
        lines.append(f"\n💰 **Ròng: +{format_currency(net)}** (bạn được nhận)")
    elif net < 0:
        lines.append(f"\n💸 **Ròng: -{format_currency(abs(net))}** (bạn phải trả)")
    else:
        lines.append(f"\n⚖️ **Ròng: 0đ** (cân bằng)")
    
    return "\n".join(lines)


async def record_transaction_with_debtor_id(
    telegram_id: int,
    telegram_name: str,
    debtor_id: int,
    debtor_name: str,
    amount: Decimal,
    transaction_type: str,
    note: str = None,
    username: str = None,
    bot=None,
    due_date: datetime = None,
) -> str:
    """
    Record transaction using an existing debtor ID.
    
    Args:
        telegram_id: Telegram user ID
        telegram_name: Telegram user name
        debtor_id: Debtor ID (already validated)
        debtor_name: Name of debtor (for display)
        amount: Transaction amount (positive)
        transaction_type: "DEBT" or "CREDIT"
        note: Optional note
        username: Telegram @username (optional)
        bot: Telegram Bot instance (optional, for sending notifications)
        due_date: Optional deadline for payment
        
    Returns:
        Formatted response message
    """
    async with AsyncSessionLocal() as session:
        # Step 1: Get or create user
        db_user = await get_or_create_user(
            session,
            telegram_id=telegram_id,
            full_name=telegram_name,
            username=username
        )
        
        # Step 2: Add transaction directly with provided debtor_id
        await add_transaction(
            session,
            debtor_id=debtor_id,
            amount=amount,
            transaction_type=transaction_type,
            note=note,
            due_date=due_date,
        )
        
        # Step 3: Get updated balance
        balance = await get_balance(session, debtor_id)
        
        # Step 4: Get all balances for summary
        all_balances = await get_all_debtors_balance(session, db_user.id)
        
        # Step 5: Check for notification (if bot is provided)
        if bot:
            result = await session.execute(select(Debtor).where(Debtor.id == debtor_id))
            debtor = result.scalar_one_or_none()
            
            if debtor and debtor.telegram_id:
                try:
                    formatted_amount = format_currency(amount)
                    reason = f". Lý do: {note}" if note else ""
                    
                    if transaction_type == "DEBT":
                        notify_msg = f"🔔 **{telegram_name}** vừa ghi nợ cho bạn: {formatted_amount}{reason}"
                    else:
                        notify_msg = f"🔔 **{telegram_name}** vừa ghi nhận bạn trả: {formatted_amount}{reason}"
                        
                    await bot.send_message(chat_id=debtor.telegram_id, text=notify_msg, parse_mode="Markdown")
                except Exception as e:
                    print(f"Failed to send notification: {e}")
        
        # Commit all changes
        await session.commit()
    
    # Format response
    formatted_amount = format_currency(amount)
    note_text = f" ({note})" if note else ""
    balance_text = format_currency(balance)
    
    if transaction_type == "DEBT":
        msg = f"✅ Đã ghi nợ {debtor_name}: {formatted_amount}{note_text}"
    else:  # CREDIT
        msg = f"✅ Đã ghi nhận {debtor_name} trả: {formatted_amount}{note_text}"
    
    # Add balance info
    if balance > 0:
        balance_msg = f"Dư nợ còn lại: {balance_text}"
    elif balance < 0:
        balance_msg = f"Chúng ta còn nợ: {format_currency(-balance)}"
    else:
        balance_msg = "Hết nợ! 🎉"
    
    response = f"{msg}\n\n{balance_msg}"
    
    if due_date:
        deadline_str = format_due_date_relative(due_date)
        response += f"\n⏰ Hạn trả: {deadline_str}"
    
    if all_balances:
        summary = format_debt_summary(all_balances)
        response += f"\n\n{summary}"
    
    return response


async def record_transaction(
    telegram_id: int,
    telegram_name: str,
    debtor_name: str,
    amount: Decimal,
    transaction_type: str,
    note: str = None,
    username: str = None,
    bot=None,
    due_date: datetime = None,
) -> str:
    """
    Unified transaction recording logic (for both /add and /paid commands).
    
    Args:
        telegram_id: Telegram user ID
        telegram_name: Telegram user name
        debtor_name: Name of debtor
        amount: Transaction amount (positive)
        transaction_type: "DEBT" or "CREDIT"
        note: Optional note
        username: str = None
        bot: Telegram Bot instance (optional, for sending notifications)
        due_date: Optional deadline for payment
        
    Returns:
        Formatted response message
        
    Raises:
        Exception: If database operation fails
    """
    async with AsyncSessionLocal() as session:
        # Step 1: Get or create user
        db_user = await get_or_create_user(
            session,
            telegram_id=telegram_id,
            full_name=telegram_name,
            username=username
        )
        
        # Step 2: Get or create debtor
        debtor = await get_or_create_debtor(
            session,
            user_id=db_user.id,
            debtor_name=debtor_name
        )
        
        # Step 3: Add transaction
        await add_transaction(
            session,
            debtor_id=debtor.id,
            amount=amount,
            transaction_type=transaction_type,
            note=note,
            due_date=due_date,
        )
        
        # Step 4: Get updated balance
        balance = await get_balance(session, debtor.id)
        
        # Step 5: Get all balances for summary
        all_balances = await get_all_debtors_balance(session, db_user.id)
        
        # Step 6: Check for notification (if bot is provided)
        if bot and debtor.telegram_id:
            try:
                formatted_amount = format_currency(amount)
                reason = f". Lý do: {note}" if note else ""
                
                if transaction_type == "DEBT":
                    notify_msg = f"🔔 **{telegram_name}** vừa ghi nợ cho bạn: {formatted_amount}{reason}"
                else:
                    notify_msg = f"🔔 **{telegram_name}** vừa ghi nhận bạn trả: {formatted_amount}{reason}"
                    
                await bot.send_message(chat_id=debtor.telegram_id, text=notify_msg, parse_mode="Markdown")
            except Exception as e:
                print(f"Failed to send notification: {e}")
        
        # Commit all changes
        await session.commit()
    
    # Format response
    formatted_amount = format_currency(amount)
    note_text = f" ({note})" if note else ""
    balance_text = format_currency(balance)
    
    if transaction_type == "DEBT":
        msg = f"✅ Đã ghi nợ {debtor_name}: {formatted_amount}{note_text}"
    else:  # CREDIT
        msg = f"✅ Đã ghi nhận {debtor_name} trả: {formatted_amount}{note_text}"
    
    # Add balance info
    if balance > 0:
        balance_msg = f"Dư nợ còn lại: {balance_text}"
    elif balance < 0:
        balance_msg = f"Chúng ta còn nợ: {format_currency(-balance)}"
    else:
        balance_msg = "Hết nợ! 🎉"
    
    response = f"{msg}\n\n{balance_msg}"
    
    if due_date:
        deadline_str = format_due_date_relative(due_date)
        response += f"\n⏰ Hạn trả: {deadline_str}"
    
    if all_balances:
        summary = format_debt_summary(all_balances)
        response += f"\n\n{summary}"
    
    return response


async def show_individual_balance(update: Update, user, debtor_name: str) -> None:
    """
    Show balance for a specific debtor (with fuzzy/alias support).
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get user
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
                # Found exact match - show balance
                balance = await get_balance(session, exact_match.id)
                
                if balance > 0:
                    emoji = "🔴"  # They owe us
                    msg = f"{emoji} **{exact_match.name}** đang nợ bạn: **{format_currency(balance)}**"
                elif balance < 0:
                    emoji = "🟢"  # We owe them
                    msg = f"{emoji} Bạn đang nợ **{exact_match.name}**: **{format_currency(-balance)}**"
                else:
                    emoji = "✅"
                    msg = f"{emoji} **{exact_match.name}** không còn khoản nợ nào (0đ)"
                
                # If matched by alias, show which alias was used
                if match_type == "alias":
                    msg = f"(Alias \"{debtor_name}\" → {exact_match.name})\n\n{msg}"
                
                await update.message.reply_text(msg, parse_mode="Markdown")
                
            elif len(candidates) > 0:
                # Found fuzzy matches - show buttons for user to choose
                buttons = []
                for idx, (debtor, score) in enumerate(candidates[:5], 1):
                    buttons.append([
                        InlineKeyboardButton(
                            f"{idx}. {debtor.name} ({score}%)",
                            callback_data=f"bal_{debtor.id}"
                        )
                    ])
                
                keyboard = InlineKeyboardMarkup(buttons)
                msg = f"🔍 Không tìm thấy \"{debtor_name}\" chính xác.\n\nBạn muốn xem số dư của ai?"
                await update.message.reply_text(msg, reply_markup=keyboard)
                
            else:
                await update.message.reply_text(f"❌ Không tìm thấy \"{debtor_name}\" trong danh bạ.")
                
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")


async def show_summary(update: Update, user) -> None:
    """
    Show summary of all debtors with non-zero balance.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
            )
            
            # Get all debtors with non-zero balance
            balances = await get_all_debtors_balance(session, db_user.id)
            
            if not balances:
                await update.message.reply_text("✅ Bạn không có khoản nợ nào đang ghi nhận.")
                return
            
            msg = format_debt_summary(balances)
            await update.message.reply_text(msg, parse_mode="Markdown")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")


async def show_history(update: Update, user, debtor_name: str) -> None:
    """
    Show transaction history for a specific debtor (with fuzzy/alias support).
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get user
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
                # Found exact match - show history
                transactions = await get_transaction_history(session, exact_match.id, limit=10)
                
                if not transactions:
                    msg = f"📭 Chưa có giao dịch nào với **{exact_match.name}**."
                    await update.message.reply_text(msg, parse_mode="Markdown")
                    return
                
                # Build formatted message
                lines = [f"📜 **LỊCH SỬ GIAO DỊCH - {exact_match.name}**\n"]
                
                # If matched by alias, show which alias was used
                if match_type == "alias":
                    lines.insert(0, f"(Alias \"{debtor_name}\" → {exact_match.name})\n")
                
                for tx in transactions:
                    # Format date (convert UTC to Vietnam time +7)
                    tx_date = tx.created_at + timedelta(hours=7)
                    date_str = tx_date.strftime("%d/%m/%Y %H:%M")
                    
                    # Emoji and amount
                    if tx.type == "DEBT":
                        emoji = "🔴"
                        amount_str = f"+{format_currency(tx.amount)}"
                    else:  # CREDIT
                        emoji = "🟢"
                        amount_str = f"-{format_currency(tx.amount)}"
                    
                    # Note
                    note_str = f" ({tx.note})" if tx.note else ""
                    
                    lines.append(f"{emoji} `{date_str}` {amount_str}{note_str}")
                
                # Add current balance
                balance = await get_balance(session, exact_match.id)
                lines.append("\n" + "─" * 25)
                if balance > 0:
                    lines.append(f"💰 **Dư nợ hiện tại: {format_currency(balance)}**")
                elif balance < 0:
                    lines.append(f"💸 **Bạn đang nợ: {format_currency(-balance)}**")
                else:
                    lines.append(f"✅ **Hết nợ!**")
                
                msg = "\n".join(lines)
                await update.message.reply_text(msg, parse_mode="Markdown")
                
            elif len(candidates) > 0:
                # Found fuzzy matches - show buttons for user to choose
                buttons = []
                for idx, (debtor, score) in enumerate(candidates[:5], 1):
                    buttons.append([
                        InlineKeyboardButton(
                            f"{idx}. {debtor.name} ({score}%)",
                            callback_data=f"hist_{debtor.id}"
                        )
                    ])
                
                keyboard = InlineKeyboardMarkup(buttons)
                msg = f"🔍 Không tìm thấy \"{debtor_name}\" chính xác.\n\nBạn muốn xem lịch sử của ai?"
                await update.message.reply_text(msg, reply_markup=keyboard)
                
            else:
                await update.message.reply_text(f"❌ Không tìm thấy \"{debtor_name}\" trong danh bạ.")
                
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")


__all__ = [
    "format_debt_summary",
    "record_transaction",
    "record_transaction_with_debtor_id",
    "show_summary",
    "show_individual_balance",
    "show_history",
]
