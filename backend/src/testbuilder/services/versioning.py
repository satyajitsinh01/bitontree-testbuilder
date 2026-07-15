from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Assessment,
    AssessmentVersion,
    Question,
    QuestionVersion,
    Section,
    SectionPoolRule,
    SectionQuestion,
)
from ..models.base import now_utc


async def get_current_version(
    db: AsyncSession, assessment: Assessment
) -> AssessmentVersion | None:
    if not assessment.current_version_id:
        return None
    return (
        await db.execute(
            select(AssessmentVersion).where(
                AssessmentVersion.id == assessment.current_version_id
            )
        )
    ).scalar_one_or_none()


async def _copy_version_contents(
    db: AsyncSession, source: AssessmentVersion, target: AssessmentVersion
) -> None:
    sections = (
        (
            await db.execute(
                select(Section)
                .where(Section.assessment_version_id == source.id)
                .order_by(Section.order_index)
            )
        )
        .scalars()
        .all()
    )
    for section in sections:
        clone = Section(
            assessment_version_id=target.id,
            order_index=section.order_index,
            name=section.name,
            description=section.description,
            duration_min=section.duration_min,
            weightage_pct=section.weightage_pct,
            allowed_qtypes=section.allowed_qtypes,
            question_count=section.question_count,
            navigation=section.navigation,
            is_final=section.is_final,
        )
        db.add(clone)
        await db.flush()
        picks = (
            (
                await db.execute(
                    select(SectionQuestion).where(SectionQuestion.section_id == section.id)
                )
            )
            .scalars()
            .all()
        )
        for pick in picks:
            db.add(
                SectionQuestion(
                    section_id=clone.id,
                    question_version_id=pick.question_version_id,
                    pool_group=pick.pool_group,
                    points=pick.points,
                )
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
        for rule in rules:
            db.add(
                SectionPoolRule(
                    section_id=clone.id,
                    pool_group=rule.pool_group,
                    select_count=rule.select_count,
                )
            )


async def get_or_fork_draft(db: AsyncSession, assessment: Assessment) -> AssessmentVersion:
    """Editing surface (Constitution III / FR-034): an unfrozen current version is
    edited in place; a frozen one forks version n+1 which becomes the new head."""
    current = await get_current_version(db, assessment)
    if current is None:
        version = AssessmentVersion(assessment_id=assessment.id, version=1)
        db.add(version)
        await db.flush()
        assessment.current_version_id = version.id
        return version
    if not current.frozen:
        return current
    fork = AssessmentVersion(assessment_id=assessment.id, version=current.version + 1)
    db.add(fork)
    await db.flush()
    await _copy_version_contents(db, current, fork)
    assessment.current_version_id = fork.id
    return fork


async def freeze_version(db: AsyncSession, version: AssessmentVersion) -> None:
    """Called when the first candidate starts (FR-034)."""
    if not version.frozen:
        version.frozen = True


async def validate_for_publish(
    db: AsyncSession, org_id: str, version: AssessmentVersion
) -> list[str]:
    """FR-038: coverage, weightage, durations, final section."""
    errors: list[str] = []
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
    if not sections:
        return ["assessment needs at least one section"]
    assessment = (
        await db.execute(select(Assessment).where(Assessment.id == version.assessment_id))
    ).scalar_one()
    if assessment.window_start_at is None or assessment.window_end_at is None:
        errors.append("assessment start and end time are required")
    else:
        window_minutes = int(
            (assessment.window_end_at - assessment.window_start_at).total_seconds() // 60
        )
        section_minutes = sum(section.duration_min for section in sections)
        if section_minutes != window_minutes:
            errors.append(
                "section durations must equal the assessment window "
                f"({window_minutes} minutes; currently {section_minutes})"
            )
    weight_total = sum(
        (Decimal(str(section.weightage_pct)) for section in sections), Decimal("0")
    )
    if weight_total != Decimal("100"):
        errors.append(f"section weightages must sum to 100 (currently {weight_total:g})")
    for section in sections:
        if section.duration_min <= 0:
            errors.append(f"section '{section.name}': duration must be > 0")
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
        # every referenced question must be active
        active_by_pool: dict[str | None, int] = {}
        for pick in picks:
            question = (
                await db.execute(
                    select(Question)
                    .join(
                        QuestionVersion,
                        QuestionVersion.question_id == Question.id,
                    )
                    .where(QuestionVersion.id == pick.question_version_id)
                )
            ).scalar_one_or_none()
            if question is None or question.org_id != org_id:
                errors.append(f"section '{section.name}': unknown question reference")
                continue
            if question.status != "active":
                errors.append(
                    f"section '{section.name}': question {question.id} is not active"
                )
                continue
            active_by_pool[pick.pool_group] = active_by_pool.get(pick.pool_group, 0) + 1
        for rule in rules:
            available = active_by_pool.get(rule.pool_group, 0)
            if available < rule.select_count:
                errors.append(
                    f"section '{section.name}': pool '{rule.pool_group}' requires "
                    f"{rule.select_count}, only {available} active questions match"
                )
        delivered = active_by_pool.get(None, 0) + sum(r.select_count for r in rules)
        if section.question_count and section.question_count != delivered:
            errors.append(
                f"section '{section.name}': question_count={section.question_count} but "
                f"rules deliver {delivered}"
            )
    if not sections[-1].is_final:
        # last section implicitly carries Submit and End Test (FR-033)
        sections[-1].is_final = True
    return errors


async def publish(
    db: AsyncSession, assessment: Assessment, version: AssessmentVersion, user_id: str
) -> None:
    sections = (
        (
            await db.execute(
                select(Section).where(Section.assessment_version_id == version.id)
            )
        )
        .scalars()
        .all()
    )
    version.total_duration_min = sum(s.duration_min for s in sections)
    version.published_at = now_utc()
    version.published_by = user_id
    assessment.status = "published"


async def started_sessions_count(db: AsyncSession, version_id: str) -> int:
    from ..models import ExamSession

    return (
        await db.execute(
            select(func.count())
            .select_from(ExamSession)
            .where(ExamSession.assessment_version_id == version_id)
        )
    ).scalar_one()
