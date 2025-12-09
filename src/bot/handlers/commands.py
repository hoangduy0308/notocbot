"""
Bot command handlers for NoTocBot.

Handles all /command style interactions.
"""

from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from decimal import Decimal
import re
from sqlalchemy import select

from src.database.config import AsyncSessionLocal
from src.database.models import Debtor
from src.services.user_service import get_or_create_user, get_user_by_username
from src.services.debtor_service import (
    get_or_create_debtor,
    search_debtors_fuzzy,
    resolve_debtor,
    add_alias,
    update_debtor_telegram_id,
)
from src.services.debt_service import (
    get_balance,
    get_transaction_with_owner_check,
    get_debtor_count_for_user,
)
from src.services.deadline_service import (
    update_transaction_due_date,
    list_upcoming_deadlines,
)
from src.bot.date_parser_vi import parse_vi_due_date
from src.utils.formatters import format_currency, parse_amount, format_due_date_relative

from .shared import (
    record_transaction,
    record_transaction_with_debtor_id,
    show_summary,
    show_individual_balance,
    show_history,
)


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
            full_name=user.first_name or "Unknown",
            username=user.username
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
/paid - Ghi nhận trả nợ
/balance - Xem số dư của một người
/summary - Xem tổng kết tất cả
/history - Xem lịch sử giao dịch
/alias - Tạo biệt danh
/link - Liên kết với Telegram user

**⏰ Quản lý hạn trả:**
/deadline [ID] [date] - Đặt hạn trả cho giao dịch
/duedate - Xem các khoản nợ sắp đến hạn

**🗑️ Xóa dữ liệu:**
/xoagiaodich [ID] - Xóa một giao dịch
/xoano [Tên] - Xóa toàn bộ nợ của một người
/xoatatca - Xóa TẤT CẢ dữ liệu nợ

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
    
    Note: Group chat support is disabled. Use private chat only.
    """
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    # Reject group chat - only private chat supported
    if chat.type in ["group", "supergroup"]:
        await message.reply_text(
            "⚠️ Bot chỉ hoạt động trong chat riêng.\n"
            "Vui lòng nhắn tin trực tiếp cho bot để ghi nợ."
        )
        return
    
    # Validate arguments
    if not context.args or len(context.args) < 2:
        error_msg = """❌ Cú pháp /add không đúng!

Cách dùng: `/add [Tên người] [Số tiền] [Ghi chú (tùy chọn)]`

Ví dụ: `/add Khánh Duy 50k tien cafe`"""
        await message.reply_text(error_msg)
        return
    
    # Smart parse: Find amount in args (supports multi-word names)
    amount = None
    amount_idx = -1
    
    for idx, arg in enumerate(context.args):
        try:
            amount = parse_amount(arg)
            amount_idx = idx
            break
        except ValueError:
            continue
    
    if amount is None or amount_idx == 0:
        error_msg = """❌ Không tìm thấy số tiền hợp lệ!

Cách dùng: `/add [Tên người] [Số tiền] [Ghi chú (tùy chọn)]`

Ví dụ: `/add Khánh Duy 50k tien cafe`"""
        await message.reply_text(error_msg)
        return
    
    # Name is everything before amount, excluding keywords
    name_parts = context.args[:amount_idx]
    while name_parts and name_parts[-1].lower() in ["nợ", "vay", "mượn", "no"]:
        name_parts.pop()
    
    if not name_parts:
        error_msg = """❌ Thiếu tên người nợ!

Cách dùng: `/add [Tên người] [Số tiền] [Ghi chú (tùy chọn)]`

