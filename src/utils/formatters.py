"""
Utility functions for formatting and parsing input.
"""

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def parse_amount(text: str) -> Decimal:
    """
    Parse amount from text with support for suffixes like 'k' (thousand).
    
    Examples:
        "50k" -> Decimal("50000")
        "50000" -> Decimal("50000")
        "50.5k" -> Decimal("50500")
    
    Args:
        text: Text representation of amount
        
    Returns:
        Decimal amount
        
    Raises:
        ValueError: If amount is invalid or <= 0
    """
    text = text.strip().lower()
    
    # Handle 'k' suffix (thousand)
    if text.endswith('k'):
        text = text[:-1].strip()
        try:
            amount = Decimal(text) * Decimal("1000")
        except InvalidOperation:
            raise ValueError(f"Invalid amount: {text}")
    else:
        try:
            amount = Decimal(text)
        except InvalidOperation:
            raise ValueError(f"Invalid amount: {text}")
    
    # Validate amount is positive
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    
    return amount


def format_currency(amount: Decimal) -> str:
    """
    Format decimal amount as currency string.
    
    Examples:
        Decimal("50000") -> "50.000"
        Decimal("50500") -> "50.500"
        Decimal("100") -> "100"
    
    Args:
        amount: Amount in decimal
        
    Returns:
        Formatted currency string with thousand separator
    """
    # Convert to int if no decimal part
    if amount == int(amount):
        return f"{int(amount):,}".replace(",", ".")
    else:
        return f"{amount:,}".replace(",", ".")


def format_due_date(due_date: datetime) -> str:
    """Format due date as Vietnamese date string."""
    return due_date.strftime("%d/%m/%Y")


def format_due_date_relative(due_date: datetime, now: datetime = None) -> str:
    """
    Format due date with relative time.
    
    Returns: "25/12/2024 (còn 5 ngày)" or "25/12/2024 (quá hạn 2 ngày)"
    """
    if now is None:
        now = datetime.now()
    
    date_str = format_due_date(due_date)
    delta = (due_date.date() - now.date()).days
    
    if delta > 0:
        return f"{date_str} (còn {delta} ngày)"
    elif delta == 0:
        return f"{date_str} (hôm nay)"
    else:
        return f"{date_str} (quá hạn {abs(delta)} ngày)"


__all__ = ["parse_amount", "format_currency", "format_due_date", "format_due_date_relative"]
