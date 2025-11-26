"""
Bot command handlers for NoTocBot.
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
import json
import re

from src.database.config import AsyncSessionLocal
from src.services.user_service import get_or_create_user
from src.services.debtor_service import get_or_create_debtor, search_debtors_fuzzy, add_alias, resolve_debtor
from src.services.debt_service import add_transaction, get_balance, get_all_debtors_balance, get_transaction_history
from src.utils.formatters import parse_amount, format_currency
from src.bot.nlp_engine import NLPEngine
from datetime import datetime, timedelta


async def record_transaction_with_debtor_id(
    telegram_id: int,
    telegram_name: str,
    debtor_id: int,
    debtor_name: str,
    amount: Decimal,
    transaction_type: str,
    note: str = None
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
        
    Returns:
        Formatted response message
    """
    async with AsyncSessionLocal() as session:
        # Step 1: Get or create user
        db_user = await get_or_create_user(
            session,
            telegram_id=telegram_id,
            full_name=telegram_name
        )
        
        # Step 2: Add transaction directly with provided debtor_id
        await add_transaction(
            session,
            debtor_id=debtor_id,
            amount=amount,
            transaction_type=transaction_type,
            note=note
        )
        
        # Step 3: Get updated balance
        balance = await get_balance(session, debtor_id)
        
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
    
    return f"{msg}\n\n{balance_msg}"


async def record_transaction(
    telegram_id: int,
    telegram_name: str,
    debtor_name: str,
    amount: Decimal,
    transaction_type: str,
    note: str = None
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
            full_name=telegram_name
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
            note=note
        )
        
        # Step 4: Get updated balance
        balance = await get_balance(session, debtor.id)
        
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
    
    return f"{msg}\n\n{balance_msg}"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command - Register user and send welcome message.
    """
    user = update.effective_user
    
    # Register user in database
    async with AsyncSessionLocal() as session:
        await get_or_create_user(
            session,
            telegram_id=user.id,
            full_name=user.first_name or "Unknown"
        )
        await session.commit()
    
    message = f"Xin chào {user.first_name}! Tôi là NoTocBot. Gõ /help để xem hướng dẫn."
    await update.message.reply_text(message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /help command - Show usage instructions.
    """
    help_text = """
📖 **Hướng dẫn sử dụng NoTocBot:**

/start - Bắt đầu sử dụng bot
/help - Xem hướng dẫn này
/add - Ghi lại một khoản nợ
/balance - Xem số dư của một người
/history - Xem lịch sử giao dịch

**Cú pháp /add:** `/add [Tên người] [Số tiền] [Ghi chú (tùy chọn)]`

**Ví dụ:**
- `/add Khánh Duy 50k tien cafe`
- `/add Tuấn 100000`
- `/add Minh 20k`

**Hỗ trợ định dạng tiền:**
- `50k` = 50.000 đồng
- `50000` = 50.000 đồng
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /add command - Record a debt transaction with fuzzy search.
    
    Format: /add [Name] [Amount] [Note (optional)]
    Example: /add Khánh Duy 50k tien cafe
    """
    user = update.effective_user
    
    # Validate arguments
    if not context.args or len(context.args) < 2:
        error_msg = """❌ Cú pháp /add không đúng!

Cách dùng: `/add [Tên người] [Số tiền] [Ghi chú (tùy chọn)]`

Ví dụ: `/add Khánh Duy 50k tien cafe`"""
        await update.message.reply_text(error_msg)
        return
    
    # Parse arguments
    debtor_name = context.args[0]
    amount_str = context.args[1]
    note = " ".join(context.args[2:]) if len(context.args) > 2 else None
    
    # Parse and validate amount
    try:
        amount = parse_amount(amount_str)
    except ValueError as e:
        error_msg = f"❌ Lỗi định dạng tiền: {e}\n\nHỗ trợ: `50k` hoặc `50000`"
        await update.message.reply_text(error_msg)
        return
    
    try:
        async with AsyncSessionLocal() as session:
            # Get or create user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown"
            )
            
            # Search for fuzzy matches
            candidates = await search_debtors_fuzzy(
                session,
                user_id=db_user.id,
                name_query=debtor_name,
                threshold=60
            )
            
            # Check for exact match
            exact_match = None
            for debtor, score in candidates:
                if score == 100:  # Exact match
                    exact_match = debtor
                    break
            
            if exact_match:
                # Found exact match - proceed directly
                response = await record_transaction_with_debtor_id(
                    telegram_id=user.id,
                    telegram_name=user.first_name or "Unknown",
                    debtor_id=exact_match.id,
                    debtor_name=exact_match.name,
                    amount=amount,
                    transaction_type="DEBT",
                    note=note
                )
                await update.message.reply_text(response)
                
            elif len(candidates) > 0:
                # Found fuzzy matches - show buttons
                buttons = []
                candidates_dict = {}
                
                # Add matching debtors as buttons
                for idx, (debtor, score) in enumerate(candidates[:5], 1):  # Max 5 options
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
                
                # Add "Create new" button
                buttons.append([
                    InlineKeyboardButton(
                        f"➕ Tạo mới \"{debtor_name}\"",
                        callback_data="new_debtor"
                    )
                ])
                
                keyboard = InlineKeyboardMarkup(buttons)
                
                # Store pending transaction
                context.user_data["pending_transaction"] = {
                    "telegram_id": user.id,
                    "telegram_name": user.first_name or "Unknown",
                    "name_query": debtor_name,
                    "amount": str(amount),
                    "transaction_type": "DEBT",
                    "note": note,
                    "candidates": candidates_dict
                }
                
                msg = f"🔍 Tôi tìm thấy những tên gần giống:\n\nBạn muốn ghi nợ cho ai?"
                await update.message.reply_text(msg, reply_markup=keyboard)
                
            else:
                # No matches - create new debtor directly
                response = await record_transaction(
                    telegram_id=user.id,
                    telegram_name=user.first_name or "Unknown",
                    debtor_name=debtor_name,
                    amount=amount,
                    transaction_type="DEBT",
                    note=note
                )
                await update.message.reply_text(response)
                
    except Exception as e:
        error_msg = f"❌ Lỗi: {str(e)}"
        await update.message.reply_text(error_msg)


