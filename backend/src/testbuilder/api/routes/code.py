import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...db import get_db
from ...judge.client import get_runner
from ...models import CodeSubmission, QuestionVersion, SessionQuestion
from ...models.coding import SUPPORTED_LANGUAGES
from ...services import harness, ratelimit
from ...services.scoring import score_code_cases
from ...services.sessions import checkpoint_answer, require_active_session
from ..deps import CandidateContext, get_candidate

router = APIRouter(prefix="/exam", tags=["code"])


class CodeIn(BaseModel):
    language: str
    source_code: str
    custom_input: str | None = None  # LeetCode-style custom testcase (Run only)


async def _get_coding_question(
    db: AsyncSession, session_id: str, session_question_id: str
) -> tuple[SessionQuestion, QuestionVersion]:
    sq = (
        await db.execute(
            select(SessionQuestion).where(
                SessionQuestion.id == session_question_id,
                SessionQuestion.session_id == session_id,
            )
        )
    ).scalar_one_or_none()
    if sq is None:
        raise HTTPException(404, "not_found")
    version = (
        await db.execute(
            select(QuestionVersion).where(QuestionVersion.id == sq.question_version_id)
        )
    ).scalar_one()
    if version.qtype != "coding":
        raise HTTPException(422, "not_a_coding_question")
    return sq, version


def _validate_language(language: str, version: QuestionVersion) -> None:
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(422, {"code": "unsupported_language",
                                  "details": [f"supported: {SUPPORTED_LANGUAGES}"]})
    allowed = version.config.get("allowed_languages") or list(SUPPORTED_LANGUAGES)
    if language not in allowed:
        raise HTTPException(422, {"code": "language_not_allowed",
                                  "details": [f"allowed: {allowed}"]})


def _worst_status(results: list) -> str:
    order = ("compile_error", "runtime_error", "timeout", "failed")
    for status in order:
        if any(r.status == status for r in results):
            return status
    return "completed"


