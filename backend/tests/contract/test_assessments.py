"""FT-M4: test builder, publish validation, versioning/freeze semantics."""

from tests.conftest import (
    add_candidate,
    build_published_assessment,
    candidate_login,
    create_question,
)


async def test_publish_requires_weightage_100(client, admin):
    assessment = (
        await client.post(
            "/api/v1/assessments", json={"title": "Broken weights"},
            headers=admin["headers"],
        )
    ).json()["data"]
    question = await create_question(client, admin["headers"], "mcq", "Solo question here")
    section = (
        await client.post(
            f"/api/v1/assessments/{assessment['id']}/sections",
            json={"name": "Only", "duration_min": 10, "weightage_pct": 50,
                  "question_count": 1},
            headers=admin["headers"],
        )
    ).json()["data"]
    await client.put(
        f"/api/v1/sections/{section['id']}/questions",
        json={"items": [{"question_id": question["id"]}]},
        headers=admin["headers"],
    )
    response = await client.post(
        f"/api/v1/assessments/{assessment['id']}/publish", headers=admin["headers"]
    )
    assert response.status_code == 422
    assert any("sum to 100" in d for d in response.json()["error"]["details"])


async def test_publish_requires_pool_coverage(client, admin):
    """FR-038: 'pick 10 of N' must have N >= 10 active questions."""
    assessment = (
        await client.post(
            "/api/v1/assessments", json={"title": "Thin pool"}, headers=admin["headers"]
        )
    ).json()["data"]
    question = await create_question(client, admin["headers"], "mcq", "Pool question one")
    section = (
        await client.post(
            f"/api/v1/assessments/{assessment['id']}/sections",
            json={"name": "Pool", "duration_min": 10, "weightage_pct": 100,
                  "question_count": 5},
            headers=admin["headers"],
        )
    ).json()["data"]
    await client.put(
        f"/api/v1/sections/{section['id']}/questions",
        json={"items": [{"question_id": question["id"], "pool_group": "g"}]},
        headers=admin["headers"],
    )
    await client.put(
        f"/api/v1/sections/{section['id']}/pool-rules",
        json={"items": [{"pool_group": "g", "select_count": 5}]},
        headers=admin["headers"],
    )
    response = await client.post(
        f"/api/v1/assessments/{assessment['id']}/publish", headers=admin["headers"]
    )
    assert response.status_code == 422
    assert any("only 1 active" in d for d in response.json()["error"]["details"])


async def test_happy_publish(client, admin):
    assessment = await build_published_assessment(client, admin)
    assert assessment["status"] == "published"
    assert assessment["version"]["total_duration_min"] == 20
    assert len(assessment["version"]["sections"]) == 2
    assert assessment["version"]["sections"][-1]["is_final"] is True


async def test_edit_after_start_forks_new_version(client, admin):
    """FR-034: first candidate start freezes the version; edits fork v2 and the
    in-flight session stays pinned to v1."""
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    started = await client.post(
        "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
    )
    assert started.status_code == 200
    session_v1 = started.json()["data"]["session_id"]

    edited = await client.patch(
        f"/api/v1/assessments/{assessment['id']}",
        json={"title": "Backend Screening v2"},
        headers=admin["headers"],
    )
    assert edited.status_code == 200
    assert edited.json()["data"]["version"]["version"] == 2
    assert edited.json()["data"]["version"]["frozen"] is False

    versions = await client.get(
        f"/api/v1/assessments/{assessment['id']}/versions", headers=admin["headers"]
    )
    items = versions.json()["data"]["items"]
    assert [v["version"] for v in items] == [1, 2]
    assert items[0]["frozen"] is True and items[1]["is_current"] is True

    # candidate exam still runs on the frozen v1
    state = await client.get("/api/v1/exam/state", headers=headers)
    assert state.status_code == 200
    assert state.json()["data"]["session_id"] == session_v1


async def test_frozen_section_edit_409(client, admin):
    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    await client.post("/api/v1/exam/start", json={"acknowledged_rules": True},
                      headers=headers)
    section_id = assessment["version"]["sections"][0]["id"]
    response = await client.patch(
        f"/api/v1/sections/{section_id}",
        json={"name": "Renamed", "duration_min": 5, "weightage_pct": 40},
        headers=admin["headers"],
    )
    assert response.status_code == 409