async def paid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /paid command - Record a debt repayment with fuzzy search.
    
    Format: /paid [Name] [Amount] [Note (optional)]
    Example: /paid Khánh Duy 20000 tien cafe
    """
    user = update.effective_user
    
    # Validate arguments
    if not context.args or len(context.args) < 2:
        error_msg = """❌ Cú pháp /paid không đúng!

Cách dùng: `/paid [Tên người] [Số tiền] [Ghi chú (tùy chọn)]`

Ví dụ: `/paid Khánh Duy 20000`"""
        await update.message.reply_text(error_msg)
        return
    
    # Parse arguments
    debtor_name = context.args[0]
    amount_str = context.args[1]
    note = " ".join(context.args[2:]) if len(context.args) > 2 else None
    
    # Parse and validate amount
    try:
        amount = parse_amount(amount_str)
    except ValueError as e:
        error_msg = f"❌ Lỗi định dạng tiền: {e}\n\nHỗ trợ: `50k` hoặc `50000`"
        await update.message.reply_text(error_msg)
        return
    
    try:
        async with AsyncSessionLocal() as session:
            # Get or create user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown"
            )
            
            # Search for fuzzy matches
            candidates = await search_debtors_fuzzy(
                session,
                user_id=db_user.id,
                name_query=debtor_name,
                threshold=60
            )
            
            # Check for exact match
            exact_match = None
            for debtor, score in candidates:
                if score == 100:  # Exact match
                    exact_match = debtor
                    break
            
            if exact_match:
                # Found exact match - proceed directly
                response = await record_transaction_with_debtor_id(
                    telegram_id=user.id,
                    telegram_name=user.first_name or "Unknown",
                    debtor_id=exact_match.id,
                    debtor_name=exact_match.name,
                    amount=amount,
                    transaction_type="CREDIT",
                    note=note
                )
                await update.message.reply_text(response)
                
            elif len(candidates) > 0:
                # Found fuzzy matches - show buttons
                buttons = []
                candidates_dict = {}
                
                # Add matching debtors as buttons
                for idx, (debtor, score) in enumerate(candidates[:5], 1):  # Max 5 options
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
                
                # No "Create new" button for repayment (must be existing debtor)
                keyboard = InlineKeyboardMarkup(buttons)
                
                # Store pending transaction
                context.user_data["pending_transaction"] = {
                    "telegram_id": user.id,
                    "telegram_name": user.first_name or "Unknown",
                    "name_query": debtor_name,
                    "amount": str(amount),
                    "transaction_type": "CREDIT",
                    "note": note,
                    "candidates": candidates_dict
                }
                
                msg = f"🔍 Tôi tìm thấy những tên gần giống:\n\nBạn muốn ghi nhận ai trả tiền?"
                await update.message.reply_text(msg, reply_markup=keyboard)
                
            else:
                # No matches for repayment
                error_msg = f"❌ Không tìm thấy \"{debtor_name}\" trong danh bạ. Bạn cần tạo hồ sơ trước!"
                await update.message.reply_text(error_msg)
                
    except Exception as e:
        error_msg = f"❌ Lỗi: {str(e)}"
        await update.message.reply_text(error_msg)


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle callback queries from fuzzy search inline buttons.
    
    Callback data format:
    - For existing debtor: "debtor_{debtor_id}"
    - For creating new: "new_debtor"
    """
    query = update.callback_query
    await query.answer()  # Dismiss the "loading" state
    
    # Retrieve pending transaction data from context
    pending = context.user_data.get("pending_transaction")
    if not pending:
        await query.edit_message_text(text="❌ Hết phiên làm việc, vui lòng thử lại.")
        return
    
    telegram_id = pending["telegram_id"]
    telegram_name = pending["telegram_name"]
    amount = Decimal(pending["amount"])
    transaction_type = pending["transaction_type"]
    note = pending["note"]
    
    callback_data = query.data

    try:
        if callback_data.startswith("debtor_"):
            # User selected an existing debtor
            debtor_id = int(callback_data.split("_")[1])
            
            # Security: Verify debtor ownership before proceeding
            async with AsyncSessionLocal() as session:
                db_user = await get_or_create_user(
                    session,
                    telegram_id=telegram_id,
                    full_name=telegram_name
                )
                
                from src.database.models import Debtor
                from sqlalchemy import select
                result = await session.execute(
                    select(Debtor).where(
                        (Debtor.id == debtor_id) &
                        (Debtor.user_id == db_user.id)  # Security: Verify ownership
                    )
                )
                debtor = result.scalar_one_or_none()
                
                if not debtor:
                    await query.edit_message_text("❌ Không tìm thấy thông tin người nợ.")
                    context.user_data.pop("pending_transaction", None)
                    return
                
                debtor_name = debtor.name
            
            # Record transaction with selected debtor (now verified)
            response = await record_transaction_with_debtor_id(
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                debtor_id=debtor_id,
                debtor_name=debtor_name,
                amount=amount,
                transaction_type=transaction_type,
                note=note
            )
            
        elif callback_data == "new_debtor":
            # User wants to create new debtor
            debtor_name = pending["name_query"]
            response = await record_transaction(
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                debtor_name=debtor_name,
                amount=amount,
                transaction_type=transaction_type,
                note=note
            )
        else:
            response = "❌ Lựa chọn không hợp lệ."
        
        # Update message with result
        await query.edit_message_text(text=response)
        
        # Clean up pending transaction
        context.user_data.pop("pending_transaction", None)
        
    except Exception as e:
        error_msg = f"❌ Lỗi: {str(e)}"
        await query.edit_message_text(text=error_msg)
        context.user_data.pop("pending_transaction", None)


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
            await _show_summary(update, user)
            return
        elif inquiry_type == "BALANCE" and name:
            await _show_individual_balance(update, user, name)
            return
        elif inquiry_type == "HISTORY" and name:
            await _show_history(update, user, name)
            return
    
    # Try to parse transaction message (debt/credit)
    parse_result = NLPEngine.parse_message(text)
    
    if not parse_result:
        # No match - do nothing (fallback)
        return
    
    transaction_type, debtor_name, amount_str, note = parse_result
    
    # Parse and validate amount
    try:
        amount = parse_amount(amount_str)
    except ValueError as e:
        error_msg = f"❌ Không hiểu số tiền: {amount_str}\n\nHỗ trợ: `50k`, `50.000`, `50,000`"
        await update.message.reply_text(error_msg)
        return
    
    try:
        async with AsyncSessionLocal() as session:
            # Get or create user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown"
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
                    note=note
                )
                # If matched by alias, show which real name was used
                if match_type == "alias":
                    response = f"(Alias \"{debtor_name}\" → {exact_match.name})\n\n{response}"
                await update.message.reply_text(response)
                
            elif len(candidates) > 0:
                # Found fuzzy matches - show buttons for user to choose
                buttons = []
                candidates_dict = {}
                
                # Add matching debtors as buttons
                for idx, (debtor, score) in enumerate(candidates[:5], 1):  # Max 5 options
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
                
                # Add "Create new" button
                buttons.append([
                    InlineKeyboardButton(
                        f"➕ Tạo mới \"{debtor_name}\"",
                        callback_data="new_debtor"
                    )
                ])
                
                keyboard = InlineKeyboardMarkup(buttons)
                
                # Store pending transaction
                context.user_data["pending_transaction"] = {
                    "telegram_id": user.id,
                    "telegram_name": user.first_name or "Unknown",
                    "name_query": debtor_name,
                    "amount": str(amount),
                    "transaction_type": transaction_type,
                    "note": note,
                    "candidates": candidates_dict
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
                    note=note
                )
                await update.message.reply_text(response)
                
    except Exception as e:
        error_msg = f"❌ Lỗi: {str(e)}"
        await update.message.reply_text(error_msg)


