"""
Calendar helpers for statement and due dates.
Days are stored as a day-of-month (1-31). The next occurrence uses the real
calendar, including short months, instead of a fixed 30-day modulo.
"""

import calendar
from datetime import date, datetime, timezone


def days_until_day_of_month(day: int, today: date | None = None) -> int:
    """
    Returns how many days until the next occurrence of `day` (1-31).
    A day later than the current month's length lands on that month's last day.
    Zero means the event is today.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()

    day = max(1, min(int(day), 31))
    year, month = today.year, today.month
    last_day = calendar.monthrange(year, month)[1]
    target = date(year, month, min(day, last_day))
    if target < today:
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        last_day = calendar.monthrange(year, month)[1]
        target = date(year, month, min(day, last_day))
    return (target - today).days
