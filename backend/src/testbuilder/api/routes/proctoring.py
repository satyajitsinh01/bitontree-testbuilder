import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import (
    Assessment,
    ExamSession,
    ProctoringEvent,
    ProctoringEvidence,
    TestAssignment,
)
from ...models.base import now_utc
from ...models.proctoring import CLIENT_EVENT_KINDS
from ...services.ai import analyze_proctoring_image
from ...services.sessions import get_active_session
from ...storage import get_object, put_base64_image
from ..deps import AdminContext, CandidateContext, get_candidate, require_roles

router = APIRouter(tags=["proctoring"])

CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)

# severity policy per event kind under the "standard" policy (FR-076)
DEFAULT_SEVERITY = {
    "tab_switch": "warning",
    "window_blur": "info",
    "fullscreen_exit": "warning",
    "copy_attempt": "warning",
    "paste_attempt": "warning",
    "camera_lost": "red_flag",
    "mic_lost": "warning",
    "capture_failed": "info",
    "devtools_open": "red_flag",
    "multi_display": "warning",
    "window_resize": "red_flag",
    "print_screen_attempt": "red_flag",
    "blocked_shortcut": "red_flag",
}


class EventIn(BaseModel):
    kind: str
    occurred_at: datetime | None = None
    detail: dict = {}


class EventsIn(BaseModel):
    events: list[EventIn]


def _severity_for(kind: str, policy: str) -> str:
    base = DEFAULT_SEVERITY.get(kind, "info")
    if policy == "lenient":
        return "info"
    if policy == "strict" and base == "warning":
        return "red_flag"
    return base


def _clamp_occurred(occurred_at: datetime | None, received: datetime) -> datetime:
    """UT-M8-05: client timestamps beyond skew tolerance clamp to server time."""
    if occurred_at is None:
        return received
    occurred = occurred_at.replace(tzinfo=None)
    if abs(occurred - received) > CLOCK_SKEW_TOLERANCE:
        return received
    return occurred


@router.post("/exam/proctoring/events")
async def ingest_events(
    body: EventsIn,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db, ctx.assignment.id)
    if session is None:
        raise HTTPException(409, "no_active_session")
    assessment = (
        await db.execute(
            select(Assessment).where(Assessment.id == ctx.assignment.assessment_id)
        )
    ).scalar_one()
    policy = (assessment.settings or {}).get("proctoring_policy", "standard")
    received = now_utc()
    accepted = 0
    for event in body.events:
        if event.kind not in CLIENT_EVENT_KINDS:
            raise HTTPException(422, {"code": "invalid_event_kind", "details": [event.kind]})
        db.add(
            ProctoringEvent(
                session_id=session.id,
                kind=event.kind,
                severity=_severity_for(event.kind, policy),
                occurred_at=_clamp_occurred(event.occurred_at, received),
                received_at=received,
                detail=event.detail,
            )
        )
        accepted += 1
    await db.commit()
    return {"data": {"accepted": accepted}, "error": None}


class EvidenceIn(BaseModel):
    kind: str = "screenshot"
    image_base64: str  # data URL or bare base64 (direct-to-S3 presign in prod, R8)
    captured_at: datetime | None = None


@router.post("/exam/proctoring/evidence")
async def ingest_evidence(
    body: EvidenceIn,
    ctx: CandidateContext = Depends(get_candidate),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db, ctx.assignment.id)
    if session is None:
        raise HTTPException(409, "no_active_session")
    try:
        object_key = put_base64_image(f"evidence/{session.id}", body.image_base64)
    except Exception:
        db.add(
            ProctoringEvent(
                session_id=session.id,
                kind="capture_failed",
                severity="info",
                occurred_at=now_utc(),
                detail={"reason": "invalid image payload"},
            )
        )
        await db.commit()
        raise HTTPException(422, "invalid_image") from None
    evidence = ProctoringEvidence(
        session_id=session.id,
        kind=body.kind,
        object_key=object_key,
        captured_at=_clamp_occurred(body.captured_at, now_utc()),
    )
    db.add(evidence)
    await db.flush()
    content = get_object(object_key)
    if content is not None:
        try:
            mime_type = "image/png" if object_key.endswith(".png") else "image/jpeg"
            analysis = await asyncio.to_thread(analyze_proctoring_image, content, mime_type)
            evidence.analysis = analysis
            evidence.analyzed = True
            for flag in analysis.get("flags", []):
                db.add(
                    ProctoringEvent(
                        session_id=session.id,
                        kind=flag,
                        severity="red_flag",
                        occurred_at=evidence.captured_at,
                        detail={
                            "confidence": analysis.get("confidence", 0),
                            "note": analysis.get("note", ""),
                            "model": analysis.get("model", "stub"),
                        },
                        evidence_id=evidence.id,
                    )
                )
        except Exception:
            evidence.analysis = {"flags": [], "error": "AI analysis unavailable"}
            evidence.analyzed = False
    await db.commit()
    return {"data": {"evidence_id": evidence.id, "object_key": object_key}, "error": None}


async def _session_for_admin(
    db: AsyncSession, org_id: str, session_id: str
) -> ExamSession:
    row = (
        await db.execute(
            select(ExamSession)
            .join(TestAssignment, TestAssignment.id == ExamSession.assignment_id)
            .where(ExamSession.id == session_id, TestAssignment.org_id == org_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not_found")
    return row


@router.get("/sessions/{session_id}/proctoring/timeline")
async def proctoring_timeline(
    session_id: str,
    ctx: AdminContext = Depends(require_roles("evaluator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    session = await _session_for_admin(db, ctx.org_id, session_id)
    events = (
        (
            await db.execute(
                select(ProctoringEvent)
                .where(ProctoringEvent.session_id == session.id)
                .order_by(ProctoringEvent.occurred_at)
            )
        )
        .scalars()
        .all()
    )
    evidence = (
        (
            await db.execute(
                select(ProctoringEvidence)
                .where(ProctoringEvidence.session_id == session.id)
                .order_by(ProctoringEvidence.captured_at)
            )
        )
        .scalars()
        .all()
    )
    return {
        "data": {
            "events": [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "severity": e.severity,
                    "occurred_at": e.occurred_at.isoformat(),
                    "detail": e.detail,
                }
                for e in events
            ],
            "evidence": [
                {
                    "id": ev.id,
                    "kind": ev.kind,
                    "object_key": ev.object_key,
                    "captured_at": ev.captured_at.isoformat(),
                    "analysis": ev.analysis,
                }
                for ev in evidence
            ],
        },
        "error": None,
    }


@router.get("/sessions/{session_id}/proctoring/flags")
async def proctoring_flags(
    session_id: str,
    ctx: AdminContext = Depends(require_roles("evaluator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    session = await _session_for_admin(db, ctx.org_id, session_id)
    events = (
        (
            await db.execute(
                select(ProctoringEvent).where(
                    ProctoringEvent.session_id == session.id,
                    ProctoringEvent.severity.in_(("warning", "red_flag")),
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        "data": {
            "red_flags": [
                {"kind": e.kind, "occurred_at": e.occurred_at.isoformat(), "detail": e.detail}
                for e in events
                if e.severity == "red_flag"
            ],
            "warnings": [
                {"kind": e.kind, "occurred_at": e.occurred_at.isoformat(), "detail": e.detail}
                for e in events
                if e.severity == "warning"
            ],
        },
        "error": None,
    }