Ví dụ: `/add Khánh Duy 50k tien cafe`"""
        await message.reply_text(error_msg)
        return
    
    debtor_name = " ".join(name_parts)
    note = " ".join(context.args[amount_idx + 1:]) if len(context.args) > amount_idx + 1 else None
    
    try:
        async with AsyncSessionLocal() as session:
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
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
                if score == 100:
                    exact_match = debtor
                    break
            
            if exact_match:
                response = await record_transaction_with_debtor_id(
                    telegram_id=user.id,
                    telegram_name=user.first_name or "Unknown",
                    debtor_id=exact_match.id,
                    debtor_name=exact_match.name,
                    amount=amount,
                    transaction_type="DEBT",
                    note=note,
                    username=user.username,
                    bot=context.bot
                )
                await message.reply_text(response)
                
            elif len(candidates) > 0:
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
                    "transaction_type": "DEBT",
                    "note": note,
                    "candidates": candidates_dict
                }
                
                msg = f"🔍 Tôi tìm thấy những tên gần giống:\n\nBạn muốn ghi nợ cho ai?"
                await message.reply_text(msg, reply_markup=keyboard)
                
            else:
                response = await record_transaction(
                    telegram_id=user.id,
                    telegram_name=user.first_name or "Unknown",
                    debtor_name=debtor_name,
                    amount=amount,
                    transaction_type="DEBT",
                    note=note,
                    username=user.username,
                    bot=context.bot
                )
                await message.reply_text(response)
                
    except Exception as e:
        error_msg = f"❌ Lỗi: {str(e)}"
        await message.reply_text(error_msg)


async def paid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /paid command - Record a debt repayment with fuzzy search.
    
    Format: /paid [Name] [Amount] [Note (optional)]
    Example: /paid Khánh Duy 20000 tien cafe
    """
    user = update.effective_user
    
    if not context.args or len(context.args) < 2:
        error_msg = """❌ Cú pháp /paid không đúng!

Cách dùng: `/paid [Tên người] [Số tiền] [Ghi chú (tùy chọn)]`

Ví dụ: `/paid Khánh Duy 20000`"""
        await update.message.reply_text(error_msg)
        return
    
    # Smart parse: Find amount in args
    amount = None
    amount_idx = -1
    
    for idx, arg in enumerate(context.args):
        try:
            amount = parse_amount(arg)
            amount_idx = idx
            break
        except ValueError:
            continue
    
    if amount is None or amount_idx == 0:
        error_msg = """❌ Không tìm thấy số tiền hợp lệ!

Cách dùng: `/paid [Tên người] [Số tiền] [Ghi chú (tùy chọn)]`

Ví dụ: `/paid Khánh Duy 20000`"""
        await update.message.reply_text(error_msg)
        return
    
    # Name is everything before amount, excluding keywords
    name_parts = context.args[:amount_idx]
    while name_parts and name_parts[-1].lower() in ["trả", "tra", "đưa", "dua", "bù", "bu"]:
        name_parts.pop()
    
    if not name_parts:
        error_msg = """❌ Thiếu tên người trả!

Cách dùng: `/paid [Tên người] [Số tiền] [Ghi chú (tùy chọn)]`

Ví dụ: `/paid Khánh Duy 20000`"""
        await update.message.reply_text(error_msg)
        return
    
    debtor_name = " ".join(name_parts)
    note = " ".join(context.args[amount_idx + 1:]) if len(context.args) > amount_idx + 1 else None
    
    try:
        async with AsyncSessionLocal() as session:
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
            )
            
            candidates = await search_debtors_fuzzy(
                session,
                user_id=db_user.id,
                name_query=debtor_name,
                threshold=60
            )
            
            exact_match = None
            for debtor, score in candidates:
                if score == 100:
                    exact_match = debtor
                    break
            
            if exact_match:
                response = await record_transaction_with_debtor_id(
                    telegram_id=user.id,
                    telegram_name=user.first_name or "Unknown",
                    debtor_id=exact_match.id,
                    debtor_name=exact_match.name,
                    amount=amount,
                    transaction_type="CREDIT",
                    note=note,
                    username=user.username,
                    bot=context.bot
                )
                await update.message.reply_text(response)
                
            elif len(candidates) > 0:
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
                
                keyboard = InlineKeyboardMarkup(buttons)
                
                context.user_data["pending_transaction"] = {
                    "telegram_id": user.id,
                    "telegram_name": user.first_name or "Unknown",
                    "username": user.username,
                    "name_query": debtor_name,
                    "amount": str(amount),
                    "transaction_type": "CREDIT",
                    "note": note,
                    "candidates": candidates_dict
                }
                
                msg = f"🔍 Tôi tìm thấy những tên gần giống:\n\nBạn muốn ghi nhận ai trả tiền?"
                await update.message.reply_text(msg, reply_markup=keyboard)
                
            else:
                error_msg = f"❌ Không tìm thấy \"{debtor_name}\" trong danh bạ. Bạn cần tạo hồ sơ trước!"
                await update.message.reply_text(error_msg)
                
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
        debtor_name = " ".join(context.args)
        await show_individual_balance(update, user, debtor_name)
    else:
        await show_summary(update, user)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /summary command - Show summary of all debtors with non-zero balance.
    """
    user = update.effective_user
    await show_summary(update, user)


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
    await show_history(update, user, debtor_name)


async def alias_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /alias command - Create an alias for a debtor.
    
    Format: /alias [nickname] = [real_name]
    Example: /alias Béo = Tuấn
    """
    user = update.effective_user
    
    if not context.args:
        help_msg = """❌ Cú pháp /alias không đúng!

Cách dùng: `/alias [Biệt danh] = [Tên thật]`

Ví dụ: `/alias Béo = Tuấn`
Sau đó có thể chat: "Béo nợ 50k" sẽ ghi vào Tuấn."""
        await update.message.reply_text(help_msg)
        return
    
    full_text = " ".join(context.args)
    
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
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
            )
            
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


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /link command - Link a debtor to a real Telegram user.
    
    Format: /link [DebtorName] [@Username]
    Example: /link Duy @khanhduy
    """
    user = update.effective_user
    message = update.message
    
    if not context.args or len(context.args) < 2:
        await message.reply_text(
            "❌ Cú pháp sai!\n"
            "Cách dùng: `/link [Tên người] [@Username]`\n"
            "Ví dụ: `/link Duy @khanhduy`"
        )
        return
        
    target_username = context.args[-1]
    if not target_username.startswith("@"):
        await message.reply_text("❌ Username phải bắt đầu bằng @ (ví dụ: @khanhduy)")
        return
        
    debtor_name = " ".join(context.args[:-1])
    
    async with AsyncSessionLocal() as session:
        target_user = await get_user_by_username(session, target_username)
        
        if not target_user:
            await message.reply_text(
                f"❌ Không tìm thấy người dùng {target_username}.\n"
                f"Hãy bảo họ chat `/start` với Bot trước để đăng ký hệ thống."
            )
            return
            
        db_user = await get_or_create_user(
            session,
            telegram_id=user.id,
            full_name=user.first_name or "Unknown",
            username=user.username
        )
        
        exact_match, candidates, match_type = await resolve_debtor(session, db_user.id, debtor_name)
        
        if not exact_match:
            await message.reply_text(f"❌ Không tìm thấy hồ sơ nợ nào tên là \"{debtor_name}\" trong danh bạ của bạn.")
            return
            
        success = await update_debtor_telegram_id(session, exact_match.id, target_user.telegram_id)
        
        if success:
            await session.commit()
            await message.reply_text(
                f"✅ Đã liên kết **{exact_match.name}** với tài khoản Telegram {target_username}.\n"
                f"Từ giờ, khi bạn ghi nợ cho {exact_match.name}, Bot sẽ gửi thông báo cho họ."
            )
        else:
            await message.reply_text("❌ Có lỗi xảy ra khi liên kết.")


async def delete_transaction_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /xoagiaodich command - Delete a single transaction by ID.
    
    Format: /xoagiaodich [ID]
    Example: /xoagiaodich 123
    """
    user = update.effective_user
    message = update.message
    
    if not context.args or len(context.args) != 1:
        error_msg = """❌ Cú pháp không đúng!

Cách dùng: `/xoagiaodich [ID giao dịch]`

Ví dụ: `/xoagiaodich 123`

💡 Xem ID giao dịch bằng lệnh `/history [Tên người]`"""
        await message.reply_text(error_msg)
        return
    
    try:
        transaction_id = int(context.args[0])
    except ValueError:
        await message.reply_text("❌ ID giao dịch phải là số nguyên!")
        return
    
    try:
        async with AsyncSessionLocal() as session:
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
            )
            
            transaction = await get_transaction_with_owner_check(
                session, db_user.id, transaction_id
            )
            
            if not transaction:
                await message.reply_text("❌ Không tìm thấy giao dịch này hoặc bạn không có quyền xóa.")
                return
            
            # Get debtor name for display
            from src.database.models import Debtor
            debtor_result = await session.execute(
                select(Debtor).where(Debtor.id == transaction.debtor_id)
            )
            debtor = debtor_result.scalar_one_or_none()
            debtor_name = debtor.name if debtor else "Unknown"
            
            # Format transaction info
            tx_type = "nợ thêm" if transaction.type == "DEBT" else "trả nợ"
            amount_str = format_currency(transaction.amount)
            note_str = f" ({transaction.note})" if transaction.note else ""
            
            # Show confirmation
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Xóa giao dịch này", callback_data=f"del_tx_{transaction_id}")],
                [InlineKeyboardButton("❌ Hủy", callback_data="del_tx_cancel")]
            ])
            
            msg = f"""⚠️ **XÁC NHẬN XÓA GIAO DỊCH**

📋 **Chi tiết:**
- Người: **{debtor_name}**
- Loại: {tx_type}
- Số tiền: **{amount_str}**{note_str}

⚠️ Hành động này không thể hoàn tác!"""
            
            await message.reply_text(msg, reply_markup=keyboard, parse_mode="Markdown")
            
    except Exception as e:
        await message.reply_text(f"❌ Lỗi: {str(e)}")


