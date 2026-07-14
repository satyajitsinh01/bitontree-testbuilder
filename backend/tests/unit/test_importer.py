from datetime import datetime

from testbuilder.services.importer import CSV_TEMPLATE, parse_rows, validate_row

NOW = datetime(2026, 7, 14, 10, 0, 0)


def _row(**overrides):
    base = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+911234567890",
        "start_at": "2026-08-01 10:00",
        "end_at": "2026-08-01 14:00",
    }
    base.update(overrides)
    return base


def test_valid_row_passes():
    clean, error = validate_row(_row(), NOW)
    assert error is None
    assert clean["email"] == "jane@example.com"
    assert clean["start_at"] < clean["end_at"]


def test_email_lowercased():
    clean, _ = validate_row(_row(email="JANE@Example.COM"), NOW)
    assert clean["email"] == "jane@example.com"


def test_invalid_email_rejected():
    _, error = validate_row(_row(email="not-an-email"), NOW)
    assert "invalid email" in error


def test_missing_name_rejected():
    _, error = validate_row(_row(name="  "), NOW)
    assert "name" in error


def test_invalid_phone_rejected():
    _, error = validate_row(_row(phone="abc"), NOW)
    assert "invalid phone" in error


def test_end_before_start_rejected():
    _, error = validate_row(_row(start_at="2026-08-01 14:00", end_at="2026-08-01 10:00"), NOW)
    assert "after start" in error


def test_window_in_past_rejected():
    _, error = validate_row(
        _row(start_at="2026-01-01 10:00", end_at="2026-01-01 12:00"), NOW
    )
    assert "past" in error


def test_unparseable_dates_rejected():
    _, error = validate_row(_row(start_at="soon", end_at="later"), NOW)
    assert "ISO datetimes" in error


def test_csv_template_parses():
    rows = parse_rows("template.csv", CSV_TEMPLATE.encode())
    assert len(rows) == 1
    clean, error = validate_row(rows[0], NOW)
    assert error is None and clean["name"] == "Jane Doe"
