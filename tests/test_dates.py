import datetime as dt

import pytest

from app.utils.dates import (
    DISPLAY_FORMAT,
    format_date_for_display,
    format_date_iso,
    get_display_format,
    parse_date,
    set_display_format,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("01-07-2026", dt.date(2026, 7, 1)),
        ("01/07/2026", dt.date(2026, 7, 1)),
        ("2026-07-01", dt.date(2026, 7, 1)),
    ],
)
def test_parse_date_supported_formats(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_does_not_assume_us_format():
    # 13 no puede ser mes: solo es interpretable como día/mes/año.
    assert parse_date("13/01/2026") == dt.date(2026, 1, 13)


def test_parse_date_none_and_empty():
    assert parse_date(None) is None
    assert parse_date("") is None


def test_parse_date_invalid_raises():
    with pytest.raises(ValueError):
        parse_date("no-es-fecha")


def test_format_date_for_display():
    assert format_date_for_display(dt.date(2026, 7, 1)) == "01/07/2026"


def test_format_date_iso():
    assert format_date_iso(dt.date(2026, 7, 1)) == "2026-07-01"


def test_set_display_format_changes_output():
    set_display_format("%Y-%m-%d")
    assert format_date_for_display(dt.date(2026, 7, 1)) == "2026-07-01"
    assert get_display_format() == "%Y-%m-%d"


def test_set_display_format_empty_falls_back_to_default():
    set_display_format("")
    assert get_display_format() == DISPLAY_FORMAT