async def alias_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /alias command - Create an alias for a debtor.
    
    Format: /alias [nickname] = [real_name]
    Example: /alias Béo = Tuấn
    """
    user = update.effective_user
    
    # Get full text after /alias
    if not context.args:
        help_msg = """❌ Cú pháp /alias không đúng!

Cách dùng: `/alias [Biệt danh] = [Tên thật]`

Ví dụ: `/alias Béo = Tuấn`
Sau đó có thể chat: "Béo nợ 50k" sẽ ghi vào Tuấn."""
        await update.message.reply_text(help_msg)
        return
    
    # Join all args and parse with = sign
    full_text = " ".join(context.args)
    
    # Parse: alias_name = real_name
    match = re.match(r"^\s*(.+?)\s*=\s*(.+?)\s*$", full_text)
    if not match:
        error_msg = """❌ Cú pháp không đúng! Thiếu dấu "=".

Cách dùng: `/alias [Biệt danh] = [Tên thật]`

Ví dụ: `/alias Béo = Tuấn`"""
        await update.message.reply_text(error_msg)
        return
    
    alias_name = match.group(1).strip()
    real_name = match.group(2).strip()
    
    if not alias_name or not real_name:
        error_msg = "❌ Biệt danh và tên thật không được để trống!"
        await update.message.reply_text(error_msg)
        return
    
    try:
        async with AsyncSessionLocal() as session:
            # Get or create user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown"
            )
            
            # Add alias
            success, message, debtor = await add_alias(
                session,
                user_id=db_user.id,
                alias_name=alias_name,
                real_name=real_name
            )
            
            if success:
                await session.commit()
            
            await update.message.reply_text(message)
            
    except Exception as e:
        error_msg = f"❌ Lỗi: {str(e)}"
        await update.message.reply_text(error_msg)


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /balance command - Check balance for a specific debtor or show summary.
    
    Format: 
    - /balance [Name] - Check individual balance
    - /balance (no args) - Show summary of all debtors
    """
    user = update.effective_user
    
    if context.args:
        # Individual balance inquiry
        debtor_name = " ".join(context.args)
        await _show_individual_balance(update, user, debtor_name)
    else:
        # Summary of all debtors
        await _show_summary(update, user)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /summary command - Show summary of all debtors with non-zero balance.
    """
    user = update.effective_user
    await _show_summary(update, user)


async def _show_individual_balance(update: Update, user, debtor_name: str) -> None:
    """
    Show balance for a specific debtor (with fuzzy/alias support).
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown"
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


