"""JSON question import: template format, partial success, draft gating, dedupe
behavior of AI generation."""

import io
import json


async def _upload(client, admin, payload) -> dict:
    response = await client.post(
        "/api/v1/questions/import",
        files={"file": ("bank.json", io.BytesIO(json.dumps(payload).encode()),
                        "application/json")},
        headers=admin["headers"],
    )
    return response


async def test_template_downloadable_and_importable(client, admin):
    """The published template must itself import cleanly."""
    template = await client.get(
        "/api/v1/questions/import-template", headers=admin["headers"]
    )
    assert template.status_code == 200
    payload = template.json()["data"]
    assert {q["qtype"] for q in payload["questions"]} == {"mcq", "text", "coding"}

    response = await _upload(client, admin, payload)
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["imported"] == 4 and data["failed"] == 0


async def test_import_lands_as_draft_and_requires_approval(client, admin):
    payload = {
        "questions": [
            {
                "qtype": "mcq",
                "title": "Imported draft question",
                "difficulty": "hard",
                "config": {
                    "options": [{"id": "a", "text": "yes"}, {"id": "b", "text": "no"}],
                    "correct_option_ids": ["a"],
                },
            }
        ]
    }
    data = (await _upload(client, admin, payload)).json()["data"]
    question_id = data["question_ids"][0]
    detail = (
        await client.get(f"/api/v1/questions/{question_id}", headers=admin["headers"])
    ).json()["data"]
    assert detail["status"] == "draft"
    assert detail["source"] == "import"
    assert detail["current_version"]["difficulty"] == "hard"

    # drafts activate through the approval flow, same as AI output
    approved = await client.post(
        f"/api/v1/questions/{question_id}/approve", headers=admin["headers"]
    )
    assert approved.json()["data"]["status"] == "active"


async def test_import_partial_success_reports_row_errors(client, admin):
    payload = {
        "questions": [
            {  # valid
                "qtype": "mcq",
                "title": "Valid imported question",
                "config": {
                    "options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
                    "correct_option_ids": ["a"],
                },
            },
            {  # broken structure: no correct option
                "qtype": "mcq",
                "title": "Broken imported question",
                "config": {"options": [{"id": "a", "text": "only"}],
                           "correct_option_ids": []},
            },
            {  # unknown type + bad difficulty
                "qtype": "essay",
                "title": "Wrong type",
                "difficulty": "impossible",
                "config": {},
            },
        ]
    }
    data = (await _upload(client, admin, payload)).json()["data"]
    assert data["imported"] == 1
    assert data["failed"] == 2
    assert {e["index"] for e in data["errors"]} == {1, 2}


async def test_import_rejects_malformed_file(client, admin):
    import io as _io

    response = await client.post(
        "/api/v1/questions/import",
        files={"file": ("bank.json", _io.BytesIO(b"not json at all"),
                        "application/json")},
        headers=admin["headers"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_json"

    response = await _upload(client, admin, {"wrong_key": []})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_format"


async def test_ai_generation_respects_difficulty_and_skips_duplicates(
    client, admin, monkeypatch
):
    """The route must pass difficulty through and drop near-duplicates of the
    existing bank and of the same batch."""
    from testbuilder.services import ai as ai_service

    fixed = [
        {
            "title": "What is a hash map exactly?",
            "body": "Pick one.",
            "qtype": "mcq",
            "answer_type": "single_choice",
            "difficulty": "hard",
            "config": {"options": [{"id": "a", "text": "kv store"},
                                   {"id": "b", "text": "list"}],
                       "correct_option_ids": ["a"]},
            "topic": "ds",
            "skills": ["ds"],
        },
        {  # near-identical to the first -> in-batch duplicate
            "title": "What is a hash map exactly?",
            "body": "Pick one.",
            "qtype": "mcq",
            "answer_type": "single_choice",
            "difficulty": "hard",
            "config": {"options": [{"id": "a", "text": "kv store"},
                                   {"id": "b", "text": "list"}],
                       "correct_option_ids": ["a"]},
            "topic": "ds",
            "skills": ["ds"],
        },
    ]
    monkeypatch.setattr(
        ai_service, "generate_questions", lambda *a, **k: (list(fixed), "stub")
    )

    first = (
        await client.post(
            "/api/v1/questions/ai-generate",
            json={"prompt": "ds questions", "qtype": "mcq", "count": 2,
                  "difficulty": "hard", "topic": "ds"},
            headers=admin["headers"],
        )
    ).json()["data"]
    assert len(first["question_ids"]) == 1  # in-batch duplicate skipped
    assert first["skipped_duplicates"] == 1

    detail = (
        await client.get(
            f"/api/v1/questions/{first['question_ids'][0]}", headers=admin["headers"]
        )
    ).json()["data"]
    assert detail["current_version"]["difficulty"] == "hard"

    # second run: everything is now a bank duplicate (draft counts too)
    second = (
        await client.post(
            "/api/v1/questions/ai-generate",
            json={"prompt": "ds questions", "qtype": "mcq", "count": 2,
                  "difficulty": "hard", "topic": "ds"},
            headers=admin["headers"],
        )
    ).json()["data"]
    assert second["question_ids"] == []
    assert second["skipped_duplicates"] == 2


async def test_ai_generate_rejects_bad_difficulty(client, admin):
    response = await client.post(
        "/api/v1/questions/ai-generate",
        json={"prompt": "anything", "qtype": "mcq", "difficulty": "insane"},
        headers=admin["headers"],
    )
    assert response.status_code == 422