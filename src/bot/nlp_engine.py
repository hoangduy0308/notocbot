"""
NLP Engine - Parse natural language messages using regex.
Supports debt, credit, balance inquiry, and summary pattern matching.
Also handles Telegram message entities for group mentions.
"""

import re
from typing import Optional, Tuple, Union, List, NamedTuple
from decimal import Decimal
from telegram import Message, MessageEntity


class MentionedUser(NamedTuple):
    """Represents a mentioned user extracted from message entities."""
    telegram_id: Optional[int]  # None for @username mentions without user object
    name: str  # first_name or username
    username: Optional[str]  # @username if available


class NLPEngine:
    """Parse natural language debt/credit/inquiry messages."""
    
    # Matches 1-4 word names (Vietnamese names: Họ + Đệm + Tên)
    NAME_BODY = r"\S+(?:\s+\S+){0,3}"
    
    # Regex patterns for debt (nợ/vay/muộn)
    DEBT_PATTERN = re.compile(
        r"^(?P<name>\S+(?:\s+\S+){0,3})\s+(?:nợ|vay|muộn)\s+(?P<amount>\d+(?:[.,]\d+)?k?)(?:\s+(?P<note>.*))?$",
        re.IGNORECASE | re.UNICODE
    )
    
    # Regex patterns for credit (trả/đưa/bù)
    CREDIT_PATTERN = re.compile(
        r"^(?P<name>\S+(?:\s+\S+){0,3})\s+(?:trả|đưa|bù)\s+(?P<amount>\d+(?:[.,]\d+)?k?)(?:\s+(?P<note>.*))?$",
        re.IGNORECASE | re.UNICODE
    )
    
    # Regex patterns for balance inquiry (xem nợ một người)
    # Examples: "Duy nợ bao nhiêu", "xem nợ Duy", "dư nợ Tuấn", "Béo còn nợ bao nhiêu"
    BALANCE_INQUIRY_PATTERNS = [
        re.compile(r"^(?P<name>\S+(?:\s+\S+){0,3}?)\s+(?:còn\s+)?nợ\s+bao\s*nhiêu\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?:xem\s+nợ|dư\s+nợ|nợ\s+của)\s+(?P<name>[^\s?]+(?:\s+[^\s?]+){0,3})\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?P<name>\S+(?:\s+\S+){0,3}?)\s+(?:còn\s+)?(?:dư|nợ)\s+(?:bao\s*nhiêu|mấy)\??$", re.IGNORECASE | re.UNICODE),
    ]
    
    # Regex patterns for summary (tổng quan tất cả nợ)
    # Examples: "tổng nợ", "ai nợ tôi", "ai đang nợ", "danh sách nợ", "summary"
    SUMMARY_PATTERNS = [
        re.compile(r"^(?:tổng\s+nợ|tổng\s+kết|tổng\s+quan)\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?:ai\s+(?:đang\s+)?nợ(?:\s+tôi)?|ai\s+còn\s+nợ)\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?:danh\s+sách\s+nợ|ds\s+nợ|list\s+nợ)\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^summary\??$", re.IGNORECASE),
    ]
    
    # Regex patterns for transaction history inquiry
    # Examples: "lịch sử Tuan", "history Duy", "log Béo", "xem lại giao dịch Tuan"
    HISTORY_PATTERNS = [
        re.compile(r"^(?:lịch\s*sử|history|log)\s+(?:nợ\s+)?(?P<name>[^\s?]+(?:\s+[^\s?]+){0,3})\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?:xem\s+lại|xem\s+log|xem\s+lịch\s*sử)\s+(?:giao\s+dịch\s+)?(?P<name>[^\s?]+(?:\s+[^\s?]+){0,3})\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?:lịch\s*sử\s+giao\s+dịch)\s+(?P<name>[^\s?]+(?:\s+[^\s?]+){0,3})\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?P<name>\S+(?:\s+\S+){0,3})\s+(?:lịch\s*sử|history)\??$", re.IGNORECASE | re.UNICODE),
    ]
    
    @staticmethod
    def parse_message(text: str) -> Optional[Tuple[str, str, str, Optional[str]]]:
        """
        Parse a message and detect debt/credit pattern.
        
        Args:
            text: Message text
            
        Returns:
            Tuple of (transaction_type, name, amount_str, note) or None if no match
            
        Examples:
            "Tuấn nợ 50k tiền cơm" -> ("DEBT", "Tuấn", "50k", "tiền cơm")
            "Lan trả 20000" -> ("CREDIT", "Lan", "20000", None)
        """
        text = text.strip()
        
        # Try debt pattern
        debt_match = NLPEngine.DEBT_PATTERN.match(text)
        if debt_match:
            return (
                "DEBT",
                debt_match.group("name"),
                debt_match.group("amount"),
                debt_match.group("note")
            )
        
        # Try credit pattern
        credit_match = NLPEngine.CREDIT_PATTERN.match(text)
        if credit_match:
            return (
                "CREDIT",
                credit_match.group("name"),
                credit_match.group("amount"),
                credit_match.group("note")
            )
        
        # No match
        return None
    
    @staticmethod
    def parse_inquiry(text: str) -> Optional[Tuple[str, Optional[str]]]:
        """
        Parse a message and detect balance inquiry, summary, or history request.
        
        Args:
            text: Message text
            
        Returns:
            Tuple of (inquiry_type, name_or_none):
            - ("BALANCE", "Tên") for individual balance inquiry
            - ("SUMMARY", None) for summary request
            - ("HISTORY", "Tên") for transaction history inquiry
            - None if no match
            
        Examples:
            "Duy nợ bao nhiêu" -> ("BALANCE", "Duy")
            "tổng nợ" -> ("SUMMARY", None)
            "lịch sử Tuan" -> ("HISTORY", "Tuan")
        """
        text = text.strip()
        
        # Try history patterns first (more specific)
        for pattern in NLPEngine.HISTORY_PATTERNS:
            match = pattern.match(text)
            if match:
                return ("HISTORY", match.group("name"))
        
        # Try balance inquiry patterns
        for pattern in NLPEngine.BALANCE_INQUIRY_PATTERNS:
            match = pattern.match(text)
            if match:
                return ("BALANCE", match.group("name"))
        
        # Try summary patterns
        for pattern in NLPEngine.SUMMARY_PATTERNS:
            if pattern.match(text):
                return ("SUMMARY", None)
        
        # No match
        return None


