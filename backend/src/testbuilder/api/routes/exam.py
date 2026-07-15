from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import (
    Answer,
    Assessment,
    QuestionVersion,
    Section,
    SessionQuestion,
    SessionSection,
)
from ...models.base import now_utc
from ...services.sessions import (
    _advance_section,
    checkpoint_answer,
    enforce_deadlines,
    finalize_session,
    get_active_session,
    require_active_session,
    start_session,
    window_state,
)
from ..deps import CandidateContext, get_candidate, get_candidate_for_state

router = APIRouter(prefix="/exam", tags=["exam"])


@router.get("/summary")
async def exam_summary(
    ctx: CandidateContext = Depends(get_candidate), db: AsyncSession = Depends(get_db)
):
    assessment = (
        await db.execute(
            select(Assessment).where(Assessment.id == ctx.assignment.assessment_id)
        )
    ).scalar_one()
    return {
        "data": {
            "assessment_title": assessment.title,
            "window_start_at": ctx.assignment.window_start_at.isoformat(),
            "window_end_at": ctx.assignment.window_end_at.isoformat(),
            "server_now": now_utc().isoformat(),
            "status": ctx.assignment.status,
            "rules": [
                "Full-screen mode is required for the entire exam.",
                "You must share your entire screen; a screenshot of your screen is "
                "captured whenever a violation occurs.",
                "Camera and microphone must stay enabled; periodic snapshots are taken.",
                "Switching to any other app, tab or window is recorded as a red flag.",
                "Developer tools, right-click, copy/paste and screenshots are disabled; "
                "any attempt is recorded as a red flag.",
                "The browser window must stay at its starting size; shrinking it is "
                "recorded as a red flag.",
                "Each section is timed and auto-submits on expiry; the final section ends "
                "with Submit and End Test.",
            ],
            "system_requirements": [
                "Latest Chrome or Edge",
                "Webcam and microphone",
                "Stable internet connection",
            ],
        },
        "error": None,
    }


class DeviceCheckIn(BaseModel):
    camera: bool
    microphone: bool
    network_mbps: float = 0
    browser: str = ""
    fullscreen: bool = False


@router.post("/device-check")
async def device_check(
    body: DeviceCheckIn,
    ctx: CandidateContext = Depends(get_candidate),
):
    checks = {
        "camera": body.camera,
        "microphone": body.microphone,
        "network": body.network_mbps >= 0.5,
        "browser": True,  # UA sniffing is unreliable; FE gates on API availability
        "fullscreen": body.fullscreen,
    }
    return {"data": {"checks": checks, "all_passed": all(checks.values())}, "error": None}


class StartIn(BaseModel):
    acknowledged_rules: bool = False


