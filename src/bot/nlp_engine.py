"""
NLP Engine - Parse natural language messages using regex.
Supports debt, credit, balance inquiry, and summary pattern matching.
"""

import re
from typing import Optional, Tuple, Union
from decimal import Decimal


class NLPEngine:
    """Parse natural language debt/credit/inquiry messages."""
    
    # Regex patterns for debt (nợ/vay/muộn)
    DEBT_PATTERN = re.compile(
        r"^(?P<name>\S+)\s+(?:nợ|vay|muộn)\s+(?P<amount>\d+(?:[.,]\d+)?k?)(?:\s+(?P<note>.*))?$",
        re.IGNORECASE | re.UNICODE
    )
    
    # Regex patterns for credit (trả/đưa/bù)
    CREDIT_PATTERN = re.compile(
        r"^(?P<name>\S+)\s+(?:trả|đưa|bù)\s+(?P<amount>\d+(?:[.,]\d+)?k?)(?:\s+(?P<note>.*))?$",
        re.IGNORECASE | re.UNICODE
    )
    
    # Regex patterns for balance inquiry (xem nợ một người)
    # Examples: "Duy nợ bao nhiêu", "xem nợ Duy", "dư nợ Tuấn", "Béo còn nợ bao nhiêu"
    BALANCE_INQUIRY_PATTERNS = [
        re.compile(r"^(?P<name>\S+)\s+(?:nợ|còn nợ)\s+bao\s*nhiêu\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?:xem\s+nợ|dư\s+nợ|nợ\s+của)\s+(?P<name>\S+)\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?P<name>\S+)\s+(?:còn\s+)?(?:dư|nợ)\s+(?:bao\s*nhiêu|mấy)\??$", re.IGNORECASE | re.UNICODE),
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
        re.compile(r"^(?:lịch\s*sử|history|log)\s+(?:nợ\s+)?(?P<name>\S+)\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?:xem\s+lại|xem\s+log|xem\s+lịch\s*sử)\s+(?:giao\s+dịch\s+)?(?P<name>\S+)\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?:lịch\s*sử\s+giao\s+dịch)\s+(?P<name>\S+)\??$", re.IGNORECASE | re.UNICODE),
        re.compile(r"^(?P<name>\S+)\s+(?:lịch\s*sử|history)\??$", re.IGNORECASE | re.UNICODE),
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


__all__ = ["NLPEngine"]
