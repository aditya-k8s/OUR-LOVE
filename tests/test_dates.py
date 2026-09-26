from datetime import date

from apps.core.dates import duration_between, format_long, month_matrix, years_ago_label


def test_duration_simple():
    d = duration_between(date(2024, 5, 10), date(2026, 9, 27))
    assert (d.years, d.months, d.days) == (2, 4, 17)
    assert d.total_days == (date(2026, 9, 27) - date(2024, 5, 10)).days


def test_duration_month_end_is_calendar_aware():
    d = duration_between(date(2025, 1, 31), date(2025, 3, 1))
    assert (d.years, d.months, d.days) == (0, 1, 1)


def test_duration_leap_day():
    d = duration_between(date(2024, 2, 29), date(2025, 2, 28))
    assert (d.years, d.months, d.days) == (1, 0, 0)
    assert d.total_days == 365


def test_duration_same_day_and_future():
    assert duration_between(date(2025, 7, 19), date(2025, 7, 19)).total_days == 0
    assert duration_between(date(2030, 1, 1), date(2025, 1, 1)) is None


def test_units_are_pluralised():
    d = duration_between(date(2024, 1, 1), date(2025, 2, 2))
    assert d.parts == [(1, "year"), (1, "month"), (1, "day")]


def test_format_long_uk_style():
    assert format_long("2025-07-20") == "20 July 2025"
    assert format_long("") == ""
    assert format_long("not-a-date") == ""


def test_years_ago_label():
    assert years_ago_label(date(2025, 9, 26), date(2026, 9, 26)) == "1 year ago"
    assert years_ago_label(date(2023, 9, 26), date(2026, 9, 26)) == "3 years ago"


def test_month_matrix_starts_monday():
    weeks = month_matrix(2026, 9)
    assert weeks[0][1] == date(2026, 9, 1)  # 1 September 2026 is a Tuesday
    assert weeks[0][0] is None
