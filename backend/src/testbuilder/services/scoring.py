"""Automatic evaluation (FR-080..082): MCQ exact scoring, coding test-case
scoring from the final submitted checkpoint, AI-assisted text review."""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Answer,
    CodeSubmission,
    Evaluation,
    ExamSession,
    ProctoringEvent,
    QuestionVersion,
    Report,
    Section,
    SessionQuestion,
    SessionSection,
)
from . import ai as ai_service

log = structlog.get_logger()


def score_mcq(config: dict, payload: dict, max_score: float, negative_marks: float = 0.0) -> float:
    """Exact-set match for single and multi correct (UT-M9-01). Unanswered -> 0."""
    selected = set(payload.get("selected_option_ids") or [])
    if not selected:
        return 0.0
    correct = set(config.get("correct_option_ids") or [])
    if selected == correct:
        return max_score
    return -abs(negative_marks) if negative_marks else 0.0


def score_code_cases(cases: list[dict], results: list[dict], max_score: float) -> float:
    """Weighted per-case partial credit (UT-M7-03)."""
    weights = {c["id"]: float(c.get("weight", 1)) for c in cases}
    total = sum(weights.values())
    if total == 0:
        return 0.0
    earned = sum(weights.get(r["case_id"], 0) for r in results if r.get("passed"))
    return round(max_score * earned / total, 4)


async def _latest_submit(
    db: AsyncSession, session_question_id: str
) -> CodeSubmission | None:
    return (
        await db.execute(
            select(CodeSubmission)
            .where(
                CodeSubmission.session_question_id == session_question_id,
                CodeSubmission.kind == "submit",
            )
            .order_by(CodeSubmission.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def evaluate_session(db: AsyncSession, session: ExamSession) -> Report:
    """Runs on submission (FT-M9-01). Idempotent: re-running replaces nothing that
    a human has overridden."""
    session_questions = (
        (
            await db.execute(
                select(SessionQuestion).where(SessionQuestion.session_id == session.id)
            )
        )
        .scalars()
        .all()
    )
    section_totals: dict[str, dict] = {}
    for sq in session_questions:
        version = (
            await db.execute(
                select(QuestionVersion).where(QuestionVersion.id == sq.question_version_id)
            )
        ).scalar_one()
        answer = (
            await db.execute(
                select(Answer).where(
                    Answer.session_id == session.id,
                    Answer.session_question_id == sq.id,
                )
            )
        ).scalar_one_or_none()
        payload = answer.payload if answer else {}
        existing = (
            await db.execute(
                select(Evaluation).where(Evaluation.session_question_id == sq.id)
            )
        ).scalar_one_or_none()
        if existing is not None and existing.overridden_by is not None:
            evaluation = existing  # human override wins (FR-083)
        else:
            if existing is None:
                evaluation = Evaluation(session_question_id=sq.id, method="manual",
                                        max_score=sq.points)
                db.add(evaluation)
            else:
                evaluation = existing
            evaluation.max_score = sq.points
            if version.qtype == "mcq":
                evaluation.method = "auto_mcq"
                evaluation.auto_score = score_mcq(
                    version.config, payload, sq.points,
                    float(version.config.get("negative_marks", 0) or 0),
                )
                evaluation.final_score = evaluation.auto_score
            elif version.qtype == "coding":
                evaluation.method = "auto_code"
                submission = await _latest_submit(db, sq.id)
                evaluation.auto_score = submission.score if submission and submission.score else 0.0
                evaluation.final_score = evaluation.auto_score
            else:  # text -> AI-assisted (FR-082)
                evaluation.method = "ai_text"
                try:
                    result = ai_service.evaluate_written(
                        version.config.get("rubric", ""),
                        version.config.get("expected_answer", ""),
                        str(payload.get("text", "")),
                        sq.points,
                    )
                except Exception as exc:
                    log.warning("ai_text_eval_failed", error=str(exc))
                    result = {"score": 0.0, "rationale": "AI evaluation failed; "
                              "needs manual review.", "confidence": 0.0}
                evaluation.ai_score = result["score"]
                evaluation.ai_rationale = result["rationale"]
                evaluation.ai_confidence = result["confidence"]
                evaluation.final_score = result["score"]
        bucket = section_totals.setdefault(
            sq.section_id,
            {"score": 0.0, "max": 0.0, "attempted": 0, "unattempted": 0,
             "correct": 0, "wrong": 0},
        )
        bucket["score"] += evaluation.final_score
        bucket["max"] += sq.points
        answered = bool(payload)
        bucket["attempted" if answered else "unattempted"] += 1
        if answered:
            if evaluation.final_score >= sq.points:
                bucket["correct"] += 1
            elif evaluation.final_score <= 0:
                bucket["wrong"] += 1

    section_scores = []
    for section_id, totals in section_totals.items():
        section = (
            await db.execute(select(Section).where(Section.id == section_id))
        ).scalar_one()
        session_section = (
            await db.execute(
                select(SessionSection).where(
                    SessionSection.session_id == session.id,
                    SessionSection.section_id == section_id,
                )
            )
        ).scalar_one_or_none()
        section_scores.append(
            {
                "section_id": section_id,
                "name": section.name,
                "weightage_pct": section.weightage_pct,
                "score": round(totals["score"], 2),
                "max": round(totals["max"], 2),
                "time_spent_sec": session_section.time_spent_sec if session_section else 0,
                "attempted": totals["attempted"],
                "unattempted": totals["unattempted"],
                "correct": totals["correct"],
                "wrong": totals["wrong"],
            }
        )
    # weighted overall (UT-M9-02): section weightage applied over section max
    overall_score = 0.0
    for entry in section_scores:
        if entry["max"] > 0:
            overall_score += entry["score"] / entry["max"] * entry["weightage_pct"]
    overall_max = sum(e["weightage_pct"] for e in section_scores) or 100.0

    events = (
        (
            await db.execute(
                select(ProctoringEvent).where(ProctoringEvent.session_id == session.id)
            )
        )
        .scalars()
        .all()
    )
    red_flags = sum(1 for e in events if e.severity == "red_flag")
    warnings = sum(1 for e in events if e.severity == "warning")

    report = (
        await db.execute(select(Report).where(Report.session_id == session.id))
    ).scalar_one_or_none()
    if report is None:
        report = Report(session_id=session.id)
        db.add(report)
    report.overall_score = round(overall_score, 2)
    report.overall_max = round(overall_max, 2)
    report.section_scores = section_scores
    report.red_flag_count = red_flags
    report.warning_count = warnings
    try:
        report.ai_observations = ai_service.summarize_performance(
            {
                "overall_score": report.overall_score,
                "overall_max": report.overall_max,
                "sections": section_scores,
                "red_flags": red_flags,
                "warnings": warnings,
            }
        )
    except Exception as exc:
        log.warning("ai_summary_failed", error=str(exc))
        report.ai_observations = ""
    return report