async def _show_summary(update: Update, user) -> None:
    """
    Show summary of all debtors with non-zero balance.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown"
            )
            
            # Get all debtors with non-zero balance
            balances = await get_all_debtors_balance(session, db_user.id)
            
            if not balances:
                await update.message.reply_text("✅ Bạn không có khoản nợ nào đang ghi nhận.")
                return
            
            # Build formatted message
            lines = ["📊 **TỔNG KẾT NỢ**\n"]
            total_owed_to_us = Decimal("0")  # Positive: they owe us
            total_we_owe = Decimal("0")  # Negative: we owe them
            
            for name, debtor_id, balance in balances:
                if balance > 0:
                    emoji = "🔴"
                    total_owed_to_us += balance
                    lines.append(f"{emoji} {name}: {format_currency(balance)}")
                else:
                    emoji = "🟢"
                    total_we_owe += abs(balance)
                    lines.append(f"{emoji} {name}: -{format_currency(abs(balance))}")
            
            # Add summary line
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
            
            msg = "\n".join(lines)
            await update.message.reply_text(msg, parse_mode="Markdown")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")


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
            # Get current user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown"
            )
            
            # Get debtor info - MUST filter by user_id for security
            from src.database.models import Debtor
            from sqlalchemy import select
            
            result = await session.execute(
                select(Debtor).where(
                    (Debtor.id == debtor_id) &
                    (Debtor.user_id == db_user.id)  # Security: Verify ownership
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


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /history command - Show transaction history for a debtor.
    
    Format: /history [Name]
    Example: /history Tuan
    """
    user = update.effective_user
    
    if not context.args:
        error_msg = """❌ Cú pháp /history không đúng!

Cách dùng: `/history [Tên người]`

Ví dụ: `/history Tuan`"""
        await update.message.reply_text(error_msg)
        return
    
    debtor_name = " ".join(context.args)
    await _show_history(update, user, debtor_name)


async def _show_history(update: Update, user, debtor_name: str) -> None:
    """
    Show transaction history for a specific debtor (with fuzzy/alias support).
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown"
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
            # Get current user
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown"
            )
            
            # Get debtor info - MUST filter by user_id for security
            from src.database.models import Debtor
            from sqlalchemy import select
            
            result = await session.execute(
                select(Debtor).where(
                    (Debtor.id == debtor_id) &
                    (Debtor.user_id == db_user.id)  # Security: Verify ownership
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
            
            # Build formatted message
            lines = [f"📜 **LỊCH SỬ GIAO DỊCH - {debtor.name}**\n"]
            
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
    "start_command",
    "help_command",
    "add_command",
    "paid_command",
    "nlp_message_handler",
    "button_callback_handler",
    "alias_command",
    "balance_command",
    "summary_command",
    "balance_callback_handler",
    "history_command",
    "history_callback_handler",
    "record_transaction",
    "record_transaction_with_debtor_id"
]