async def delete_debtor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /xoano command - Delete all debts for a specific debtor.
    
    Format: /xoano [Name]
    Example: /xoano Tuấn
    """
    user = update.effective_user
    message = update.message
    
    if not context.args:
        error_msg = """❌ Cú pháp không đúng!

Cách dùng: `/xoano [Tên người]`

Ví dụ: `/xoano Tuấn`

⚠️ Lệnh này sẽ xóa TOÀN BỘ hồ sơ nợ và lịch sử giao dịch với người đó."""
        await message.reply_text(error_msg)
        return
    
    debtor_name = " ".join(context.args)
    
    try:
        async with AsyncSessionLocal() as session:
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
            )
            
            exact_match, candidates, match_type = await resolve_debtor(
                session, db_user.id, debtor_name
            )
            
            if match_type == "none":
                await message.reply_text(f"❌ Không tìm thấy người tên \"{debtor_name}\" trong danh bạ.")
                return
            
            if exact_match:
                # Show confirmation for exact match
                balance = await get_balance(session, exact_match.id)
                balance_str = format_currency(abs(balance))
                
                if balance > 0:
                    balance_info = f"💰 Dư nợ hiện tại: {balance_str} (họ nợ bạn)"
                elif balance < 0:
                    balance_info = f"💸 Dư nợ hiện tại: {balance_str} (bạn nợ họ)"
                else:
                    balance_info = "✅ Hết nợ (0đ)"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"🗑️ Xóa hết với {exact_match.name}", callback_data=f"del_debtor_{exact_match.id}")],
                    [InlineKeyboardButton("❌ Hủy", callback_data="del_debtor_cancel")]
                ])
                
                msg = f"""⚠️ **XÁC NHẬN XÓA TOÀN BỘ HỒ SƠ NỢ**

