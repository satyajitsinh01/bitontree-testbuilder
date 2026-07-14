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
from ...services import ratelimit
from ...services.scoring import score_code_cases
from ...services.sessions import checkpoint_answer, require_active_session
from ..deps import CandidateContext, get_candidate

router = APIRouter(prefix="/exam", tags=["code"])


class CodeIn(BaseModel):
    language: str
    source_code: str


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


async def _execute(
    db: AsyncSession,
    sq: SessionQuestion,
    version: QuestionVersion,
    body: CodeIn,
    kind: str,
    visible_only: bool,
) -> CodeSubmission:
    cases = version.config.get("test_cases", [])
    if visible_only:
        cases = [c for c in cases if not c.get("is_hidden")]
    submission = CodeSubmission(
        session_question_id=sq.id,
        kind=kind,
        language=body.language,
        source_code=body.source_code,
        status="running",
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


def _results_out(submission: CodeSubmission, version: QuestionVersion) -> list[dict]:
    """Respect show_case_results config; hidden case outputs are masked."""
    mode = version.config.get("show_case_results", "visible_only")
    out = []
    for result in submission.results:
        entry = dict(result)
        if entry.get("hidden"):
            if mode == "count_only":
                continue
            entry["stdout"] = ""
            entry["stderr"] = ""
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
    return {
        "data": {
            "submission_id": submission.id,
            "status": submission.status,
            "results": _results_out(submission, version),
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
