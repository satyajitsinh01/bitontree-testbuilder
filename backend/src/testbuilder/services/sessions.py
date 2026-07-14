"""Exam session lifecycle: one-active-session enforcement, seeded per-candidate
question selection (research R11), server-authoritative timers with lazy expiry
enforcement on every exam call (research R3)."""

import random
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Answer,
    AnswerCheckpoint,
    Assessment,
    AssessmentVersion,
    ExamSession,
    QuestionVersion,
    Section,
    SectionPoolRule,
    SectionQuestion,
    SessionQuestion,
    SessionSection,
    TestAssignment,
)
from ..models.base import now_utc
from .versioning import freeze_version


def window_state(assignment: TestAssignment, now: datetime | None = None) -> str:
    now = now or now_utc()
    if now < assignment.window_start_at:
        return "not_started"
    if now >= assignment.window_end_at:
        return "expired"
    return "open"


async def get_active_session(
    db: AsyncSession, assignment_id: str
) -> ExamSession | None:
    return (
        await db.execute(
            select(ExamSession).where(
                ExamSession.assignment_id == assignment_id,
                ExamSession.status == "active",
            )
        )
    ).scalar_one_or_none()


async def _build_session_questions(
    db: AsyncSession, session: ExamSession, section: Section, rng: random.Random
) -> None:
    picks = (
        (
            await db.execute(
                select(SectionQuestion).where(SectionQuestion.section_id == section.id)
            )
        )
        .scalars()
        .all()
    )
    rules = (
        (
            await db.execute(
                select(SectionPoolRule).where(SectionPoolRule.section_id == section.id)
            )
        )
        .scalars()
        .all()
    )
    chosen: list[SectionQuestion] = [p for p in picks if p.pool_group is None]
    for rule in rules:
        pool = [p for p in picks if p.pool_group == rule.pool_group]
        rng.shuffle(pool)
        chosen.extend(pool[: rule.select_count])
    rng.shuffle(chosen)  # randomized question order per candidate (FR-052)
    for index, pick in enumerate(chosen):
        version = (
            await db.execute(
                select(QuestionVersion).where(
                    QuestionVersion.id == pick.question_version_id
                )
            )
        ).scalar_one()
        option_order = None
        if version.qtype == "mcq":
            option_ids = [o["id"] for o in version.config.get("options", [])]
            rng.shuffle(option_ids)
            option_order = option_ids
        db.add(
            SessionQuestion(
                session_id=session.id,
                section_id=section.id,
                question_version_id=version.id,
                order_index=index,
                option_order=option_order,
                points=pick.points,
            )
        )


async def start_session(
    db: AsyncSession,
    assignment: TestAssignment,
    *,
    created_by_admin: str | None = None,
) -> ExamSession:
    if await get_active_session(db, assignment.id) is not None:
        raise HTTPException(409, "session_active")
    assessment = (
        await db.execute(
            select(Assessment).where(Assessment.id == assignment.assessment_id)
        )
    ).scalar_one()
    if assessment.status != "published" or not assessment.current_version_id:
        raise HTTPException(409, "assessment_not_published")
    version = (
        await db.execute(
            select(AssessmentVersion).where(
                AssessmentVersion.id == assessment.current_version_id
            )
        )
    ).scalar_one()
    await freeze_version(db, version)  # FR-034
    sections = (
        (
            await db.execute(
                select(Section)
                .where(Section.assessment_version_id == version.id)
                .order_by(Section.order_index)
            )
        )
        .scalars()
        .all()
    )
    total_minutes = sum(s.duration_min for s in sections)
    now = now_utc()
    session = ExamSession(
        assignment_id=assignment.id,
        assessment_version_id=version.id,
        ends_at=min(assignment.window_end_at, now + timedelta(minutes=total_minutes)),
        created_by_admin=created_by_admin,
    )
    db.add(session)
    await db.flush()
    rng = random.Random(session.id)  # seeded, reproducible (research R11)
    for index, section in enumerate(sections):
        session_section = SessionSection(
            session_id=session.id, section_id=section.id, order_index=index
        )
        if index == 0:
            session_section.status = "active"
            session_section.started_at = now
            session_section.deadline_at = min(
                now + timedelta(minutes=section.duration_min), session.ends_at
            )
            session.current_section_id = section.id
        db.add(session_section)
        await _build_session_questions(db, session, section, rng)
    assignment.status = "in_progress"
    return session


