"""
Utility / helper functions.
"""

import uuid
from datetime import datetime, timezone


def generate_id() -> str:
    """Generate a unique ID string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def format_currency(amount: float) -> str:
    """Format a number as USD currency."""
    return f"${amount:,.2f}"


def safe_json_loads(data: str, default=None):
    """Safely parse a JSON string, returning default on failure."""
    import json
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return default


def truncate_string(s: str, max_length: int = 100) -> str:
    """Truncate a string with ellipsis if too long."""
    if len(s) <= max_length:
        return s
    return s[: max_length - 3] + "..."
