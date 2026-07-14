"""Unified email+password login for admins and candidates, plus credential
invalidation after submission."""

from tests.conftest import add_candidate, build_published_assessment


async def test_admin_logs_in_via_unified_endpoint(client, admin):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Passw0rd!123"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["kind"] == "admin"
    assert data["access_token"]
    assert set(data["roles"]) == {"hr_admin", "test_creator", "evaluator"}


async def test_candidate_logs_in_with_email_and_password(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"], email="uni@example.com")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "uni@example.com", "password": assignment["initial_password"]},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["kind"] == "candidate"
    assert data["assignment_summary"]["assessment_title"] == "Backend Screening"

    # token works on the exam surface
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    summary = await client.get("/api/v1/exam/summary", headers=headers)
    assert summary.status_code == 200


async def test_wrong_password_401(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    await add_candidate(client, admin, assessment["id"], email="wrong@example.com")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "not-the-password"},
    )
    assert response.status_code == 401


async def test_same_email_two_assessments_password_disambiguates(client, admin):
    """FR-014: the per-assignment password picks the right assignment."""
    first = await build_published_assessment(client, admin, with_coding=False)
    second = await build_published_assessment(client, admin, with_coding=False)
    a1 = await add_candidate(client, admin, first["id"], email="both@example.com")
    a2 = await add_candidate(client, admin, second["id"], email="both@example.com")

    r1 = await client.post(
        "/api/v1/auth/login",
        json={"email": "both@example.com", "password": a1["initial_password"]},
    )
    r2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "both@example.com", "password": a2["initial_password"]},
    )
    assert r1.json()["data"]["assignment_summary"]["assignment_id"] == a1["id"]
    assert r2.json()["data"]["assignment_summary"]["assignment_id"] == a2["id"]


async def test_submitted_assessment_invalidates_credentials(client, admin):
    """After final submission the same credentials must be rejected."""
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"], email="done@example.com")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "done@example.com", "password": assignment["initial_password"]},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    await client.post("/api/v1/exam/start", json={"acknowledged_rules": True},
                      headers=headers)
    submitted = await client.post("/api/v1/exam/submit", json={"confirm": True},
                                  headers=headers)
    assert submitted.status_code == 200

    # first retry: explicit "already submitted" message
    retry = await client.post(
        "/api/v1/auth/login",
        json={"email": "done@example.com", "password": assignment["initial_password"]},
    )
    assert retry.status_code == 403
    assert retry.json()["error"]["code"] == "already_submitted"

    # credentials are now permanently expired -> plain 401 afterwards
    again = await client.post(
        "/api/v1/auth/login",
        json={"email": "done@example.com", "password": assignment["initial_password"]},
    )
    assert again.status_code == 401

    # legacy username endpoint rejects too
    legacy = await client.post(
        "/api/v1/auth/candidate/login",
        json={"username": assignment["username"],
              "password": assignment["initial_password"]},
    )
    assert legacy.status_code == 401


async def test_exam_duration_is_sum_of_section_minutes(client, admin):
    """ends_at - started_at == sum of section durations (10 + 10 here), because the
    candidate window is much wider."""
    from datetime import datetime

    assessment = await build_published_assessment(
        client, admin, with_coding=False, section_minutes=(10, 10)
    )
    assignment = await add_candidate(client, admin, assessment["id"], email="t@example.com")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "t@example.com", "password": assignment["initial_password"]},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    state = (
        await client.post("/api/v1/exam/start", json={"acknowledged_rules": True},
                          headers=headers)
    ).json()["data"]
    ends = datetime.fromisoformat(state["ends_at"])
    server_now = datetime.fromisoformat(state["server_now"])
    minutes = (ends - server_now).total_seconds() / 60
    assert 19.5 <= minutes <= 20.1