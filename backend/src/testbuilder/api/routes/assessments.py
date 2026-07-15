from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import (
    Assessment,
    AssessmentVersion,
    Question,
    Section,
    SectionPoolRule,
    SectionQuestion,
)
from ...models.base import now_utc
from ...services.audit import write_audit
from ...services.versioning import (
    get_current_version,
    get_or_fork_draft,
    publish,
    validate_for_publish,
)
from ..deps import AdminContext, require_roles

router = APIRouter(prefix="/assessments", tags=["assessments"])


class AssessmentIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = ""
    window_start_at: datetime
    window_end_at: datetime
    settings: dict = {}


class SectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    duration_min: int = Field(gt=0)
    weightage_pct: float = Field(ge=0, le=100, multiple_of=0.01)
    allowed_qtypes: list[str] = []
    question_count: int = 0
    order_index: int | None = None
    is_final: bool = False


async def _get_assessment(db: AsyncSession, org_id: str, assessment_id: str) -> Assessment:
    assessment = (
        await db.execute(
            select(Assessment).where(
                Assessment.id == assessment_id, Assessment.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(404, "not_found")
    return assessment


async def _validate_section_weight_total(
    db: AsyncSession,
    version_id: str,
    proposed_weight: float,
    *,
    exclude_section_id: str | None = None,
) -> None:
    query = select(Section.weightage_pct).where(
        Section.assessment_version_id == version_id
    )
    if exclude_section_id is not None:
        query = query.where(Section.id != exclude_section_id)
    existing_weights = (await db.execute(query)).scalars().all()
    total = sum((Decimal(str(weight)) for weight in existing_weights), Decimal("0"))
    total += Decimal(str(proposed_weight))
    if total > Decimal("100"):
        raise HTTPException(
            422,
            {
                "code": "section_weightage_exceeded",
                "message": "Section weightages cannot exceed 100%.",
                "details": [f"proposed total is {total}%"],
            },
        )


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def _assessment_duration_minutes(assessment: Assessment) -> int:
    if assessment.window_start_at is None or assessment.window_end_at is None:
        raise HTTPException(422, "assessment_window_required")
    seconds = (assessment.window_end_at - assessment.window_start_at).total_seconds()
    if seconds <= 0 or seconds % 60 != 0:
        raise HTTPException(422, "assessment_window_must_use_whole_minutes")
    if assessment.window_end_at <= now_utc():
        raise HTTPException(422, "assessment_window_must_end_in_future")
    return int(seconds // 60)


async def _validate_section_duration_total(
    db: AsyncSession,
    assessment: Assessment,
    version_id: str,
    proposed_duration: int,
    *,
    exclude_section_id: str | None = None,
) -> None:
    query = select(Section.duration_min).where(Section.assessment_version_id == version_id)
    if exclude_section_id is not None:
        query = query.where(Section.id != exclude_section_id)
    allocated = sum((await db.execute(query)).scalars().all()) + proposed_duration
    available = _assessment_duration_minutes(assessment)
    if allocated > available:
        raise HTTPException(
            422,
            {
                "code": "section_duration_exceeded",
                "message": "Section durations cannot exceed the assessment window.",
                "details": [f"allocated {allocated} minutes; available {available} minutes"],
            },
        )


async def _sections_out(db: AsyncSession, version: AssessmentVersion) -> list[dict]:
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
    out = []
    for section in sections:
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
        out.append(
            {
                "id": section.id,
                "order_index": section.order_index,
                "name": section.name,
                "description": section.description,
                "duration_min": section.duration_min,
                "weightage_pct": section.weightage_pct,
                "allowed_qtypes": section.allowed_qtypes,
                "question_count": section.question_count,
                "is_final": section.is_final,
                "questions": [
                    {
                        "question_version_id": p.question_version_id,
                        "pool_group": p.pool_group,
                        "points": p.points,
                    }
                    for p in picks
                ],
                "pool_rules": [
                    {"pool_group": r.pool_group, "select_count": r.select_count}
                    for r in rules
                ],
            }
        )
    return out


async def _assessment_out(db: AsyncSession, assessment: Assessment) -> dict:
    version = await get_current_version(db, assessment)
    return {
        "id": assessment.id,
        "title": assessment.title,
        "description": assessment.description,
        "window_start_at": assessment.window_start_at.isoformat()
        if assessment.window_start_at
        else None,
        "window_end_at": assessment.window_end_at.isoformat()
        if assessment.window_end_at
        else None,
        "status": assessment.status,
        "settings": assessment.settings,
        "version": None
        if version is None
        else {
            "id": version.id,
            "version": version.version,
            "frozen": version.frozen,
            "total_duration_min": version.total_duration_min,
            "published_at": version.published_at.isoformat()
            if version.published_at
            else None,
            "sections": await _sections_out(db, version),
        },
    }


@router.get("")
async def list_assessments(
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    ctx: AdminContext = Depends(require_roles("test_creator", "hr_admin", "evaluator")),
    db: AsyncSession = Depends(get_db),
):
    base = select(Assessment).where(Assessment.org_id == ctx.org_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(Assessment.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        .scalars()
        .all()
    )
    items = [
        {"id": a.id, "title": a.title, "status": a.status, "created_at": a.created_at.isoformat()}
        for a in rows
    ]
    return {"data": {"items": items, "total": total, "page": page, "size": size}, "error": None}


@router.post("", status_code=201)
async def create_assessment(
    body: AssessmentIn,
    ctx: AdminContext = Depends(require_roles("test_creator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    assessment = Assessment(
        org_id=ctx.org_id,
        title=body.title,
        description=body.description,
        window_start_at=_naive(body.window_start_at),
        window_end_at=_naive(body.window_end_at),
        settings=body.settings,
        created_by=ctx.user.id,
    )
    _assessment_duration_minutes(assessment)
    db.add(assessment)
    await db.flush()
    await get_or_fork_draft(db, assessment)
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="assessment.created",
        entity_type="assessment",
        entity_id=assessment.id,
        after={"title": body.title},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": await _assessment_out(db, assessment), "error": None}


@router.get("/{assessment_id}")
async def get_assessment(
    assessment_id: str,
    ctx: AdminContext = Depends(require_roles("test_creator", "hr_admin", "evaluator")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await _get_assessment(db, ctx.org_id, assessment_id)
    return {"data": await _assessment_out(db, assessment), "error": None}


class AssessmentPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    settings: dict | None = None


@router.patch("/{assessment_id}")
async def patch_assessment(
    assessment_id: str,
    body: AssessmentPatch,
    ctx: AdminContext = Depends(require_roles("test_creator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await _get_assessment(db, ctx.org_id, assessment_id)
    version = await get_or_fork_draft(db, assessment)  # forks when frozen (FR-034)
    if body.title is not None:
        assessment.title = body.title
    if body.description is not None:
        assessment.description = body.description
    if body.settings is not None:
        assessment.settings = {**assessment.settings, **body.settings}
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="assessment.updated",
        entity_type="assessment",
        entity_id=assessment.id,
        after=body.model_dump(exclude_none=True) | {"version": version.version},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": await _assessment_out(db, assessment), "error": None}


@router.post("/{assessment_id}/sections", status_code=201)
async def add_section(
    assessment_id: str,
    body: SectionIn,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await _get_assessment(db, ctx.org_id, assessment_id)
    version = await get_or_fork_draft(db, assessment)
    await _validate_section_weight_total(db, version.id, body.weightage_pct)
    await _validate_section_duration_total(db, assessment, version.id, body.duration_min)
    if body.order_index is None:
        max_order = (
            await db.execute(
                select(func.max(Section.order_index)).where(
                    Section.assessment_version_id == version.id
                )
            )
        ).scalar()
        body.order_index = 0 if max_order is None else max_order + 1
    section = Section(assessment_version_id=version.id, **body.model_dump())
    db.add(section)
    await db.commit()
    return {"data": {"id": section.id, "order_index": section.order_index}, "error": None}


@router.get("/{assessment_id}/versions")
async def list_versions(
    assessment_id: str,
    ctx: AdminContext = Depends(require_roles("test_creator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await _get_assessment(db, ctx.org_id, assessment_id)
    versions = (
        (
            await db.execute(
                select(AssessmentVersion)
                .where(AssessmentVersion.assessment_id == assessment.id)
                .order_by(AssessmentVersion.version)
            )
        )
        .scalars()
        .all()
    )
    return {
        "data": {
            "items": [
                {
                    "id": v.id,
                    "version": v.version,
                    "frozen": v.frozen,
                    "published_at": v.published_at.isoformat() if v.published_at else None,
                    "is_current": v.id == assessment.current_version_id,
                }
                for v in versions
            ]
        },
        "error": None,
    }


@router.post("/{assessment_id}/publish")
async def publish_assessment(
    assessment_id: str,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    assessment = await _get_assessment(db, ctx.org_id, assessment_id)
    version = await get_current_version(db, assessment)
    if version is None:
        raise HTTPException(422, {"code": "publish_failed", "details": ["no version"]})
    errors = await validate_for_publish(db, ctx.org_id, version)
    if errors:
        raise HTTPException(422, {"code": "publish_failed", "details": errors})
    await publish(db, assessment, version, ctx.user.id)
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="assessment.published",
        entity_type="assessment",
        entity_id=assessment.id,
        after={"version": version.version},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": await _assessment_out(db, assessment), "error": None}


# --- Section-level endpoints -------------------------------------------------

section_router = APIRouter(prefix="/sections", tags=["sections"])


async def _get_section_ctx(
    db: AsyncSession, org_id: str, section_id: str
) -> tuple[Section, AssessmentVersion, Assessment]:
    row = (
        await db.execute(
            select(Section, AssessmentVersion, Assessment)
            .join(
                AssessmentVersion, AssessmentVersion.id == Section.assessment_version_id
            )
            .join(Assessment, Assessment.id == AssessmentVersion.assessment_id)
            .where(Section.id == section_id, Assessment.org_id == org_id)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "not_found")
    return row


@section_router.patch("/{section_id}")
async def patch_section(
    section_id: str,
    body: SectionIn,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    section, version, assessment = await _get_section_ctx(db, ctx.org_id, section_id)
    if version.frozen:
        raise HTTPException(
            409,
            {
                "code": "version_frozen",
                "details": ["edit the assessment to fork a new draft version first"],
            },
        )
    await _validate_section_weight_total(
        db,
        version.id,
        body.weightage_pct,
        exclude_section_id=section.id,
    )
    await _validate_section_duration_total(
        db,
        assessment,
        version.id,
        body.duration_min,
        exclude_section_id=section.id,
    )
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(section, field, value)
    await db.commit()
    return {"data": {"id": section.id}, "error": None}


@section_router.delete("/{section_id}")
async def delete_section(
    section_id: str,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    section, version, _ = await _get_section_ctx(db, ctx.org_id, section_id)
    if version.frozen:
        raise HTTPException(409, "version_frozen")
    for model in (SectionQuestion, SectionPoolRule):
        rows = (
            (await db.execute(select(model).where(model.section_id == section.id)))
            .scalars()
            .all()
        )
        for row in rows:
            await db.delete(row)
    await db.delete(section)
    await db.commit()
    return {"data": {"deleted": True}, "error": None}


class SectionQuestionsIn(BaseModel):
    items: list[dict]  # {question_id, pool_group?, points?}


@section_router.put("/{section_id}/questions")
async def set_section_questions(
    section_id: str,
    body: SectionQuestionsIn,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    section, version, _ = await _get_section_ctx(db, ctx.org_id, section_id)
    if version.frozen:
        raise HTTPException(409, "version_frozen")
    existing = (
        (
            await db.execute(
                select(SectionQuestion).where(SectionQuestion.section_id == section.id)
            )
        )
        .scalars()
        .all()
    )
    for row in existing:
        await db.delete(row)
    for item in body.items:
        question = (
            await db.execute(
                select(Question).where(
                    Question.id == item.get("question_id"), Question.org_id == ctx.org_id
                )
            )
        ).scalar_one_or_none()
        if question is None or question.current_version_id is None:
            raise HTTPException(422, {"code": "unknown_question", "details": [str(item)]})
        db.add(
            SectionQuestion(
                section_id=section.id,
                question_version_id=question.current_version_id,
                pool_group=item.get("pool_group"),
                points=float(item.get("points", 1.0)),
            )
        )
    await db.commit()
    return {"data": {"count": len(body.items)}, "error": None}


class PoolRulesIn(BaseModel):
    items: list[dict]  # {pool_group, select_count}


@section_router.put("/{section_id}/pool-rules")
async def set_pool_rules(
    section_id: str,
    body: PoolRulesIn,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    section, version, _ = await _get_section_ctx(db, ctx.org_id, section_id)
    if version.frozen:
        raise HTTPException(409, "version_frozen")
    existing = (
        (
            await db.execute(
                select(SectionPoolRule).where(SectionPoolRule.section_id == section.id)
            )
        )
        .scalars()
        .all()
    )
    for row in existing:
        await db.delete(row)
    for item in body.items:
        db.add(
            SectionPoolRule(
                section_id=section.id,
                pool_group=str(item["pool_group"]),
                select_count=int(item["select_count"]),
            )
        )
    await db.commit()
    return {"data": {"count": len(body.items)}, "error": None}