👤 Người: **{exact_match.name}**
{balance_info}

🗑️ Sẽ xóa:
- Tất cả lịch sử giao dịch
- Tất cả biệt danh

⚠️ **Hành động này KHÔNG THỂ hoàn tác!**"""
                
                await message.reply_text(msg, reply_markup=keyboard, parse_mode="Markdown")
                
            elif candidates:
                # Show fuzzy matches
                buttons = []
                for idx, (debtor, score) in enumerate(candidates[:5], 1):
                    buttons.append([
                        InlineKeyboardButton(
                            f"{idx}. {debtor.name} ({score}%)",
                            callback_data=f"del_pick_{debtor.id}"
                        )
                    ])
                buttons.append([InlineKeyboardButton("❌ Hủy", callback_data="del_debtor_cancel")])
                
                keyboard = InlineKeyboardMarkup(buttons)
                msg = "🔍 Bạn muốn xóa hồ sơ nợ của ai?"
                await message.reply_text(msg, reply_markup=keyboard)
                
    except Exception as e:
        await message.reply_text(f"❌ Lỗi: {str(e)}")


async def delete_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /xoatatca command - Delete ALL debt data for the current user.
    
    Format: /xoatatca
    """
    user = update.effective_user
    message = update.message
    
    try:
        async with AsyncSessionLocal() as session:
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                full_name=user.first_name or "Unknown",
                username=user.username
            )
            
            count = await get_debtor_count_for_user(session, db_user.id)
            
            if count == 0:
                await message.reply_text("📭 Bạn chưa có dữ liệu nợ nào để xóa.")
                return
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚠️ ĐỒNG Ý XÓA TẤT CẢ", callback_data="del_all_confirm")],
                [InlineKeyboardButton("❌ Hủy", callback_data="del_all_cancel")]
            ])
            
            msg = f"""🚨 **CẢNH BÁO: XÓA TOÀN BỘ DỮ LIỆU**

Bạn có **{count}** hồ sơ nợ.

🗑️ Lệnh này sẽ xóa:
- TẤT CẢ hồ sơ người nợ
- TẤT CẢ lịch sử giao dịch
- TẤT CẢ biệt danh

⚠️ **HÀNH ĐỘNG NÀY KHÔNG THỂ HOÀN TÁC!**

Bạn có chắc chắn muốn tiếp tục?"""
            
            await message.reply_text(msg, reply_markup=keyboard, parse_mode="Markdown")
            
    except Exception as e:
        await message.reply_text(f"❌ Lỗi: {str(e)}")


