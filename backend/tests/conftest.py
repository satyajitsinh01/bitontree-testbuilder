import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio

os.environ.setdefault("TB_JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
os.environ.setdefault("TB_ACCESS_TOKEN_MINUTES", "120")  # survives time-travel tests
os.environ.setdefault("TB_GEMINI_API_KEY", "")  # force AI stub
os.environ.setdefault("TB_RESEND_API_KEY", "")  # force console email transport
os.environ.setdefault("TB_JUDGE0_URL", "")


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class FakeRunner:
    """Deterministic code runner: source containing 'CORRECT' passes every case,
    'SYNTAX_ERROR' compile-errors, anything else fails all cases (wrong answer)."""

    async def run_cases(self, language, source, cases):
        from testbuilder.judge.client import CaseResult

        results = []
        for case in cases:
            if "SYNTAX_ERROR" in source:
                results.append(
                    CaseResult(case["id"], False, "compile_error", "", "SyntaxError", 1, 100)
                )
            elif "CORRECT" in source:
                results.append(
                    CaseResult(
                        case["id"], True, "completed",
                        str(case.get("expected_output", "")), "", 12, 2048,
                    )
                )
            else:
                results.append(
                    CaseResult(case["id"], False, "completed", "wrong", "", 10, 1024)
                )
        return results


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TB_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("TB_LOCAL_STORAGE_DIR", str(tmp_path / "storage"))
    from testbuilder import db as db_module

    db_module.reset_engine_for_tests()
    from testbuilder.db import create_all
    from testbuilder.judge.client import set_runner_for_tests
    from testbuilder.main import create_app
    from testbuilder.services import ratelimit

    await create_all()
    ratelimit.reset_for_tests()
    set_runner_for_tests(FakeRunner())
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    set_runner_for_tests(None)
    db_module.reset_engine_for_tests()


async def _create_admin(email: str, roles: list[str], org_slug: str = "acme") -> dict:
    from sqlalchemy import select

    from testbuilder.db import session_factory
    from testbuilder.models import Organization, User, UserRole
    from testbuilder.security import hash_password

    async with session_factory()() as session:
        org = (
            await session.execute(
                select(Organization).where(Organization.slug == org_slug)
            )
        ).scalar_one_or_none()
        if org is None:
            org = Organization(name=org_slug.title(), slug=org_slug)
            session.add(org)
            await session.flush()
        user = User(
            org_id=org.id,
            email=email,
            password_hash=hash_password("Passw0rd!123"),
            full_name="Test Admin",
        )
        session.add(user)
        await session.flush()
        for role in roles:
            session.add(UserRole(user_id=user.id, role=role))
        await session.commit()
        return {"org_id": org.id, "user_id": user.id, "email": email}


async def _login(client: httpx.AsyncClient, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/admin/login", json={"email": email, "password": "Passw0rd!123"}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest_asyncio.fixture
async def admin(client):
    """Admin with all three roles."""
    info = await _create_admin("admin@example.com", ["hr_admin", "test_creator", "evaluator"])
    headers = await _login(client, info["email"])
    return {**info, "headers": headers}


@pytest_asyncio.fixture
async def evaluator_only(client):
    info = await _create_admin("eval@example.com", ["evaluator"])
    headers = await _login(client, info["email"])
    return {**info, "headers": headers}


MCQ_CONFIG = {
    "options": [
        {"id": "a", "text": "Correct"},
        {"id": "b", "text": "Wrong 1"},
        {"id": "c", "text": "Wrong 2"},
        {"id": "d", "text": "Wrong 3"},
    ],
    "correct_option_ids": ["a"],
}
CODING_CONFIG = {
    "allowed_languages": ["python", "javascript"],
    "starter_code": {"python": "def solve():\n    pass\n"},
    "show_case_results": "visible_only",
    "test_cases": [
        {"id": "t1", "input": "1", "expected_output": "1", "is_hidden": False, "weight": 1},
        {"id": "t2", "input": "2", "expected_output": "2", "is_hidden": True, "weight": 2},
        {"id": "t3", "input": "3", "expected_output": "3", "is_hidden": True, "weight": 2},
    ],
}
TEXT_CONFIG = {"rubric": "Explain REST API design principles clearly",
               "expected_answer": "REST uses HTTP verbs resources statelessness"}


async def create_question(client, headers, qtype="mcq", title="What is 2+2?", **overrides):
    config = {"mcq": MCQ_CONFIG, "coding": CODING_CONFIG, "text": TEXT_CONFIG}[qtype]
    answer_type = {"mcq": "single_choice", "coding": "code", "text": "long_text"}[qtype]
    payload = {
        "qtype": qtype,
        "title": title,
        "body": f"Body of {title}",
        "answer_type": answer_type,
        "config": config,
        "topic": "general",
        **overrides,
    }
    response = await client.post("/api/v1/questions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def build_published_assessment(
    client, admin, *, with_coding=True, with_text=True, section_minutes=(10, 10)
) -> dict:
    """Two-section assessment: MCQ section (3 questions, pool 2-of-3) and a final
    section with text + optional coding."""
    response = await client.post(
        "/api/v1/assessments",
        json={"title": "Backend Screening", "description": "spec test"},
        headers=admin["headers"],
    )
    assert response.status_code == 201, response.text
    assessment = response.json()["data"]

    mcq_ids = []
    for i in range(3):
        q = await create_question(client, admin["headers"], "mcq", f"MCQ number {i} unique")
        mcq_ids.append(q["id"])
    section1 = (
        await client.post(
            f"/api/v1/assessments/{assessment['id']}/sections",
            json={
                "name": "Aptitude",
                "duration_min": section_minutes[0],
                "weightage_pct": 40,
                "question_count": 2,
            },
            headers=admin["headers"],
        )
    ).json()["data"]
    await client.put(
        f"/api/v1/sections/{section1['id']}/questions",
        json={"items": [{"question_id": qid, "pool_group": "p1"} for qid in mcq_ids]},
        headers=admin["headers"],
    )
    await client.put(
        f"/api/v1/sections/{section1['id']}/pool-rules",
        json={"items": [{"pool_group": "p1", "select_count": 2}]},
        headers=admin["headers"],
    )

    final_items = []
    if with_text:
        text_q = await create_question(client, admin["headers"], "text", "Explain REST design")
        final_items.append({"question_id": text_q["id"], "points": 5})
    if with_coding:
        code_q = await create_question(client, admin["headers"], "coding", "Echo the input")
        final_items.append({"question_id": code_q["id"], "points": 10})
    section2 = (
        await client.post(
            f"/api/v1/assessments/{assessment['id']}/sections",
            json={
                "name": "Deep Dive",
                "duration_min": section_minutes[1],
                "weightage_pct": 60,
                "question_count": len(final_items),
                "is_final": True,
            },
            headers=admin["headers"],
        )
    ).json()["data"]
    await client.put(
        f"/api/v1/sections/{section2['id']}/questions",
        json={"items": final_items},
        headers=admin["headers"],
    )
    response = await client.post(
        f"/api/v1/assessments/{assessment['id']}/publish", headers=admin["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def add_candidate(
    client, admin, assessment_id, email="jane@example.com",
    start_delta=timedelta(minutes=-5), end_delta=timedelta(hours=2),
) -> dict:
    response = await client.post(
        f"/api/v1/assessments/{assessment_id}/assignments",
        json={
            "full_name": "Jane Doe",
            "email": email,
            "phone": "+911234567890",
            "window_start_at": (now() + start_delta).isoformat(),
            "window_end_at": (now() + end_delta).isoformat(),
            "send_email": True,
        },
        headers=admin["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def candidate_login(client, assignment: dict) -> dict:
    response = await client.post(
        "/api/v1/auth/candidate/login",
        json={"username": assignment["username"], "password": assignment["initial_password"]},
    )
    assert response.status_code == 200, response.text
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
