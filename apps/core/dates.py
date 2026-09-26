"""Calendar-date helpers. Event dates are stored as ISO strings (YYYY-MM-DD)."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime

from django.utils import timezone


def parse_iso(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def today() -> date:
    return timezone.localdate()


def format_long(value) -> str:
    """20 July 2025"""
    d = parse_iso(value)
    return f"{d.day} {calendar.month_name[d.month]} {d.year}" if d else ""


@dataclass(frozen=True)
class Duration:
    years: int
    months: int
    days: int
    total_days: int

    @property
    def parts(self) -> list[tuple[int, str]]:
        def unit(n: int, word: str) -> tuple[int, str]:
            return n, word if n == 1 else f"{word}s"

        return [unit(self.years, "year"), unit(self.months, "month"), unit(self.days, "day")]


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def duration_between(start: date, end: date) -> Duration | None:
    """Calendar-aware years/months/days between two dates (None if start is in the future)."""
    if start is None or end < start:
        return None
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if _add_months(start, months) > end:
        months -= 1
    anchor = _add_months(start, months)
    return Duration(
        years=months // 12,
        months=months % 12,
        days=(end - anchor).days,
        total_days=(end - start).days,
    )


def years_ago_label(event: date, on: date) -> str:
    years = on.year - event.year
    if years <= 0:
        return "Earlier this year" if event < on else "Today"
    return "1 year ago" if years == 1 else f"{years} years ago"


def month_matrix(year: int, month: int) -> list[list[date | None]]:
    """Weeks (Monday first) for a month grid; days outside the month are None."""
    cal = calendar.Calendar(firstweekday=0)
    return [[d if d.month == month else None for d in week] for week in cal.monthdatescalendar(year, month)]


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    d = _add_months(date(year, month, 1), delta)
    return d.year, d.month
