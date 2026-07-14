"""FT-M4-04/05 + timezone-edge behavior: server-side deadline enforcement via the
lazy check (research R3) under time travel."""

from datetime import UTC, datetime, timedelta

import time_machine
from tests.conftest import add_candidate, build_published_assessment, candidate_login


async def test_section_timeout_auto_advances(client, admin):
    assessment = await build_published_assessment(
        client, admin, with_coding=False, section_minutes=(10, 30)
    )
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    state = (
        await client.post(
            "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
        )
    ).json()["data"]
    first_section = state["sections"][0]
    assert first_section["status"] == "active"

    with time_machine.travel(datetime.now(UTC) + timedelta(minutes=11), tick=False):
        moved = (await client.get("/api/v1/exam/state", headers=headers)).json()["data"]
    sections = {s["name"]: s for s in moved["sections"]}
    assert sections["Aptitude"]["status"] == "auto_submitted"  # FR-036
    assert sections["Deep Dive"]["status"] == "active"
    assert moved["current_section_id"] == sections["Deep Dive"]["section_id"]


async def test_exam_end_auto_submits_everything(client, admin):
    assessment = await build_published_assessment(
        client, admin, with_coding=False, section_minutes=(10, 10)
    )
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    state = (
        await client.post(
            "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
        )
    ).json()["data"]
    question = state["questions"][0]
    await client.put(
        f"/api/v1/exam/questions/{question['session_question_id']}/answer",
        json={"payload": {"selected_option_ids": ["a"]}},
        headers=headers,
    )

    with time_machine.travel(datetime.now(UTC) + timedelta(minutes=21), tick=False):
        final = (await client.get("/api/v1/exam/state", headers=headers)).json()["data"]
        assert final["status"] == "auto_submitted"  # FR-037

        # answered state was preserved and evaluated
        results = (
            await client.get(
                f"/api/v1/assessments/{assessment['id']}/results", headers=admin["headers"]
            )
        ).json()["data"]
        assert results["items"][0]["status"] == "auto_submitted"
        report = (
            await client.get(
                f"/api/v1/sessions/{results['items'][0]['session_id']}/report",
                headers=admin["headers"],
            )
        ).json()["data"]
        aptitude = next(s for s in report["section_scores"] if s["name"] == "Aptitude")
        assert aptitude["attempted"] == 1


async def test_credentials_expire_after_window_end(client, admin):
    """FR-017/FR-026: past window end the candidate token stops working."""
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(
        client, admin, assessment["id"], end_delta=timedelta(minutes=30)
    )
    headers = await candidate_login(client, assignment)
    with time_machine.travel(datetime.now(UTC) + timedelta(minutes=31), tick=False):
        response = await client.get("/api/v1/exam/summary", headers=headers)
        assert response.status_code == 401
        login = await client.post(
            "/api/v1/auth/candidate/login",
            json={"username": assignment["username"],
                  "password": assignment["initial_password"]},
        )
        assert login.status_code == 403
        assert login.json()["error"]["code"] == "window_expired"
