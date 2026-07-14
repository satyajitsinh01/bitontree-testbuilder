"""Bulk candidate import from CSV/XLSX (research R7). Per-row validation with a
row-level error report; valid rows import even when others fail (FR-012)."""

import csv
import io
import re
from datetime import datetime

from openpyxl import load_workbook

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Indian mobile: exactly 10 digits starting 6-9, optional +91 prefix
INDIAN_MOBILE_RE = re.compile(r"^(?:\+91)?[6-9]\d{9}$")
COLUMNS = ["name", "email", "phone", "start_at", "end_at"]


def normalize_phone(raw: str) -> str:
    return re.sub(r"[\s()\-]", "", raw)


def parse_rows(filename: str, content: bytes) -> list[dict]:
    """Returns raw dict rows keyed by COLUMNS."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        workbook = load_workbook(io.BytesIO(content), read_only=True)
        sheet = workbook.active
        rows = []
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i == 0:
                continue  # header
            values = ["" if v is None else str(v) for v in row[: len(COLUMNS)]]
            values += [""] * (len(COLUMNS) - len(values))
            rows.append(dict(zip(COLUMNS, values, strict=True)))
        return rows
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        if i == 0:
            continue
        values = [v.strip() for v in row[: len(COLUMNS)]]
        values += [""] * (len(COLUMNS) - len(values))
        rows.append(dict(zip(COLUMNS, values, strict=True)))
    return rows


def _parse_dt(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def validate_row(row: dict, now: datetime) -> tuple[dict | None, str | None]:
    """Returns (clean_row, error). clean_row has name, email, phone, start_at, end_at."""
    name = row.get("name", "").strip()
    email = row.get("email", "").strip().lower()
    phone = normalize_phone(row.get("phone", "").strip())
    if not name:
        return None, "name is required"
    if not EMAIL_RE.match(email):
        return None, f"invalid email: {email or '(empty)'}"
    if phone and not INDIAN_MOBILE_RE.match(phone):
        return None, f"invalid phone (expected 10-digit Indian mobile): {phone}"
    start_at = _parse_dt(row.get("start_at", ""))
    end_at = _parse_dt(row.get("end_at", ""))
    if start_at is None or end_at is None:
        return None, "start_at/end_at must be ISO datetimes (YYYY-MM-DD HH:MM)"
    if end_at <= start_at:
        return None, "end_at must be after start_at"
    if end_at <= now:
        return None, "assessment window is entirely in the past"
    return (
        {"name": name, "email": email, "phone": phone, "start_at": start_at, "end_at": end_at},
        None,
    )


CSV_TEMPLATE = (
    "name,email,phone,start_at,end_at\n"
    "Jane Doe,jane@example.com,+919876543210,2026-08-01 10:00,2026-08-01 14:00\n"
)
