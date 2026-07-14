from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import (
    Evaluation,
    ExamSession,
    Report,
    SessionQuestion,
    TestAssignment,
)
from ...services.audit import write_audit
from ..deps import AdminContext, require_roles

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


class OverrideIn(BaseModel):
    final_score: float
    override_reason: str = Field(min_length=3)


@router.patch("/{evaluation_id}")
async def override_evaluation(
    evaluation_id: str,
    body: OverrideIn,
    ctx: AdminContext = Depends(require_roles("evaluator")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Evaluation, ExamSession)
            .join(SessionQuestion, SessionQuestion.id == Evaluation.session_question_id)
            .join(ExamSession, ExamSession.id == SessionQuestion.session_id)
            .join(TestAssignment, TestAssignment.id == ExamSession.assignment_id)
            .where(Evaluation.id == evaluation_id, TestAssignment.org_id == ctx.org_id)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "not_found")
    evaluation, session = row
    report = (
        await db.execute(select(Report).where(Report.session_id == session.id))
    ).scalar_one_or_none()
    if report is not None and report.status == "finalized":
        raise HTTPException(409, "report_finalized")
    if body.final_score < 0 or body.final_score > evaluation.max_score:
        raise HTTPException(
            422,
            {"code": "score_out_of_range", "details": [f"max is {evaluation.max_score}"]},
        )
    before = evaluation.final_score
    evaluation.final_score = body.final_score
    evaluation.overridden_by = ctx.user.id
    evaluation.override_reason = body.override_reason
    # audit row commits atomically with the override (FR-083)
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="score.overridden",
        entity_type="evaluation",
        entity_id=evaluation.id,
        before={"final_score": before},
        after={"final_score": body.final_score, "reason": body.override_reason},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    # recompute the report totals with the override in place
    if session is not None:
        from ...services.scoring import evaluate_session

        await evaluate_session(db, session)
    await db.commit()
    return {
        "data": {
            "id": evaluation.id,
            "final_score": evaluation.final_score,
            "overridden_by": ctx.user.id,
        },
        "error": None,
    }
