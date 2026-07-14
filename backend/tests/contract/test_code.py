"""FT-M7: language validation, rate limiting, error surfacing, history."""

from tests.conftest import add_candidate, build_published_assessment, candidate_login


async def _coding_session(client, admin):
    assessment = await build_published_assessment(client, admin, with_text=False)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    state = (
        await client.post(
            "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
        )
    ).json()["data"]
    section1 = state["sections"][0]["section_id"]
    await client.post(f"/api/v1/exam/sections/{section1}/submit", headers=headers)
    state2 = (await client.get("/api/v1/exam/state", headers=headers)).json()["data"]
    code_q = next(q for q in state2["questions"] if q["qtype"] == "coding")
    return headers, code_q


async def test_language_restrictions(client, admin):
    headers, code_q = await _coding_session(client, admin)
    sqid = code_q["session_question_id"]
    unsupported = await client.post(
        f"/api/v1/exam/questions/{sqid}/code/run",
        json={"language": "ruby", "source_code": "puts 1"},
        headers=headers,
    )
    assert unsupported.status_code == 422
    not_allowed = await client.post(
        f"/api/v1/exam/questions/{sqid}/code/run",
        json={"language": "java", "source_code": "class A {}"},  # question allows py/js
        headers=headers,
    )
    assert not_allowed.status_code == 422
    assert not_allowed.json()["error"]["code"] == "language_not_allowed"


async def test_compile_error_surfaced(client, admin):
    headers, code_q = await _coding_session(client, admin)
    response = await client.post(
        f"/api/v1/exam/questions/{code_q['session_question_id']}/code/run",
        json={"language": "python", "source_code": "SYNTAX_ERROR"},
        headers=headers,
    )
    data = response.json()["data"]
    assert data["status"] == "compile_error"
    assert "SyntaxError" in data["results"][0]["stderr"]


async def test_run_rate_limit_429(client, admin):
    """FR-067: 10 runs/min then 429; the counter is per assignment."""
    headers, code_q = await _coding_session(client, admin)
    sqid = code_q["session_question_id"]
    for _ in range(10):
        ok = await client.post(
            f"/api/v1/exam/questions/{sqid}/code/run",
            json={"language": "python", "source_code": "print('CORRECT')"},
            headers=headers,
        )
        assert ok.status_code == 202
    blocked = await client.post(
        f"/api/v1/exam/questions/{sqid}/code/run",
        json={"language": "python", "source_code": "print('CORRECT')"},
        headers=headers,
    )
    assert blocked.status_code == 429


async def test_wrong_answer_partial_credit(client, admin):
    headers, code_q = await _coding_session(client, admin)
    response = await client.post(
        f"/api/v1/exam/questions/{code_q['session_question_id']}/code/submit",
        json={"language": "python", "source_code": "print('wrong')"},
        headers=headers,
    )
    data = response.json()["data"]
    assert data["passed_count"] == 0
    assert data["score"] == 0.0


async def test_submission_poll_endpoint(client, admin):
    headers, code_q = await _coding_session(client, admin)
    submitted = (
        await client.post(
            f"/api/v1/exam/questions/{code_q['session_question_id']}/code/submit",
            json={"language": "python", "source_code": "print('CORRECT')"},
            headers=headers,
        )
    ).json()["data"]
    polled = await client.get(
        f"/api/v1/exam/code-submissions/{submitted['submission_id']}", headers=headers
    )
    assert polled.status_code == 200
    assert polled.json()["data"]["status"] == "completed"