def _canon(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


async def _execute_harness(
    db: AsyncSession,
    sq: SessionQuestion,
    version: QuestionVersion,
    body: CodeIn,
    kind: str,
    visible_only: bool,
) -> CodeSubmission:
    """LeetCode-style execution: wrap the candidate function with a driver, feed
    typed args as stdin, and compare outputs structurally in the backend."""
    config = version.config
    signature = config["signature"]
    n_params = len(signature["params"])
    time_ms = int(config.get("time_limit_ms", 5000))
    mem_kb = int(config.get("memory_limit_kb", 256000))
    all_cases = config.get("test_cases", [])
    exec_cases = [c for c in all_cases if not (visible_only and c.get("is_hidden"))]

    submission = CodeSubmission(
        session_question_id=sq.id, kind=kind, language=body.language,
        source_code=body.source_code, status="running",
    )
    db.add(submission)
    await db.flush()

    try:
        source = harness.build_program(signature, body.language, body.source_code)
    except ValueError as exc:
        raise HTTPException(422, {"code": "unsupported_language", "details": [str(exc)]}) \
            from None

    meta: dict[str, dict] = {}
    runner_cases: list[dict] = []
    for case in exec_cases:
        cid = case["id"]
        runner_cases.append({
            "id": cid,
            "input": harness.stdin_for_args(case.get("args", [])),
            "time_limit_ms": time_ms,
            "memory_limit_kb": mem_kb,
        })
        meta[cid] = {
            "expected": case.get("expected"),
            "hidden": bool(case.get("is_hidden")),
            "args": case.get("args", []),
            "custom": False,
        }
    # a candidate custom testcase runs only on Run and is never scored
    if kind == "run" and body.custom_input:
        args = harness.parse_custom_input(body.custom_input, n_params)
        if args is None:
            raise HTTPException(422, {
                "code": "invalid_custom_input",
                "details": [f"provide {n_params} JSON value(s), one per line"],
            })
        runner_cases.append({
            "id": "custom", "input": harness.stdin_for_args(args),
            "time_limit_ms": time_ms, "memory_limit_kb": mem_kb,
        })
        meta["custom"] = {"expected": None, "hidden": False, "args": args, "custom": True}

    results = await get_runner().run_cases(body.language, source, runner_cases)
    stored: list[dict] = []
    for r in results:
        m = meta.get(r.case_id, {})
        if m.get("custom"):
            passed = None  # custom run has no expected output
        elif r.status == "completed":
            passed = harness.outputs_equal(r.stdout, m.get("expected"))
        else:
            passed = False
        stored.append({
            "case_id": r.case_id,
            "passed": bool(passed),
            "custom": m.get("custom", False),
            "status": r.status,
            "stdout": r.stdout,
            "stderr": r.stderr,
            "time_ms": r.time_ms,
            "memory_kb": r.memory_kb,
            "hidden": m.get("hidden", False),
            "expected_display": _canon(m.get("expected")) if not m.get("custom") else None,
            "input_display": harness.stdin_for_args(m.get("args", [])),
        })
    submission.results = stored
    submission.status = _worst_status(results)
    submission.exec_time_ms = max((r.time_ms for r in results), default=0)
    submission.memory_kb = max((r.memory_kb for r in results), default=0)
    if kind == "submit":
        scorable = [s for s in stored if not s["custom"]]
        submission.score = score_code_cases(all_cases, scorable, sq.points)
    return submission


async def _execute_raw(
    db: AsyncSession, sq: SessionQuestion, version: QuestionVersion,
    body: CodeIn, kind: str, visible_only: bool,
) -> CodeSubmission:
    """Legacy stdin/stdout mode for questions without a signature."""
    cases = version.config.get("test_cases", [])
    if visible_only:
        cases = [c for c in cases if not c.get("is_hidden")]
    submission = CodeSubmission(
        session_question_id=sq.id, kind=kind, language=body.language,
        source_code=body.source_code, status="running",
    )
    db.add(submission)
    await db.flush()
    results = await get_runner().run_cases(body.language, body.source_code, cases)
    submission.results = [
        {**asdict(r), "hidden": bool(next(
            (c.get("is_hidden") for c in cases if c["id"] == r.case_id), False
        ))}
        for r in results
    ]
    submission.status = _worst_status(results)
    submission.exec_time_ms = max((r.time_ms for r in results), default=0)
    submission.memory_kb = max((r.memory_kb for r in results), default=0)
    if kind == "submit":
        submission.score = score_code_cases(
            version.config.get("test_cases", []), submission.results, sq.points
        )
    return submission


async def _execute(db, sq, version, body, kind, visible_only) -> CodeSubmission:
    if version.config.get("signature"):
        return await _execute_harness(db, sq, version, body, kind, visible_only)
    return await _execute_raw(db, sq, version, body, kind, visible_only)


def _results_out(submission: CodeSubmission, version: QuestionVersion) -> list[dict]:
    """Mask hidden cases: their input, expected and output are never revealed —
    only the pass/fail verdict and status."""
    mode = version.config.get("show_case_results", "visible_only")
    out = []
    for result in submission.results:
        entry = dict(result)
        if entry.get("hidden"):
            if mode == "count_only":
                continue
            entry["stdout"] = ""
            entry["stderr"] = ""
            entry["expected_display"] = None
            entry["input_display"] = None
        out.append(entry)
    return out


@router.post("/questions/{session_question_id}/code/run", status_code=202)
async def run_code(
    session_question_id: str,
    body: CodeIn,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    session = await require_active_session(db, ctx.assignment)
    sq, version = await _get_coding_question(db, session.id, session_question_id)
    _validate_language(body.language, version)
    if not ratelimit.allow(f"run:{ctx.assignment.id}", settings.run_rate_limit_per_min):
        raise HTTPException(429, "rate_limited")
    submission = await _execute(db, sq, version, body, "run", visible_only=True)
    await checkpoint_answer(
        db, session, sq,
        {"language": body.language, "code": body.source_code},
        "run_code", code_submission_id=submission.id,
    )
    await db.commit()
    results = _results_out(submission, version)
    return {
        "data": {
            "submission_id": submission.id,
            "status": submission.status,
            "results": results,
            "passed_count": sum(1 for r in results if not r.get("custom") and r.get("passed")),
            "total_count": sum(1 for r in results if not r.get("custom")),
            "exec_time_ms": submission.exec_time_ms,
            "memory_kb": submission.memory_kb,
        },
        "error": None,
    }


@router.post("/questions/{session_question_id}/code/submit", status_code=202)
async def submit_code(
    session_question_id: str,
    body: CodeIn,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    session = await require_active_session(db, ctx.assignment)
    sq, version = await _get_coding_question(db, session.id, session_question_id)
    _validate_language(body.language, version)
    if not ratelimit.allow(
        f"submit:{sq.id}", settings.submit_limit_per_question, window_sec=24 * 3600
    ):
        raise HTTPException(429, "rate_limited")
    body.custom_input = None  # submit never uses custom input
    submission = await _execute(db, sq, version, body, "submit", visible_only=False)
    await checkpoint_answer(
        db, session, sq,
        {"language": body.language, "code": body.source_code},
        "submit_code", code_submission_id=submission.id,
    )
    await db.commit()
    passed = sum(1 for r in submission.results if r.get("passed"))
    return {
        "data": {
            "submission_id": submission.id,
            "status": submission.status,
            "results": _results_out(submission, version),
            "passed_count": passed,
            "total_count": len(submission.results),
            "score": submission.score,
            "exec_time_ms": submission.exec_time_ms,
        },
        "error": None,
    }


@router.get("/code-submissions/{submission_id}")
async def get_submission(
    submission_id: str,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    session = await require_active_session(db, ctx.assignment)
    submission = (
        await db.execute(
            select(CodeSubmission)
            .join(SessionQuestion, SessionQuestion.id == CodeSubmission.session_question_id)
            .where(
                CodeSubmission.id == submission_id,
                SessionQuestion.session_id == session.id,
            )
        )
    ).scalar_one_or_none()
    if submission is None:
        raise HTTPException(404, "not_found")
    version = (
        await db.execute(
            select(QuestionVersion)
            .join(SessionQuestion, SessionQuestion.question_version_id == QuestionVersion.id)
            .where(SessionQuestion.id == submission.session_question_id)
        )
    ).scalar_one()
    await db.commit()
    return {
        "data": {
            "submission_id": submission.id,
            "status": submission.status,
            "results": _results_out(submission, version),
            "score": submission.score,
        },
        "error": None,
    }
