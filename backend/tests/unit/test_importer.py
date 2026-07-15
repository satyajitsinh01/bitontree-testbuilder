import pytest

from testbuilder.services.importer import CSV_TEMPLATE, parse_rows, validate_row


def _row(**overrides):
    base = {
        "studentId": "STU-1001",
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+919876543210",
        "cgpa": "8.75",
    }
    base.update(overrides)
    return base


def test_valid_row_passes():
    clean, error = validate_row(_row())
    assert error is None
    assert clean["student_id"] == "STU-1001"
    assert clean["email"] == "jane@example.com"
    assert clean["cgpa"] == 8.75


def test_student_id_required():
    _, error = validate_row(_row(studentId="  "))
    assert "studentId" in error


def test_email_lowercased():
    clean, _ = validate_row(_row(email="JANE@Example.COM"))
    assert clean["email"] == "jane@example.com"


def test_invalid_email_rejected():
    _, error = validate_row(_row(email="not-an-email"))
    assert "invalid email" in error


def test_missing_name_rejected():
    _, error = validate_row(_row(name="  "))
    assert "name" in error


def test_invalid_phone_rejected():
    _, error = validate_row(_row(phone="abc"))
    assert "invalid phone" in error


def test_phone_must_be_indian_mobile():
    _, error = validate_row(_row(phone="+9198765432109"))
    assert "invalid phone" in error
    _, error = validate_row(_row(phone="98765"))
    assert "invalid phone" in error
    _, error = validate_row(_row(phone="1234567890"))
    assert "invalid phone" in error
    clean, error = validate_row(_row(phone="98765 432-10"))
    assert error is None and clean["phone"] == "9876543210"
    clean, error = validate_row(_row(phone="+91 98765 43210"))
    assert error is None and clean["phone"] == "+919876543210"


@pytest.mark.parametrize("cgpa", ["", "not-a-number", "-0.1", "10.01", "nan", "inf"])
def test_invalid_cgpa_rejected(cgpa):
    _, error = validate_row(_row(cgpa=cgpa))
    assert "between 0 and 10" in error


def test_csv_template_parses():
    rows = parse_rows("template.csv", CSV_TEMPLATE.encode())
    assert len(rows) == 1
    clean, error = validate_row(rows[0])
    assert error is None and clean["student_id"] == "STU-1001"


def test_wrong_csv_headers_rejected():
    with pytest.raises(ValueError, match="expected columns"):
        parse_rows("old.csv", b"name,email,phone,start_at,end_at\nJane,jane@example.com,,x,y")
