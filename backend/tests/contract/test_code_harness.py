"""LeetCode-style execution: signature-driven driver, Run vs Submit, custom
input, and hidden-case masking. Uses a fake runner that actually solves the
twoSum problem so the harness comparison path is exercised end to end."""

import json

import pytest_asyncio
from tests.conftest import add_candidate, candidate_login, create_question

from testbuilder.judge.client import CaseResult, set_runner_for_tests

TWO_SUM_SIGNATURE = {
    "function_name": "twoSum",
    "params": [{"name": "nums", "type": "int[]"}, {"name": "target", "type": "int"}],
    "return_type": "int[]",
}
CODING_CONFIG = {
    "signature": TWO_SUM_SIGNATURE,
    "allowed_languages": ["python", "javascript"],
    "description": "## Two Sum\nReturn indices summing to `target`.",
    "constraints": "- `2 <= n`",
    "examples": [{"input": "nums=[2,7], target=9", "output": "[0,1]", "explanation": "ok"}],
    "test_cases": [
        {"id": "s1", "args": [[2, 7, 11, 15], 9], "expected": [0, 1],
         "is_hidden": False, "weight": 1},
        {"id": "s2", "args": [[3, 2, 4], 6], "expected": [1, 2],
         "is_hidden": False, "weight": 1},
        {"id": "h1", "args": [[3, 3], 6], "expected": [0, 1], "is_hidden": True, "weight": 1},
        {"id": "h2", "args": [[0, 4, 3, 0], 0], "expected": [0, 3],
         "is_hidden": True, "weight": 1},
    ],
    "time_limit_ms": 3000,
    "memory_limit_kb": 128000,
}


class TwoSumRunner:
    """Simulates Judge0: a source containing 'CORRECT' actually solves twoSum from
    the stdin args; otherwise it returns a wrong answer."""

    async def run_cases(self, language, source, cases):
        results = []
        for case in cases:
            lines = case["input"].split("\n")
            nums = json.loads(lines[0])
            target = json.loads(lines[1])
            if "CORRECT" in source:
                out = _solve(nums, target)
                stdout = json.dumps(out, separators=(",", ":"))
            else:
                stdout = "[9,9]"
            results.append(
                CaseResult(case["id"], True, "completed", stdout, "", 5, 1024)
            )
        return results


def _solve(nums, target):
    seen = {}
    for i, v in enumerate(nums):
        if target - v in seen:
            return [seen[target - v], i]
        seen[v] = i
    return [-1, -1]


@pytest_asyncio.fixture
def two_sum_runner():
    set_runner_for_tests(TwoSumRunner())
    yield
    from tests.conftest import FakeRunner

    set_runner_for_tests(FakeRunner())


async def _published_coding_exam(client, admin):
    """Build a single-section assessment with one LeetCode coding question."""
    from datetime import timedelta

    from tests.conftest import now

    coding_q = await create_question(
        client, admin["headers"], "coding", "Two Sum harness", config=CODING_CONFIG,
    )
    window_start = now() - timedelta(seconds=1)
    assessment = (
        await client.post("/api/v1/assessments", headers=admin["headers"], json={
            "title": "Coding Screen",
            "window_start_at": window_start.isoformat(),
            "window_end_at": (window_start + timedelta(minutes=30)).isoformat(),
        })
    ).json()["data"]
    section = (
        await client.post(
            f"/api/v1/assessments/{assessment['id']}/sections", headers=admin["headers"],
            json={"name": "DSA", "duration_min": 30, "weightage_pct": 100,
                  "question_count": 1, "is_final": True},
        )
    ).json()["data"]
    await client.put(
        f"/api/v1/sections/{section['id']}/questions", headers=admin["headers"],
        json={"items": [{"question_id": coding_q["id"], "points": 10}]},
    )
    pub = await client.post(
        f"/api/v1/assessments/{assessment['id']}/publish", headers=admin["headers"]
    )
    assert pub.status_code == 200, pub.text
    return assessment


async def _start(client, admin):
    assessment = await _published_coding_exam(client, admin)
    assignment = await add_candidate(client, admin, assessment["id"], email="dsa@example.com")
    headers = await candidate_login(client, assignment)
    state = (
        await client.post("/api/v1/exam/start", json={"acknowledged_rules": True},
                          headers=headers)
    ).json()["data"]
    sq = next(q for q in state["questions"] if q["qtype"] == "coding")
    return headers, sq


async def test_coding_question_created_with_generated_starter(client, admin):
    q = await create_question(
        client, admin["headers"], "coding", "Two Sum autofill", config=CODING_CONFIG,
    )
    version = q["current_version"]
    # starter code auto-generated from the signature for both languages
    assert "class Solution" in version["config"]["starter_code"]["python"]
    assert "twoSum" in version["config"]["starter_code"]["javascript"]


async def test_exam_hides_hidden_cases_and_signature_visible(client, admin, two_sum_runner):
    headers, sq = await _start(client, admin)
    cfg = sq["config"]
    # sample cases visible, hidden removed but counted
    assert len(cfg["test_cases"]) == 2
    assert cfg["hidden_case_count"] == 2
    assert all(not c.get("is_hidden") for c in cfg["test_cases"])
    assert cfg["signature"]["function_name"] == "twoSum"
    assert "starter_code" in cfg


async def test_run_executes_sample_plus_custom_input(client, admin, two_sum_runner):
    headers, sq = await _start(client, admin)
    run = (
        await client.post(
            f"/api/v1/exam/questions/{sq['session_question_id']}/code/run",
            json={"language": "python", "source_code": "CORRECT solution",
                  "custom_input": "[1,2,3,4]\n7"},
            headers=headers,
        )
    ).json()["data"]
    # 2 sample cases scored, both pass; custom case shown separately (no verdict)
    assert run["passed_count"] == 2 and run["total_count"] == 2
    custom = [r for r in run["results"] if r.get("custom")]
    assert len(custom) == 1
    assert custom[0]["stdout"] == "[2,3]"  # indices of 3+4=7


async def test_submit_runs_all_hidden_and_masks_them(client, admin, two_sum_runner):
    headers, sq = await _start(client, admin)
    submit = (
        await client.post(
            f"/api/v1/exam/questions/{sq['session_question_id']}/code/submit",
            json={"language": "python", "source_code": "CORRECT"},
            headers=headers,
        )
    ).json()["data"]
    assert submit["passed_count"] == 4 and submit["total_count"] == 4
    assert submit["score"] == 10.0
    hidden = [r for r in submit["results"] if r["hidden"]]
    assert len(hidden) == 2
    # hidden inputs / expected / output never revealed
    for h in hidden:
        assert h["stdout"] == "" and h["expected_display"] is None
        assert h["input_display"] is None


async def test_wrong_solution_fails_cases(client, admin, two_sum_runner):
    headers, sq = await _start(client, admin)
    submit = (
        await client.post(
            f"/api/v1/exam/questions/{sq['session_question_id']}/code/submit",
            json={"language": "python", "source_code": "return nothing useful"},
            headers=headers,
        )
    ).json()["data"]
    assert submit["passed_count"] == 0
    assert submit["score"] == 0.0


async def test_invalid_custom_input_rejected(client, admin, two_sum_runner):
    headers, sq = await _start(client, admin)
    resp = await client.post(
        f"/api/v1/exam/questions/{sq['session_question_id']}/code/run",
        json={"language": "python", "source_code": "CORRECT", "custom_input": "[1,2]"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_custom_input"
