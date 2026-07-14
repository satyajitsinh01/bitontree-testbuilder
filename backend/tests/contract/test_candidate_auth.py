"""FT-M3: window gating, one active session, admin recovery session."""

from datetime import timedelta

from tests.conftest import add_candidate, build_published_assessment, candidate_login, now


async def test_login_before_window_shows_starts_soon(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(
        client, admin, assessment["id"],
        start_delta=timedelta(hours=1), end_delta=timedelta(hours=3),
    )
    response = await client.post(
        "/api/v1/auth/candidate/login",
        json={"username": assignment["username"],
              "password": assignment["initial_password"]},
    )
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "window_not_started"
    assert error["message"] == "Your test will start soon."
    assert error["starts_at"]


async def test_login_after_window_expired(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(
        client, admin, assessment["id"],
        start_delta=timedelta(hours=-3), end_delta=timedelta(minutes=-1),
    )
    response = await client.post(
        "/api/v1/auth/candidate/login",
        json={"username": assignment["username"],
              "password": assignment["initial_password"]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Assessment window has expired."


async def test_second_login_rejected_while_session_live(client, admin):
    """FR-023: one active session; a live session blocks a second device."""
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    started = await client.post(
        "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
    )
    assert started.status_code == 200

    second = await client.post(
        "/api/v1/auth/candidate/login",
        json={"username": assignment["username"],
              "password": assignment["initial_password"]},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "session_active"


async def test_double_start_409(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    first = await client.post(
        "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
    )
    assert second.status_code == 409


async def test_admin_recovery_session_terminates_and_reopens(client, admin):
    """FR-024: recovery session terminates the active one and lets the candidate
    back in, optionally with new timings."""
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    await client.post("/api/v1/exam/start", json={"acknowledged_rules": True},
                      headers=headers)

    recovery = await client.post(
        f"/api/v1/assignments/{assignment['id']}/sessions",
        json={"window_end_at": (now() + timedelta(hours=4)).isoformat()},
        headers=admin["headers"],
    )
    assert recovery.status_code == 201
    assert recovery.json()["data"]["terminated_sessions"] == 1

    # the old session reports terminated (FE shows "session ended by administrator")
    state = await client.get("/api/v1/exam/state", headers=headers)
    assert state.status_code == 200
    assert state.json()["data"]["status"] == "terminated"

    # candidate can start fresh
    restarted = await client.post(
        "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
    )
    assert restarted.status_code == 200

    # audit trail records the reset (FR-005)
    logs = await client.get(
        "/api/v1/admin/audit-logs", params={"action": "session.reset"},
        headers=admin["headers"],
    )
    assert logs.json()["data"]["total"] >= 1


async def test_rules_acknowledgment_required(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    response = await client.post(
        "/api/v1/exam/start", json={"acknowledged_rules": False}, headers=headers
    )
    assert response.status_code == 422