@router.post("/start")
async def exam_start(
    body: StartIn,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    if not body.acknowledged_rules:
        raise HTTPException(422, "rules_must_be_acknowledged")
    state = window_state(ctx.assignment)
    if state == "not_started":
        raise HTTPException(403, {"code": "window_not_started",
                                  "message": "Your test will start soon."})
    if state == "expired":
        raise HTTPException(403, {"code": "window_expired",
                                  "message": "Assessment window has expired."})
    if ctx.assignment.status == "completed":
        raise HTTPException(409, "already_completed")
    await start_session(db, ctx.assignment)
    await db.commit()
    return await exam_state(ctx, db)  # full initial state


async def _session_questions_out(
    db: AsyncSession, session_id: str, section_id: str, include_all_sections: bool = False
) -> list[dict]:
    q = select(SessionQuestion).where(SessionQuestion.session_id == session_id)
    if not include_all_sections:
        q = q.where(SessionQuestion.section_id == section_id)
    session_questions = (
        (await db.execute(q.order_by(SessionQuestion.order_index))).scalars().all()
    )
    out = []
    for sq in session_questions:
        version = (
            await db.execute(
                select(QuestionVersion).where(QuestionVersion.id == sq.question_version_id)
            )
        ).scalar_one()
        answer = (
            await db.execute(
                select(Answer).where(
                    Answer.session_id == session_id,
                    Answer.session_question_id == sq.id,
                )
            )
        ).scalar_one_or_none()
        config = dict(version.config or {})
        # Candidate payloads never leak scoring data (FT-M6-06)
        config.pop("correct_option_ids", None)
        config.pop("reference_solution", None)
        config.pop("rubric", None)
        config.pop("expected_answer", None)
        if version.qtype == "mcq" and sq.option_order:
            by_id = {o["id"]: o for o in config.get("options", [])}
            config["options"] = [by_id[i] for i in sq.option_order if i in by_id]
        if version.qtype == "coding":
            all_cases = config.get("test_cases", [])
            # sample cases are visible (with args + expected); hidden cases are
            # removed entirely and only their count is exposed
            config["test_cases"] = [c for c in all_cases if not c.get("is_hidden")]
            config["hidden_case_count"] = sum(1 for c in all_cases if c.get("is_hidden"))
        out.append(
            {
                "session_question_id": sq.id,
                "section_id": sq.section_id,
                "order_index": sq.order_index,
                "qtype": version.qtype,
                "answer_type": version.answer_type,
                "difficulty": version.difficulty,
                "tags": version.tags,
                "title": version.title,
                "body": version.body,
                "config": config,
                "points": sq.points,
                "state": sq.state,
                "saved_answer": answer.payload if answer else None,
            }
        )
    return out


@router.get("/state")
async def exam_state(
    ctx: CandidateContext = Depends(get_candidate_for_state), db: AsyncSession = Depends(get_db)
):
    from ...models import ExamSession

    session = await get_active_session(db, ctx.assignment.id)
    if session is None:
        # fall back to the most recent session so the success page can render
        session = (
            await db.execute(
                select(ExamSession)
                .where(ExamSession.assignment_id == ctx.assignment.id)
                .order_by(ExamSession.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if session is None:
            raise HTTPException(409, "no_active_session")
    if session.status == "active":
        session = await enforce_deadlines(db, session)
        session.last_seen_at = now_utc()
    sections = (
        (
            await db.execute(
                select(SessionSection, Section)
                .join(Section, Section.id == SessionSection.section_id)
                .where(SessionSection.session_id == session.id)
                .order_by(SessionSection.order_index)
            )
        )
        .all()
    )
    current_questions = []
    if session.status == "active" and session.current_section_id:
        current_questions = await _session_questions_out(
            db, session.id, session.current_section_id
        )
    await db.commit()
    return {
        "data": {
            "session_id": session.id,
            "status": session.status,
            "server_now": now_utc().isoformat(),
            "ends_at": session.ends_at.isoformat(),
            "current_section_id": session.current_section_id,
            "sections": [
                {
                    "section_id": section.id,
                    "name": section.name,
                    "order_index": ss.order_index,
                    "status": ss.status,
                    "duration_min": section.duration_min,
                    "deadline_at": ss.deadline_at.isoformat() if ss.deadline_at else None,
                    "is_final": section.is_final,
                }
                for ss, section in sections
            ],
            "questions": current_questions,
        },
        "error": None,
    }


async def _get_session_question(
    db: AsyncSession, session_id: str, session_question_id: str
) -> SessionQuestion:
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
    return sq


async def _require_section_active(
    db: AsyncSession, session_id: str, section_id: str
) -> SessionSection:
    ss = (
        await db.execute(
            select(SessionSection).where(
                SessionSection.session_id == session_id,
                SessionSection.section_id == section_id,
            )
        )
    ).scalar_one_or_none()
    if ss is None or ss.status != "active":
        raise HTTPException(409, "section_not_active")
    return ss


class AnswerIn(BaseModel):
    payload: dict


@router.put("/questions/{session_question_id}/answer")
async def save_answer(
    session_question_id: str,
    body: AnswerIn,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    session = await require_active_session(db, ctx.assignment)
    sq = await _get_session_question(db, session.id, session_question_id)
    await _require_section_active(db, session.id, sq.section_id)
    await checkpoint_answer(db, session, sq, body.payload, "autosave")
    await db.commit()
    return {"data": {"saved_at": now_utc().isoformat()}, "error": None}


class CheckpointIn(BaseModel):
    kind: str = "next_question"
    payload: dict = {}


@router.post("/questions/{session_question_id}/checkpoint")
async def checkpoint(
    session_question_id: str,
    body: CheckpointIn,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    if body.kind not in ("next_question",):
        raise HTTPException(422, "invalid_checkpoint_kind")
    session = await require_active_session(db, ctx.assignment)
    sq = await _get_session_question(db, session.id, session_question_id)
    await _require_section_active(db, session.id, sq.section_id)
    await checkpoint_answer(db, session, sq, body.payload, body.kind)
    await db.commit()
    return {"data": {"saved_at": now_utc().isoformat()}, "error": None}


@router.post("/questions/{session_question_id}/mark-review")
async def mark_review(
    session_question_id: str,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    session = await require_active_session(db, ctx.assignment)
    sq = await _get_session_question(db, session.id, session_question_id)
    sq.state = "marked_review" if sq.state != "marked_review" else "seen"
    await db.commit()
    return {"data": {"state": sq.state}, "error": None}


@router.post("/sections/{section_id}/submit")
async def submit_section(
    section_id: str,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    session = await require_active_session(db, ctx.assignment)
    ss = await _require_section_active(db, session.id, section_id)
    await _advance_section(db, session, ss, auto=False)
    await db.commit()
    return {
        "data": {
            "session_status": session.status,
            "current_section_id": session.current_section_id,
        },
        "error": None,
    }


class SubmitIn(BaseModel):
    confirm: bool = False


@router.post("/submit")
async def submit_exam(
    body: SubmitIn,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    if not body.confirm:
        raise HTTPException(422, "confirmation_required")
    session = await require_active_session(db, ctx.assignment)
    await finalize_session(db, session, auto=False)
    await db.commit()
    return {
        "data": {
            "submitted": True,
            "submitted_at": session.submitted_at.isoformat(),
            "message": "Your assessment has been submitted successfully.",
        },
        "error": None,
    }
