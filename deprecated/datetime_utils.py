"""
DateTime Utilities for NetStacks

Provides consistent timezone-aware datetime handling across the application.
All timestamps are stored in UTC for consistency.

Usage:
    from datetime_utils import utc_now, to_utc, format_iso

    # Get current UTC time (timezone-aware)
    now = utc_now()

    # Convert to ISO format for storage/API
    timestamp_str = format_iso(now)

    # Convert naive datetime to UTC
    utc_dt = to_utc(naive_datetime)
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Union
import logging

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Get the current UTC time as a timezone-aware datetime.

    Returns:
        datetime: Current UTC time with tzinfo=timezone.utc
    """
    return datetime.now(timezone.utc)


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert a datetime to UTC.

    If the datetime is naive (no timezone), it's assumed to be UTC.
    If it has a timezone, it's converted to UTC.

    Args:
        dt: A datetime object (naive or timezone-aware)

    Returns:
        datetime: UTC datetime with tzinfo=timezone.utc, or None if input is None
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        # Naive datetime - assume it's already UTC
        return dt.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC
        return dt.astimezone(timezone.utc)


def format_iso(dt: Optional[datetime]) -> Optional[str]:
    """Format a datetime as ISO 8601 string.

    Args:
        dt: A datetime object

    Returns:
        str: ISO 8601 formatted string (e.g., "2024-01-15T10:30:00+00:00")
              or None if input is None
    """
    if dt is None:
        return None

    # Ensure UTC timezone
    utc_dt = to_utc(dt)
    return utc_dt.isoformat()


def parse_iso(iso_string: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 string to a timezone-aware datetime.

    Args:
        iso_string: ISO 8601 formatted string

    Returns:
        datetime: Timezone-aware datetime in UTC, or None if input is None/empty
    """
    if not iso_string:
        return None

    try:
        # Python 3.11+ supports fromisoformat with 'Z'
        if iso_string.endswith('Z'):
            iso_string = iso_string[:-1] + '+00:00'

        dt = datetime.fromisoformat(iso_string)
        return to_utc(dt)
    except ValueError as e:
        log.warning(f"Failed to parse ISO datetime '{iso_string}': {e}")
        return None


def utc_timestamp() -> float:
    """Get the current UTC time as a Unix timestamp.

    Returns:
        float: Unix timestamp (seconds since epoch)
    """
    return utc_now().timestamp()


def from_timestamp(ts: Optional[float]) -> Optional[datetime]:
    """Convert a Unix timestamp to a UTC datetime.

    Args:
        ts: Unix timestamp (seconds since epoch)

    Returns:
        datetime: UTC datetime, or None if input is None
    """
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# Backward compatibility helpers
def utcnow() -> datetime:
    """Deprecated: Use utc_now() instead.

    Returns timezone-aware UTC datetime for backward compatibility.
    """
    return utc_now()


def now_utc() -> datetime:
    """Alias for utc_now() for code clarity."""
    return utc_now()
