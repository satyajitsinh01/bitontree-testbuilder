"""FT-M8: event ingest, evidence, severity policy, admin timeline, authz."""

import base64

from tests.conftest import add_candidate, build_published_assessment, candidate_login, now

# 1x1 transparent PNG
TINY_PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA"
        "60e6kgAAAABJRU5ErkJggg=="
    )
).decode()


async def _live_session(client, admin, settings_override=None):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    if settings_override:
        await client.patch(
            f"/api/v1/assessments/{assessment['id']}",
            json={"settings": settings_override},
            headers=admin["headers"],
        )
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    state = (
        await client.post(
            "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
        )
    ).json()["data"]
    return assessment, headers, state


async def test_event_batch_ingest_and_timeline(client, admin):
    _, headers, state = await _live_session(client, admin)
    response = await client.post(
        "/api/v1/exam/proctoring/events",
        json={
            "events": [
                {"kind": "tab_switch", "occurred_at": now().isoformat()},
                {"kind": "fullscreen_exit", "occurred_at": now().isoformat()},
                {"kind": "camera_lost", "occurred_at": now().isoformat(),
                 "detail": {"reason": "permission revoked"}},
            ]
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["accepted"] == 3

    timeline = await client.get(
        f"/api/v1/sessions/{state['session_id']}/proctoring/timeline",
        headers=admin["headers"],
    )
    events = timeline.json()["data"]["events"]
    assert [e["kind"] for e in events] == ["tab_switch", "fullscreen_exit", "camera_lost"]
    severities = {e["kind"]: e["severity"] for e in events}
    assert severities["camera_lost"] == "red_flag"  # standard policy default
    assert severities["tab_switch"] == "warning"

    flags = await client.get(
        f"/api/v1/sessions/{state['session_id']}/proctoring/flags",
        headers=admin["headers"],
    )
    data = flags.json()["data"]
    assert len(data["red_flags"]) == 1 and len(data["warnings"]) == 2


async def test_invalid_event_kind_422(client, admin):
    _, headers, _ = await _live_session(client, admin)
    response = await client.post(
        "/api/v1/exam/proctoring/events",
        json={"events": [{"kind": "made_up_kind"}]},
        headers=headers,
    )
    assert response.status_code == 422


async def test_lenient_policy_downgrades_severity(client, admin):
    """FR-076: lenient policy logs everything as info."""
    _, headers, state = await _live_session(
        client, admin, settings_override={"proctoring_policy": "lenient"}
    )
    await client.post(
        "/api/v1/exam/proctoring/events",
        json={"events": [{"kind": "camera_lost"}]},
        headers=headers,
    )
    flags = await client.get(
        f"/api/v1/sessions/{state['session_id']}/proctoring/flags",
        headers=admin["headers"],
    )
    data = flags.json()["data"]
    assert data["red_flags"] == [] and data["warnings"] == []


async def test_evidence_upload_and_flag_counts_in_report(client, admin):
    _, headers, state = await _live_session(client, admin)
    upload = await client.post(
        "/api/v1/exam/proctoring/evidence",
        json={"image_base64": f"data:image/png;base64,{TINY_PNG}"},
        headers=headers,
    )
    assert upload.status_code == 200
    assert upload.json()["data"]["object_key"].startswith("evidence/")

    await client.post(
        "/api/v1/exam/proctoring/events",
        json={"events": [{"kind": "camera_lost"}, {"kind": "tab_switch"}]},
        headers=headers,
    )
    await client.post("/api/v1/exam/submit", json={"confirm": True}, headers=headers)

    report = await client.get(
        f"/api/v1/sessions/{state['session_id']}/report", headers=admin["headers"]
    )
    data = report.json()["data"]
    assert data["red_flag_count"] == 1
    assert data["warning_count"] == 1
    assert len(data["proctoring_timeline"]) == 2

    timeline = await client.get(
        f"/api/v1/sessions/{state['session_id']}/proctoring/timeline",
        headers=admin["headers"],
    )
    assert len(timeline.json()["data"]["evidence"]) == 1


async def test_invalid_image_logs_capture_failed(client, admin):
    _, headers, state = await _live_session(client, admin)
    response = await client.post(
        "/api/v1/exam/proctoring/evidence",
        json={"image_base64": "data:image/png;base64,!!!not-base64!!!"},
        headers=headers,
    )
    assert response.status_code == 422
    timeline = await client.get(
        f"/api/v1/sessions/{state['session_id']}/proctoring/timeline",
        headers=admin["headers"],
    )
    kinds = [e["kind"] for e in timeline.json()["data"]["events"]]
    assert "capture_failed" in kinds  # FR-072: never silently dropped


async def test_candidate_cannot_read_timeline(client, admin):
    _, headers, state = await _live_session(client, admin)
    response = await client.get(
        f"/api/v1/sessions/{state['session_id']}/proctoring/timeline", headers=headers
    )
    assert response.status_code == 403