def extract_mentioned_users(message: Message) -> List[MentionedUser]:
    """
    Extract mentioned users from Telegram message entities.
    
    Supports two types of mentions:
    - TEXT_MENTION: Rich text mentions that include user object with telegram_id
    - MENTION: @username mentions (no telegram_id, only username)
    
    Args:
        message: Telegram Message object
        
    Returns:
        List of MentionedUser with telegram_id (if available), name and optional username
    """
    mentioned_users: List[MentionedUser] = []
    
    if not message.entities:
        return mentioned_users
    
    for entity in message.entities:
        # Handle TEXT_MENTION - most reliable, includes user object with telegram_id
        if entity.type == MessageEntity.TEXT_MENTION and entity.user:
            user = entity.user
            name = user.first_name or user.username or f"User_{user.id}"
            mentioned_users.append(MentionedUser(
                telegram_id=user.id,
                name=name,
                username=user.username
            ))
        
        # Handle @username MENTION - extract username from text (no telegram_id)
        elif entity.type == MessageEntity.MENTION:
            # Extract @username from message text (without the @)
            username = message.text[entity.offset + 1:entity.offset + entity.length]
            mentioned_users.append(MentionedUser(
                telegram_id=None,  # We don't have telegram_id for @mentions
                name=username,
                username=username
            ))
    
    return mentioned_users


__all__ = ["NLPEngine", "MentionedUser", "extract_mentioned_users"]
