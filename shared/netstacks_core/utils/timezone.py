"""
Timezone Utilities for NetStacks

Provides consistent timezone handling across the application.
All timestamps are stored in UTC and converted to local time for display.
"""

import os
from datetime import datetime, timezone
from typing import Optional


def get_system_timezone() -> str:
    """Get the system timezone from environment variable TZ or default to UTC."""
    return os.environ.get('TZ', 'UTC')


def utc_now() -> datetime:
    """
    Get current time in UTC with timezone info.

    Always use this instead of datetime.utcnow() or datetime.now()
    for database timestamps.

    Returns:
        datetime: Current UTC time with tzinfo=timezone.utc
    """
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """
    Get current UTC time as ISO format string.

    Returns:
        str: ISO 8601 formatted string
    """
    return utc_now().isoformat()


def to_utc(dt: datetime) -> datetime:
    """
    Convert a datetime to UTC.

    If the datetime is naive (no timezone), assumes it's in local time.

    Args:
        dt: A datetime object (naive or timezone-aware)

    Returns:
        datetime: UTC datetime with tzinfo=timezone.utc
    """
    if dt.tzinfo is None:
        # Naive datetime - assume local time
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_iso_datetime(iso_string: str) -> Optional[datetime]:
    """
    Parse an ISO format datetime string.

    Returns timezone-aware datetime in UTC.

    Args:
        iso_string: ISO 8601 formatted string

    Returns:
        datetime: UTC datetime, or None if parsing fails
    """
    if not iso_string:
        return None

    try:
        # Handle various ISO formats
        if iso_string.endswith('Z'):
            iso_string = iso_string[:-1] + '+00:00'

        dt = datetime.fromisoformat(iso_string)

        # If naive, treat as UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def format_for_display(dt: datetime, include_tz: bool = True) -> str:
    """
    Format a datetime for display.

    Converts UTC to local time if TZ is set.

    Args:
        dt: A datetime object
        include_tz: Whether to include timezone in output

    Returns:
        str: Formatted datetime string
    """
    if dt is None:
        return ''

    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    if include_tz:
        return dt.isoformat()
    else:
        return dt.strftime('%Y-%m-%d %H:%M:%S')


def datetime_to_iso(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert datetime to ISO format string, handling None.

    Args:
        dt: A datetime object or None

    Returns:
        str: ISO 8601 formatted string, or None if input is None
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume UTC for naive datetimes from database
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
