"""
Vietnamese date parser for debt deadlines.
Parses Vietnamese date expressions like "trong 5 ngày", "25/12/2024", "ngày mai".
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

TRONG_PATTERN = re.compile(r'trong\s+(\d+)\s+(ngày|tuần|tháng)', re.IGNORECASE | re.UNICODE)
NUA_PATTERN = re.compile(r'(\d+)\s+(ngày|tuần)\s+nữa', re.IGNORECASE | re.UNICODE)
SHORT_PATTERN = re.compile(r'^(\d+)\s+(ngày|tuần)$', re.IGNORECASE | re.UNICODE)
DATE_FULL_PATTERN = re.compile(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})')
DATE_SHORT_PATTERN = re.compile(r'(\d{1,2})[/-](\d{1,2})(?![/-]\d)')

EXTRACT_PATTERNS = [
    re.compile(r'trong\s+(\d+)\s+(ngày|tuần|tháng)', re.IGNORECASE | re.UNICODE),
    re.compile(r'(\d+)\s+(ngày|tuần)\s+nữa', re.IGNORECASE | re.UNICODE),
    re.compile(r'hạn\s+(\d+)\s+(ngày|tuần|tháng)', re.IGNORECASE | re.UNICODE),
    re.compile(r'deadline\s+(\d+)\s+(ngày|tuần|tháng)', re.IGNORECASE | re.UNICODE),
    DATE_FULL_PATTERN,
    DATE_SHORT_PATTERN,
    re.compile(r'\bngày\s+mai\b', re.IGNORECASE | re.UNICODE),
    re.compile(r'\bmai\b', re.IGNORECASE | re.UNICODE),
    re.compile(r'\bhôm\s+nay\b', re.IGNORECASE | re.UNICODE),
]


def _get_midnight(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _add_unit(now: datetime, amount: int, unit: str) -> datetime:
    unit = unit.lower()
    if unit == 'ngày':
        return _get_midnight(now) + timedelta(days=amount)
    elif unit == 'tuần':
        return _get_midnight(now) + timedelta(weeks=amount)
    elif unit == 'tháng':
        return _get_midnight(now) + timedelta(days=amount * 30)
    return None


def parse_vi_due_date(text: str, now: datetime = None) -> Optional[datetime]:
    """
    Parse a Vietnamese date string and return a datetime.
    
    Args:
        text: Vietnamese date string (e.g., "trong 5 ngày", "25/12/2024")
        now: Reference datetime (defaults to datetime.now())
    
    Returns:
        Parsed datetime or None if no pattern matches
    """
    if now is None:
        now = datetime.now()
    
    text = text.strip().lower()
    if not text:
        return None
    
    if text == 'hôm nay':
        return _get_midnight(now)
    
    if text in ('mai', 'ngày mai'):
        return _get_midnight(now) + timedelta(days=1)
    
    match = TRONG_PATTERN.search(text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        return _add_unit(now, amount, unit)
    
    match = NUA_PATTERN.search(text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        return _add_unit(now, amount, unit)
    
    match = SHORT_PATTERN.match(text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        return _add_unit(now, amount, unit)
    
    match = DATE_FULL_PATTERN.search(text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        try:
            return datetime(year, month, day)
        except ValueError:
            return None
    
    match = DATE_SHORT_PATTERN.search(text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        try:
            result = datetime(now.year, month, day)
            if result < _get_midnight(now):
                result = datetime(now.year + 1, month, day)
            return result
        except ValueError:
            return None
    
    return None


def extract_due_date_from_note(note: str, now: datetime = None) -> Tuple[str, Optional[datetime]]:
    """
    Extract deadline from a note string.
    
    Args:
        note: Transaction note that may contain a deadline
        now: Reference datetime (defaults to datetime.now())
    
    Returns:
        Tuple of (cleaned_note, due_date)
    """
    if now is None:
        now = datetime.now()
    
    if not note or not note.strip():
        return (note.strip() if note else "", None)
    
    original_note = note
    note_lower = note.lower()
    
    for pattern in EXTRACT_PATTERNS:
        match = pattern.search(note_lower)
        if match:
            matched_text = match.group(0)
            start, end = match.start(), match.end()
            
            original_matched = original_note[start:end]
            
            due_date = parse_vi_due_date(matched_text, now)
            if due_date:
                cleaned = original_note[:start] + original_note[end:]
                cleaned = re.sub(r'\s+', ' ', cleaned).strip()
                return (cleaned, due_date)
    
    return (original_note.strip(), None)


__all__ = ["parse_vi_due_date", "extract_due_date_from_note"]