async def _advance_section(
    db: AsyncSession, session: ExamSession, current: SessionSection, auto: bool
) -> None:
    now = now_utc()
    current.status = "auto_submitted" if auto else "submitted"
    if current.started_at:
        current.time_spent_sec = int((now - current.started_at).total_seconds())
    next_section = (
        await db.execute(
            select(SessionSection)
            .where(
                SessionSection.session_id == session.id,
                SessionSection.order_index == current.order_index + 1,
            )
        )
    ).scalar_one_or_none()
    if next_section is None:
        await finalize_session(db, session, auto=auto)
        return
    section = (
        await db.execute(select(Section).where(Section.id == next_section.section_id))
    ).scalar_one()
    next_section.status = "active"
    next_section.started_at = now
    next_section.deadline_at = min(
        now + timedelta(minutes=section.duration_min), session.ends_at
    )
    session.current_section_id = section.id


async def finalize_session(db: AsyncSession, session: ExamSession, *, auto: bool) -> None:
    session.status = "auto_submitted" if auto else "submitted"
    session.submitted_at = now_utc()
    open_sections = (
        (
            await db.execute(
                select(SessionSection).where(
                    SessionSection.session_id == session.id,
                    SessionSection.status.in_(("active", "locked")),
                )
            )
        )
        .scalars()
        .all()
    )
    for section in open_sections:
        section.status = "auto_submitted" if auto else "submitted"
    assignment = (
        await db.execute(
            select(TestAssignment).where(TestAssignment.id == session.assignment_id)
        )
    ).scalar_one()
    assignment.status = "completed"
    from .scoring import evaluate_session  # local import to avoid cycle

    await evaluate_session(db, session)


async def enforce_deadlines(db: AsyncSession, session: ExamSession) -> ExamSession:
    """Lazy timer enforcement (research R3): auto-submit overdue sections/sessions
    before serving any exam request (FR-036/037)."""
    if session.status != "active":
        return session
    now = now_utc()
    if now >= session.ends_at:
        await finalize_session(db, session, auto=True)
        return session
    current = (
        await db.execute(
            select(SessionSection).where(
                SessionSection.session_id == session.id,
                SessionSection.status == "active",
            )
        )
    ).scalar_one_or_none()
    while current is not None and current.deadline_at and now >= current.deadline_at:
        await _advance_section(db, session, current, auto=True)
        if session.status != "active":
            break
        current = (
            await db.execute(
                select(SessionSection).where(
                    SessionSection.session_id == session.id,
                    SessionSection.status == "active",
                )
            )
        ).scalar_one_or_none()
    return session


SESSION_HEARTBEAT_GRACE_SEC = 60


def is_session_live(session: ExamSession, now: datetime | None = None) -> bool:
    """A session counts as owned by a connected device while its heartbeat is
    fresh; after the grace period the same credentials may resume it (R2)."""
    now = now or now_utc()
    return (now - session.last_seen_at).total_seconds() < SESSION_HEARTBEAT_GRACE_SEC


async def require_active_session(db: AsyncSession, assignment: TestAssignment) -> ExamSession:
    session = await get_active_session(db, assignment.id)
    if session is None:
        raise HTTPException(409, "no_active_session")
    session = await enforce_deadlines(db, session)
    if session.status != "active":
        await db.commit()
        raise HTTPException(409, "session_ended")
    session.last_seen_at = now_utc()
    return session


async def checkpoint_answer(
    db: AsyncSession,
    session: ExamSession,
    session_question: SessionQuestion,
    payload: dict,
    kind: str,
    code_submission_id: str | None = None,
) -> Answer:
    """Answer-of-record checkpoints (FR-035): latest checkpoint wins."""
    answer = (
        await db.execute(
            select(Answer).where(
                Answer.session_id == session.id,
                Answer.session_question_id == session_question.id,
            )
        )
    ).scalar_one_or_none()
    if answer is None:
        answer = Answer(
            session_id=session.id,
            session_question_id=session_question.id,
            payload=payload,
        )
        db.add(answer)
        await db.flush()
    else:
        answer.payload = payload
    db.add(
        AnswerCheckpoint(
            answer_id=answer.id,
            kind=kind,
            payload=payload,
            code_submission_id=code_submission_id,
        )
    )
    if session_question.state in ("unseen", "seen") and payload:
        session_question.state = "answered"
    return answer
