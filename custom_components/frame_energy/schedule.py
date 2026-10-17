"""When the integration updates the picture by itself.

Plain Python with no Home Assistant imports, so it can be tested on its own.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def interval_minutes(value) -> int | None:
    """Minutes between updates, or None for "manual" (no updates by itself)."""
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    return minutes if minutes > 0 else None


def schedule_minutes(minutes: int) -> list[int]:
    """Minutes of the hour to run at, lined up with the clock.

    Every 15 minutes means :00, :15, :30 and :45, the same times an
    automation with ``minutes: "/15"`` uses. So the two meet, and the
    double-update check below can catch it.
    """
    return list(range(0, 60, minutes))


def should_skip(busy: bool, last_generated: datetime | None, now: datetime, minutes: int) -> bool:
    """True if a scheduled update is not needed right now.

    - busy: another update (for example from the user's automation) is running.
    - last_generated: a picture was already made less than half an interval
      ago, so this update would only repeat it.
    """
    if busy:
        return True
    if last_generated is None:
        return False
    return now - last_generated < timedelta(minutes=minutes / 2)
