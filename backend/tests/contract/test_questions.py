"""FT-M5: question bank, quality checks, AI draft gating."""

from tests.conftest import create_question


async def test_create_valid_mcq(client, admin):
    question = await create_question(client, admin["headers"], "mcq")
    assert question["status"] == "active"
    assert question["current_version"]["version"] == 1


async def test_structurally_invalid_mcq_422(client, admin):
    response = await client.post(
        "/api/v1/questions",
        json={
            "qtype": "mcq",
            "title": "Broken question",
            "config": {"options": [{"id": "a", "text": "only one"}],
                       "correct_option_ids": []},
        },
        headers=admin["headers"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_structure"


async def test_edit_creates_new_version(client, admin):
    question = await create_question(client, admin["headers"], "mcq", "Original title here")
    payload = {
        "qtype": "mcq",
        "title": "Edited title here",
        "answer_type": "single_choice",
        "config": question["current_version"]["config"],
    }
    response = await client.put(
        f"/api/v1/questions/{question['id']}", json=payload, headers=admin["headers"]
    )
    assert response.status_code == 200
    assert response.json()["data"]["current_version"]["version"] == 2


async def test_ai_generation_creates_drafts_only(client, admin):
    """FR-042/043: AI output lands as draft with stored metadata."""
    response = await client.post(
        "/api/v1/questions/ai-generate",
        json={"prompt": "python basics", "qtype": "mcq", "count": 3, "topic": "python"},
        headers=admin["headers"],
    )
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert len(data["question_ids"]) == 3

    detail = await client.get(
        f"/api/v1/questions/{data['question_ids'][0]}", headers=admin["headers"]
    )
    body = detail.json()["data"]
    assert body["status"] == "draft"
    assert body["source"] == "ai"

    generation = await client.get(
        f"/api/v1/questions/ai-generations/{data['generation_id']}",
        headers=admin["headers"],
    )
    assert generation.json()["data"]["model"] == "stub"


async def test_ai_draft_cannot_activate_without_approval(client, admin):
    response = await client.post(
        "/api/v1/questions/ai-generate",
        json={"prompt": "sql", "qtype": "mcq", "count": 1, "topic": "sql"},
        headers=admin["headers"],
    )
    question_id = response.json()["data"]["question_ids"][0]

    blocked = await client.post(
        f"/api/v1/questions/{question_id}/status",
        json={"status": "active"},
        headers=admin["headers"],
    )
    assert blocked.status_code == 409  # FR-043

    approved = await client.post(
        f"/api/v1/questions/{question_id}/approve", headers=admin["headers"]
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "active"

    detail = await client.get(f"/api/v1/questions/{question_id}", headers=admin["headers"])
    assert detail.json()["data"]["approved_by"] == admin["user_id"]


async def test_duplicate_question_flagged(client, admin):
    await create_question(
        client, admin["headers"], "mcq", "What is polymorphism in OOP exactly"
    )
    duplicate = await create_question(
        client, admin["headers"], "mcq", "What is polymorphism in OOP exactly"
    )
    assert any(f["kind"] == "duplicate" for f in duplicate["quality_flags"])


async def test_deactivate_and_soft_delete(client, admin):
    question = await create_question(client, admin["headers"], "mcq", "Disposable question")
    response = await client.post(
        f"/api/v1/questions/{question['id']}/status",
        json={"status": "inactive"},
        headers=admin["headers"],
    )
    assert response.json()["data"]["status"] == "inactive"
    deleted = await client.delete(
        f"/api/v1/questions/{question['id']}", headers=admin["headers"]
    )
    assert deleted.status_code == 200
    gone = await client.get(f"/api/v1/questions/{question['id']}", headers=admin["headers"])
    assert gone.status_code == 404


async def test_delete_blocked_when_pinned_in_frozen_version(client, admin):
    """FT-M5-05: a question pinned inside a started (frozen) assessment version
    cannot be deleted."""
    from tests.conftest import add_candidate, build_published_assessment, candidate_login

    assessment = await build_published_assessment(client, admin, with_coding=False,
                                                  with_text=True)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    started = await client.post(
        "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
    )
    assert started.status_code == 200

    questions = await client.get(
        "/api/v1/questions", params={"size": 100}, headers=admin["headers"]
    )
    target = next(
        q for q in questions.json()["data"]["items"]
        if q["current_version"]["qtype"] == "text"
    )
    blocked = await client.delete(
        f"/api/v1/questions/{target['id']}", headers=admin["headers"]
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "pinned_in_frozen_version"