async def deadline_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /deadline command - Set/update/clear deadline for a transaction.
    
    Format: /deadline [ID] [date]
    Example: /deadline 123 trong 5 ngày
    """
    user = update.effective_user
    message = update.message
    
    if not context.args:
        error_msg = """❌ Cú pháp không đúng!

Cách dùng: `/deadline [ID giao dịch] [ngày hạn]`

Ví dụ:
- `/deadline 123 trong 5 ngày`
- `/deadline 123 25/12/2024`
- `/deadline 123 1 tuần`
- `/deadline 123 xóa` - Xóa hạn trả

💡 Xem ID giao dịch bằng lệnh `/history [Tên người]`"""
        await message.reply_text(error_msg)
        return
    
    try:
        transaction_id = int(context.args[0])
    except ValueError:
        await message.reply_text("❌ ID giao dịch phải là số nguyên!")
        return
    
    async with AsyncSessionLocal() as session:
        db_user = await get_or_create_user(
            session,
            telegram_id=user.id,
            full_name=user.first_name or "Unknown",
            username=user.username
        )
        
        transaction = await get_transaction_with_owner_check(
            session, db_user.id, transaction_id
        )
        
        if not transaction:
            await message.reply_text("❌ Không tìm thấy giao dịch này hoặc bạn không có quyền chỉnh sửa.")
            return
        
        debtor_result = await session.execute(
            select(Debtor).where(Debtor.id == transaction.debtor_id)
        )
        debtor = debtor_result.scalar_one_or_none()
        debtor_name = debtor.name if debtor else "Unknown"
        
        if len(context.args) == 1:
            if transaction.due_date:
                date_str = format_due_date_relative(transaction.due_date)
                await message.reply_text(
                    f"📅 Giao dịch [#{transaction_id}] với **{debtor_name}**\n"
                    f"Hạn trả: **{date_str}**",
                    parse_mode="Markdown"
                )
            else:
                await message.reply_text(
                    f"📅 Giao dịch [#{transaction_id}] với **{debtor_name}**\n"
                    f"Chưa có hạn trả.",
                    parse_mode="Markdown"
                )
            return
        
        date_text = " ".join(context.args[1:]).strip().lower()
        
        if date_text in ("xóa", "xoa", "clear", "none"):
            await update_transaction_due_date(session, db_user.id, transaction_id, None)
            await session.commit()
            await message.reply_text(
                f"✅ Đã xóa hạn trả cho giao dịch [#{transaction_id}] với **{debtor_name}**.",
                parse_mode="Markdown"
            )
            return
        
        due_date = parse_vi_due_date(date_text)
        if not due_date:
            await message.reply_text(
                "❌ Không hiểu định dạng ngày!\n\n"
                "Ví dụ:\n"
                "- `trong 5 ngày`\n"
                "- `25/12/2024`\n"
                "- `1 tuần`\n"
                "- `ngày mai`"
            )
            return
        
        await update_transaction_due_date(session, db_user.id, transaction_id, due_date)
        await session.commit()
        
        date_str = format_due_date_relative(due_date)
        await message.reply_text(
            f"✅ Đã đặt hạn trả cho giao dịch [#{transaction_id}] với **{debtor_name}**\n"
            f"📅 Hạn: **{date_str}**",
            parse_mode="Markdown"
        )


async def duedate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /duedate command - View upcoming deadlines.
    
    Format: /duedate [days]
    Example: /duedate 7
    """
    user = update.effective_user
    message = update.message
    
    days = None
    if context.args:
        try:
            days = int(context.args[0])
            if days <= 0:
                await message.reply_text("❌ Số ngày phải lớn hơn 0!")
                return
        except ValueError:
            await message.reply_text("❌ Số ngày phải là số nguyên!")
            return
    
    async with AsyncSessionLocal() as session:
        db_user = await get_or_create_user(
            session,
            telegram_id=user.id,
            full_name=user.first_name or "Unknown",
            username=user.username
        )
        
        transactions = await list_upcoming_deadlines(session, db_user.id, days=days)
        
        if not transactions:
            if days:
                await message.reply_text(f"📭 Không có khoản nợ nào đến hạn trong {days} ngày tới.")
            else:
                await message.reply_text("📭 Không có khoản nợ nào có hạn trả.")
            return
        
        now = datetime.now()
        overdue = []
        upcoming = []
        
        for tx in transactions:
            debtor_result = await session.execute(
                select(Debtor).where(Debtor.id == tx.debtor_id)
            )
            debtor = debtor_result.scalar_one_or_none()
            debtor_name = debtor.name if debtor else "Unknown"
            
            delta = (tx.due_date.date() - now.date()).days
            date_str = format_due_date_relative(tx.due_date, now)
            amount_str = format_currency(tx.amount)
            note_str = f" - {tx.note}" if tx.note else ""
            
            line = f"• [#{tx.id}] **{debtor_name}**: {amount_str}{note_str}\n  📅 {date_str}"
            
            if delta < 0:
                overdue.append(line)
            else:
                upcoming.append(line)
        
        parts = []
        if overdue:
            parts.append("🚨 **Đã quá hạn:**\n" + "\n".join(overdue))
        if upcoming:
            parts.append("⏰ **Sắp đến hạn:**\n" + "\n".join(upcoming))
        
        header = "📅 **DANH SÁCH HẠN TRẢ**"
        if days:
            header += f" (trong {days} ngày)"
        
        msg = header + "\n\n" + "\n\n".join(parts)
        await message.reply_text(msg, parse_mode="Markdown")


__all__ = [
    "start_command",
    "help_command",
    "add_command",
    "paid_command",
    "balance_command",
    "summary_command",
    "history_command",
    "alias_command",
    "link_command",
    "delete_transaction_command",
    "delete_debtor_command",
    "delete_all_command",
    "deadline_command",
    "duedate_command",
]
