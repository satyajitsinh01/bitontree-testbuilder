import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...db import get_db
from ...models import (
    Answer,
    AnswerCheckpoint,
    Assessment,
    Candidate,
    CodeSubmission,
    Evaluation,
    ExamSession,
    ProctoringEvent,
    QuestionVersion,
    Report,
    SessionQuestion,
    TestAssignment,
)
from ...services.audit import write_audit
from ..deps import AdminContext, require_roles

router = APIRouter(tags=["reports"])


async def _completed_reports(
    db: AsyncSession, assessment_id: str
) -> list[tuple[Report, ExamSession, TestAssignment, Candidate]]:
    rows = (
        await db.execute(
            select(Report, ExamSession, TestAssignment, Candidate)
            .join(ExamSession, ExamSession.id == Report.session_id)
            .join(TestAssignment, TestAssignment.id == ExamSession.assignment_id)
            .join(Candidate, Candidate.id == TestAssignment.candidate_id)
            .where(TestAssignment.assessment_id == assessment_id)
            .order_by(Report.overall_score.desc())
        )
    ).all()
    return list(rows)


def _apply_percentiles(rows: list, threshold: int) -> dict[str, dict]:
    """Percentile/rank only when cohort >= threshold (FR-087); ties share rank."""
    stats: dict[str, dict] = {}
    n = len(rows)
    if n == 0:
        return stats
    show = n >= threshold
    previous_score: float | None = None
    previous_rank = 0
    for index, (report, *_rest) in enumerate(rows, start=1):
        if previous_score is not None and report.overall_score == previous_score:
            rank = previous_rank
        else:
            rank = index
        previous_score, previous_rank = report.overall_score, rank
        below = sum(1 for r, *_ in rows if r.overall_score < report.overall_score)
        stats[report.id] = {
            "rank": rank if show else None,
            "percentile": round(below / n * 100, 1) if show else None,
        }
    return stats


