"""FT-M2 + FT-M10: candidate management, import, emails."""

import io
from datetime import timedelta

from tests.conftest import add_candidate, build_published_assessment, now


async def test_add_candidate_and_duplicate_409(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    first = await add_candidate(client, admin, assessment["id"], email="dup@example.com")
    assert first["username"] and first["initial_password"]

    # same email, case-insensitive -> 409 (FR-013)
    response = await client.post(
        f"/api/v1/assessments/{assessment['id']}/assignments",
        json={
            "full_name": "Jane Again",
            "email": "DUP@example.com",
            "window_start_at": now().isoformat(),
            "window_end_at": (now() + timedelta(hours=1)).isoformat(),
        },
        headers=admin["headers"],
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_email_in_assessment"


async def test_same_email_allowed_in_other_assessment(client, admin):
    """FR-014: independent assignments per assessment."""
    first = await build_published_assessment(client, admin, with_coding=False)
    second = await build_published_assessment(client, admin, with_coding=False)
    a1 = await add_candidate(client, admin, first["id"], email="multi@example.com")
    a2 = await add_candidate(client, admin, second["id"], email="multi@example.com")
    assert a1["username"] != a2["username"]  # separate credentials (FR-016)


async def test_invitation_email_recorded_and_toggle_respected(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    with_email = await add_candidate(client, admin, assessment["id"], email="a@x.com")
    emails = await client.get(
        f"/api/v1/assignments/{with_email['id']}/emails", headers=admin["headers"]
    )
    kinds = [e["kind"] for e in emails.json()["data"]["items"]]
    assert "invitation" in kinds

    response = await client.post(
        f"/api/v1/assessments/{assessment['id']}/assignments",
        json={
            "full_name": "No Mail",
            "email": "b@x.com",
            "window_start_at": now().isoformat(),
            "window_end_at": (now() + timedelta(hours=1)).isoformat(),
            "send_email": False,
        },
        headers=admin["headers"],
    )
    no_email = response.json()["data"]
    emails = await client.get(
        f"/api/v1/assignments/{no_email['id']}/emails", headers=admin["headers"]
    )
    assert emails.json()["data"]["items"] == []  # FR-018/FR-092


async def test_resend_regenerates_credentials(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"], email="r@x.com")
    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/resend-invitation",
        headers=admin["headers"],
    )
    assert response.status_code == 200
    emails = await client.get(
        f"/api/v1/assignments/{assignment['id']}/emails", headers=admin["headers"]
    )
    kinds = [e["kind"] for e in emails.json()["data"]["items"]]
    assert "resend" in kinds
    # old password no longer works
    login = await client.post(
        "/api/v1/auth/candidate/login",
        json={"username": assignment["username"],
              "password": assignment["initial_password"]},
    )
    assert login.status_code == 401


async def test_reschedule_and_remove(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"], email="m@x.com")
    new_end = (now() + timedelta(hours=6)).isoformat()
    patched = await client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        json={"window_end_at": new_end},
        headers=admin["headers"],
    )
    assert patched.status_code == 200

    removed = await client.delete(
        f"/api/v1/assignments/{assignment['id']}", headers=admin["headers"]
    )
    assert removed.status_code == 200
    # credentials expire on removal (FR-017)
    login = await client.post(
        "/api/v1/auth/candidate/login",
        json={"username": assignment["username"],
              "password": assignment["initial_password"]},
    )
    assert login.status_code == 401


def _csv_bytes() -> bytes:
    start = (now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    end = (now() + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
    rows = [
        "name,email,phone,start_at,end_at",
        f"Alice A,alice@x.com,+911111111111,{start},{end}",
        f"Bob B,not-an-email,+912222222222,{start},{end}",  # invalid email
        f"Cara C,cara@x.com,+913333333333,{start},{end}",
        f"Dupe D,alice@x.com,+914444444444,{start},{end}",  # duplicate in file
    ]
    return "\n".join(rows).encode()


async def test_bulk_import_partial_success_with_error_report(client, admin):
    """FR-012/013: valid rows import; invalid rows come back with row numbers."""
    assessment = await build_published_assessment(client, admin, with_coding=False)
    response = await client.post(
        f"/api/v1/assessments/{assessment['id']}/assignments/import",
        files={"file": ("candidates.csv", io.BytesIO(_csv_bytes()), "text/csv")},
        headers=admin["headers"],
    )
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["total_rows"] == 4
    assert data["imported_rows"] == 2  # alice + cara
    assert data["failed_rows"] == 2

    batch = await client.get(
        f"/api/v1/import-batches/{data['batch_id']}", headers=admin["headers"]
    )
    errors = batch.json()["data"]["errors"]
    assert {e["row"] for e in errors} == {3, 5}
    assert any("invalid email" in e["error"] for e in errors)
    assert any("duplicate email in file" in e["error"] for e in errors)

    listing = await client.get(
        f"/api/v1/assessments/{assessment['id']}/assignments", headers=admin["headers"]
    )
    assert listing.json()["data"]["total"] == 2


async def test_import_template_downloadable(client, admin):
    response = await client.get("/api/v1/import-batches/template", headers=admin["headers"])
    assert response.status_code == 200
    assert response.text.startswith("name,email,phone,start_at,end_at")
