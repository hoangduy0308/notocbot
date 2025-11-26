"""
Utility functions for formatting and parsing input.
"""

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


__all__ = ["parse_amount", "format_currency"]