@router.get("/assessments/{assessment_id}/results")
async def assessment_results(
    assessment_id: str,
    ctx: AdminContext = Depends(require_roles("evaluator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    assessment = (
        await db.execute(
            select(Assessment).where(
                Assessment.id == assessment_id, Assessment.org_id == ctx.org_id
            )
        )
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(404, "not_found")
    threshold = (assessment.settings or {}).get(
        "percentile_threshold", get_settings().percentile_min_cohort
    )
    rows = await _completed_reports(db, assessment_id)
    stats = _apply_percentiles(rows, threshold)
    items = [
        {
            "session_id": session.id,
            "report_id": report.id,
            "candidate": {"full_name": candidate.full_name, "email": candidate.email},
            "status": session.status,
            "overall_score": report.overall_score,
            "overall_max": report.overall_max,
            "red_flag_count": report.red_flag_count,
            "warning_count": report.warning_count,
            "report_status": report.status,
            **stats.get(report.id, {"rank": None, "percentile": None}),
        }
        for report, session, assignment, candidate in rows
    ]
    return {"data": {"items": items, "cohort_size": len(rows)}, "error": None}


async def _session_bundle(db: AsyncSession, org_id: str, session_id: str):
    row = (
        await db.execute(
            select(ExamSession, TestAssignment, Candidate, Assessment)
            .join(TestAssignment, TestAssignment.id == ExamSession.assignment_id)
            .join(Candidate, Candidate.id == TestAssignment.candidate_id)
            .join(Assessment, Assessment.id == TestAssignment.assessment_id)
            .where(ExamSession.id == session_id, TestAssignment.org_id == org_id)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "not_found")
    return row


@router.get("/sessions/{session_id}/report")
async def session_report(
    session_id: str,
    ctx: AdminContext = Depends(require_roles("evaluator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    session, assignment, candidate, assessment = await _session_bundle(
        db, ctx.org_id, session_id
    )
    report = (
        await db.execute(select(Report).where(Report.session_id == session.id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(404, "report_not_ready")
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
    return {
        "data": {
            "report_id": report.id,
            "candidate": {"full_name": candidate.full_name, "email": candidate.email},
            "assessment": {"id": assessment.id, "title": assessment.title},
            "session": {
                "id": session.id,
                "status": session.status,
                "started_at": session.started_at.isoformat(),
                "submitted_at": session.submitted_at.isoformat()
                if session.submitted_at
                else None,
            },
            "overall_score": report.overall_score,
            "overall_max": report.overall_max,
            "section_scores": report.section_scores,
            "ai_observations": report.ai_observations,
            "red_flag_count": report.red_flag_count,
            "warning_count": report.warning_count,
            "percentile": report.percentile,
            "rank": report.rank,
            "status": report.status,
            "proctoring_timeline": [
                {
                    "kind": e.kind,
                    "severity": e.severity,
                    "occurred_at": e.occurred_at.isoformat(),
                }
                for e in events
            ],
        },
        "error": None,
    }


@router.get("/sessions/{session_id}/answers")
async def session_answers(
    session_id: str,
    ctx: AdminContext = Depends(require_roles("evaluator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    session, *_ = await _session_bundle(db, ctx.org_id, session_id)
    session_questions = (
        (
            await db.execute(
                select(SessionQuestion)
                .where(SessionQuestion.session_id == session.id)
                .order_by(SessionQuestion.order_index)
            )
        )
        .scalars()
        .all()
    )
    items = []
    for sq in session_questions:
        version = (
            await db.execute(
                select(QuestionVersion).where(QuestionVersion.id == sq.question_version_id)
            )
        ).scalar_one()
        answer = (
            await db.execute(
                select(Answer).where(
                    Answer.session_id == session.id, Answer.session_question_id == sq.id
                )
            )
        ).scalar_one_or_none()
        evaluation = (
            await db.execute(
                select(Evaluation).where(Evaluation.session_question_id == sq.id)
            )
        ).scalar_one_or_none()
        checkpoints = []
        code_history = []
        if answer is not None:
            checkpoints = [
                {"kind": c.kind, "created_at": c.created_at.isoformat()}
                for c in (
                    await db.execute(
                        select(AnswerCheckpoint)
                        .where(AnswerCheckpoint.answer_id == answer.id)
                        .order_by(AnswerCheckpoint.created_at)
                    )
                ).scalars()
            ]
        if version.qtype == "coding":
            code_history = [
                {
                    "id": s.id,
                    "kind": s.kind,
                    "language": s.language,
                    "status": s.status,
                    "score": s.score,
                    "exec_time_ms": s.exec_time_ms,
                    "created_at": s.created_at.isoformat(),
                    "source_code": s.source_code,
                }
                for s in (
                    await db.execute(
                        select(CodeSubmission)
                        .where(CodeSubmission.session_question_id == sq.id)
                        .order_by(CodeSubmission.created_at)
                    )
                ).scalars()
            ]
        items.append(
            {
                "session_question_id": sq.id,
                "qtype": version.qtype,
                "title": version.title,
                "config": version.config,  # full config incl. answers (admin view)
                "answer": answer.payload if answer else None,
                "checkpoints": checkpoints,
                "code_history": code_history,
                "evaluation": None
                if evaluation is None
                else {
                    "id": evaluation.id,
                    "method": evaluation.method,
                    "auto_score": evaluation.auto_score,
                    "ai_score": evaluation.ai_score,
                    "ai_rationale": evaluation.ai_rationale,
                    "ai_confidence": evaluation.ai_confidence,
                    "final_score": evaluation.final_score,
                    "max_score": evaluation.max_score,
                    "overridden_by": evaluation.overridden_by,
                    "override_reason": evaluation.override_reason,
                },
            }
        )
    return {"data": {"items": items}, "error": None}


@router.post("/sessions/{session_id}/report/finalize")
async def finalize_report(
    session_id: str,
    ctx: AdminContext = Depends(require_roles("evaluator")),
    db: AsyncSession = Depends(get_db),
):
    session, *_ = await _session_bundle(db, ctx.org_id, session_id)
    report = (
        await db.execute(select(Report).where(Report.session_id == session.id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(404, "report_not_ready")
    report.status = "finalized"
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="report.finalized",
        entity_type="report",
        entity_id=report.id,
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": {"status": "finalized"}, "error": None}


@router.post("/assessments/{assessment_id}/results/export", response_class=PlainTextResponse)
async def export_results_csv(
    assessment_id: str,
    ctx: AdminContext = Depends(require_roles("evaluator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    rows = await _completed_reports(db, assessment_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["name", "email", "status", "overall_score", "overall_max", "red_flags",
         "warnings", "report_status"]
    )
    for report, session, _assignment, candidate in rows:
        writer.writerow(
            [
                candidate.full_name,
                candidate.email,
                session.status,
                report.overall_score,
                report.overall_max,
                report.red_flag_count,
                report.warning_count,
                report.status,
            ]
        )
    return PlainTextResponse(buffer.getvalue(), media_type="text/csv")
