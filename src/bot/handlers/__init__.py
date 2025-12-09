"""
Bot handlers package for NoTocBot.

Re-exports all handler functions for use in main.py.
"""

from .commands import (
    start_command,
    help_command,
    add_command,
    paid_command,
    balance_command,
    summary_command,
    history_command,
    alias_command,
    link_command,
    delete_transaction_command,
    delete_debtor_command,
    delete_all_command,
)
from .callbacks import (
    button_callback_handler,
    balance_callback_handler,
    history_callback_handler,
    delete_callback_handler,
)
from .nlp_handlers import (
    nlp_message_handler,
)
from .shared import (
    record_transaction,
    record_transaction_with_debtor_id,
)

__all__ = [
    # Commands
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
    # Callbacks
    "button_callback_handler",
    "balance_callback_handler",
    "history_callback_handler",
    "delete_callback_handler",
    # NLP
    "nlp_message_handler",
    # Shared utilities (for external use if needed)
    "record_transaction",
    "record_transaction_with_debtor_id",
]
