"""User Stories 2 & 4 end-to-end: exam runtime, coding, evaluation, override,
report, exports (T05A / T088)."""

from tests.conftest import add_candidate, build_published_assessment, candidate_login


async def _start_exam(client, admin):
    assessment = await build_published_assessment(client, admin)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    state = (
        await client.post(
            "/api/v1/exam/start", json={"acknowledged_rules": True}, headers=headers
        )
    ).json()["data"]
    return assessment, assignment, headers, state


async def test_full_candidate_and_evaluator_flow(client, admin):
    assessment, assignment, headers, state = await _start_exam(client, admin)

    # pool rule delivered exactly 2 of the 3 MCQs, randomized (FR-046/052)
    assert len(state["questions"]) == 2
    assert all(q["qtype"] == "mcq" for q in state["questions"])
    # no answer leakage to candidates (FT-M6-06)
    for question in state["questions"]:
        assert "correct_option_ids" not in question["config"]

    # answer first question correctly (option ids are stable under shuffling)
    q1, q2 = state["questions"]
    saved = await client.put(
        f"/api/v1/exam/questions/{q1['session_question_id']}/answer",
        json={"payload": {"selected_option_ids": ["a"]}},
        headers=headers,
    )
    assert saved.status_code == 200

    # autosave persists across a "refresh" (state reload)
    reloaded = (await client.get("/api/v1/exam/state", headers=headers)).json()["data"]
    reloaded_q1 = next(
        q for q in reloaded["questions"]
        if q["session_question_id"] == q1["session_question_id"]
    )
    assert reloaded_q1["saved_answer"] == {"selected_option_ids": ["a"]}
    assert reloaded_q1["state"] == "answered"

    # option order identical across reloads (persisted shuffle)
    assert [o["id"] for o in reloaded_q1["config"]["options"]] == [
        o["id"] for o in q1["config"]["options"]
    ]

    # mark q2 for review, then answer it wrong via next_question checkpoint
    await client.post(
        f"/api/v1/exam/questions/{q2['session_question_id']}/mark-review", headers=headers
    )
    await client.post(
        f"/api/v1/exam/questions/{q2['session_question_id']}/checkpoint",
        json={"kind": "next_question", "payload": {"selected_option_ids": ["b"]}},
        headers=headers,
    )

    # submit section 1 -> section 2 becomes active
    section1_id = state["sections"][0]["section_id"]
    advanced = (
        await client.post(f"/api/v1/exam/sections/{section1_id}/submit", headers=headers)
    ).json()["data"]
    assert advanced["current_section_id"] == state["sections"][1]["section_id"]

    # section 1 is closed: further answers rejected
    late = await client.put(
        f"/api/v1/exam/questions/{q1['session_question_id']}/answer",
        json={"payload": {"selected_option_ids": ["c"]}},
        headers=headers,
    )
    assert late.status_code == 409

    # section 2: text + coding
    state2 = (await client.get("/api/v1/exam/state", headers=headers)).json()["data"]
    text_q = next(q for q in state2["questions"] if q["qtype"] == "text")
    code_q = next(q for q in state2["questions"] if q["qtype"] == "coding")

    await client.put(
        f"/api/v1/exam/questions/{text_q['session_question_id']}/answer",
        json={"payload": {"text": "REST uses HTTP verbs and resources with statelessness"}},
        headers=headers,
    )

    # coding: visible cases only on run; hidden evaluated on submit
    run = (
        await client.post(
            f"/api/v1/exam/questions/{code_q['session_question_id']}/code/run",
            json={"language": "python", "source_code": "print('CORRECT')"},
            headers=headers,
        )
    ).json()["data"]
    assert len(run["results"]) == 1  # only the visible case (FT-M7-01)

    submit = (
        await client.post(
            f"/api/v1/exam/questions/{code_q['session_question_id']}/code/submit",
            json={"language": "python", "source_code": "print('CORRECT')"},
            headers=headers,
        )
    ).json()["data"]
    assert submit["passed_count"] == 3
    assert submit["score"] == 10.0  # all weights earned
    # hidden case stdout masked (FT-M7-02)
    hidden = [r for r in submit["results"] if r["hidden"]]
    assert hidden and all(r["stdout"] == "" for r in hidden)

    # final submit requires confirmation, then succeeds (FR-057)
    unconfirmed = await client.post("/api/v1/exam/submit", json={"confirm": False},
                                    headers=headers)
    assert unconfirmed.status_code == 422
    done = await client.post("/api/v1/exam/submit", json={"confirm": True},
                             headers=headers)
    assert done.status_code == 200
    assert done.json()["data"]["submitted"] is True

    # no re-entry after submission
    after = await client.get("/api/v1/exam/state", headers=headers)
    assert after.json()["data"]["status"] == "submitted"
    blocked = await client.put(
        f"/api/v1/exam/questions/{q1['session_question_id']}/answer",
        json={"payload": {}}, headers=headers,
    )
    assert blocked.status_code == 409

    # ---- evaluator side (Story 4) ----
    results = (
        await client.get(
            f"/api/v1/assessments/{assessment['id']}/results", headers=admin["headers"]
        )
    ).json()["data"]
    assert results["cohort_size"] == 1
    entry = results["items"][0]
    assert entry["percentile"] is None  # cohort < 20 (FR-087)
    session_id = entry["session_id"]

    report = (
        await client.get(f"/api/v1/sessions/{session_id}/report", headers=admin["headers"])
    ).json()["data"]
    assert report["overall_max"] == 100.0
    assert len(report["section_scores"]) == 2
    assert report["ai_observations"].startswith("[AI-generated]")
    mcq_section = next(s for s in report["section_scores"] if s["name"] == "Aptitude")
    assert mcq_section["attempted"] == 2
    assert mcq_section["correct"] == 1 and mcq_section["wrong"] == 1

    answers = (
        await client.get(f"/api/v1/sessions/{session_id}/answers", headers=admin["headers"])
    ).json()["data"]["items"]
    mcq_answers = [answer for answer in answers if answer["qtype"] == "mcq"]
    assert {tuple(answer["display_answer"]["selected_answers"]) for answer in mcq_answers} == {
        ("Correct",),
        ("Wrong 1",),
    }
    coding_answer = next(a for a in answers if a["qtype"] == "coding")
    assert len(coding_answer["code_history"]) == 2  # run + submit (FR-066)
    text_answer = next(a for a in answers if a["qtype"] == "text")
    assert text_answer["evaluation"]["method"] == "ai_text"
    assert text_answer["evaluation"]["ai_rationale"]

    # override the text score with a reason -> audit logged (FR-083)
    override = await client.patch(
        f"/api/v1/evaluations/{text_answer['evaluation']['id']}",
        json={"final_score": 5.0, "override_reason": "excellent real-world detail"},
        headers=admin["headers"],
    )
    assert override.status_code == 200
    logs = await client.get(
        "/api/v1/admin/audit-logs", params={"action": "score.overridden"},
        headers=admin["headers"],
    )
    assert logs.json()["data"]["total"] == 1

    # finalize locks further overrides (FT-M9-05)
    finalized = await client.post(
        f"/api/v1/sessions/{session_id}/report/finalize", headers=admin["headers"]
    )
    assert finalized.status_code == 200
    locked = await client.patch(
        f"/api/v1/evaluations/{text_answer['evaluation']['id']}",
        json={"final_score": 1.0, "override_reason": "changed my mind"},
        headers=admin["headers"],
    )
    assert locked.status_code == 409

    # CSV export (FR-086)
    export = await client.post(
        f"/api/v1/assessments/{assessment['id']}/results/export", headers=admin["headers"]
    )
    assert export.status_code == 200
    assert "jane@example.com" in export.text


async def test_override_out_of_range_rejected(client, admin):
    _, _, headers, state = await _start_exam(client, admin)
    await client.post("/api/v1/exam/submit", json={"confirm": True}, headers=headers)
    results = (
        await client.get(
            "/api/v1/assessments/{}/results".format(
                (await client.get("/api/v1/assessments", headers=admin["headers"]))
                .json()["data"]["items"][0]["id"]
            ),
            headers=admin["headers"],
        )
    ).json()["data"]
    session_id = results["items"][0]["session_id"]
    answers = (
        await client.get(f"/api/v1/sessions/{session_id}/answers", headers=admin["headers"])
    ).json()["data"]["items"]
    evaluation = answers[0]["evaluation"]
    response = await client.patch(
        f"/api/v1/evaluations/{evaluation['id']}",
        json={"final_score": 999, "override_reason": "too generous"},
        headers=admin["headers"],
    )
    assert response.status_code == 422
