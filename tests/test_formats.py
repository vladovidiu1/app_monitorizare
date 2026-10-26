from __future__ import annotations

from datetime import date, time

import pytest

from focusdesk.ui.formats import (
    duration_to_text, format_date, parse_date, parse_duration, parse_tags, parse_time,
)


@pytest.mark.parametrize("text,expected", [
    ("", None), ("90", 90), ("1h30", 90), ("1h 30", 90), ("2h", 120), ("45m", 45), ("45 min", 45), ("1,5h", 90),
    ("1.5h", 90), ("1:30", 90), ("0", 0), ("1h30m", 90), ("3 ore", 180),
])
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("bad", ["abc", "1x", "-5", "h", "1h-3"])
def test_parse_duration_invalid(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)


def test_duration_roundtrip_and_unknown_is_empty():
    assert duration_to_text(None) == ""
    for m in (5, 45, 60, 90, 125):
        assert parse_duration(duration_to_text(m)) == m


def test_parse_date_variants():
    today = date(2026, 10, 20)
    assert parse_date("", today) is None
    assert parse_date("azi", today) == today
    assert parse_date("mâine", today) == date(2026, 10, 21)
    assert parse_date("+3", today) == date(2026, 10, 23)
    assert parse_date("25.12.2026", today) == date(2026, 12, 25)
    assert parse_date("2026-12-25", today) == date(2026, 12, 25)
    assert format_date(date(2026, 1, 5)) == "05.01.2026"
    with pytest.raises(ValueError):
        parse_date("31.02.2026", today)
    with pytest.raises(ValueError):
        parse_date("cândva", today)


def test_parse_time_and_tags():
    assert parse_time("") is None
    assert parse_time("9:05") == time(9, 5)
    assert parse_time("14.30") == time(14, 30)
    with pytest.raises(ValueError):
        parse_time("25:00")
    assert parse_tags("SAP, XML; sap ,, XML") == ["SAP", "XML", "sap"]
