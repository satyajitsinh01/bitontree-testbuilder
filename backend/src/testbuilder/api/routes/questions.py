import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import (
    AIGeneration,
    AssessmentVersion,
    Question,
    QuestionQualityFlag,
    QuestionVersion,
    Section,
    SectionQuestion,
)
from ...models.base import now_utc
from ...models.questions import DIFFICULTIES, QTYPES
from ...services import ai as ai_service
from ...services.audit import write_audit
from ...services.quality import find_duplicates, structural_errors
from ..deps import AdminContext, require_roles

log = structlog.get_logger()
router = APIRouter(prefix="/questions", tags=["questions"])


class QuestionIn(BaseModel):
    qtype: str
    title: str = Field(min_length=3, max_length=300)
    body: str = ""
    answer_type: str = "single_choice"
    category: str = "general"
    difficulty: str = "medium"
    config: dict = {}
    topic: str = ""
    skills: list[str] = []
    expected_duration_sec: int = 120
    language: str = "en"
    tags: list[str] = []

    @field_validator("qtype")
    @classmethod
    def qtype_valid(cls, v: str) -> str:
        if v not in QTYPES:
            raise ValueError(f"qtype must be one of {QTYPES}")
        return v

    @field_validator("difficulty")
    @classmethod
    def difficulty_valid(cls, v: str) -> str:
        if v not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}")
        return v


def _version_out(version: QuestionVersion) -> dict:
    return {
        "id": version.id,
        "version": version.version,
        "qtype": version.qtype,
        "category": version.category,
        "answer_type": version.answer_type,
        "difficulty": version.difficulty,
        "title": version.title,
        "body": version.body,
        "config": version.config,
        "topic": version.topic,
        "skills": version.skills,
        "expected_duration_sec": version.expected_duration_sec,
        "language": version.language,
        "tags": version.tags,
    }


def _question_out(question: Question, version: QuestionVersion | None) -> dict:
    return {
        "id": question.id,
        "status": question.status,
        "source": question.source,
        "created_by": question.created_by,
        "approved_by": question.approved_by,
        "current_version": _version_out(version) if version else None,
    }


async def _current_version(db: AsyncSession, question: Question) -> QuestionVersion | None:
    if not question.current_version_id:
        return None
    return (
        await db.execute(
            select(QuestionVersion).where(QuestionVersion.id == question.current_version_id)
        )
    ).scalar_one_or_none()


async def _get_question(db: AsyncSession, org_id: str, question_id: str) -> Question:
    question = (
        await db.execute(
            select(Question).where(
                Question.id == question_id,
                Question.org_id == org_id,
                Question.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if question is None:
        raise HTTPException(404, "not_found")
    return question


async def _record_quality_flags(
    db: AsyncSession, org_id: str, version: QuestionVersion, question_id: str
) -> list[dict]:
    flags = []
    duplicates = await find_duplicates(
        db, org_id, version.title, version.body, exclude_question_id=question_id
    )
    for dup in duplicates:
        db.add(
            QuestionQualityFlag(
                question_version_id=version.id, kind="duplicate", detail=dup
            )
        )
        flags.append({"kind": "duplicate", "detail": dup})
    return flags


@router.get("")
async def list_questions(
    qtype: str | None = None,
    status: str | None = None,
    difficulty: str | None = None,
    category: str | None = None,
    source: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    ctx: AdminContext = Depends(require_roles("test_creator", "hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Question).where(
        Question.org_id == ctx.org_id, Question.deleted_at.is_(None)
    )
    if status:
        query = query.where(Question.status == status)
    if source:
        query = query.where(Question.source == source)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    questions = (
        (
            await db.execute(
                query.order_by(Question.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        .scalars()
        .all()
    )
    items = []
    for question in questions:
        version = await _current_version(db, question)
        if version is None:
            continue
        if qtype and version.qtype != qtype:
            continue
        if difficulty and version.difficulty != difficulty:
            continue
        if category and version.category != category:
            continue
        if q and q.lower() not in f"{version.title} {version.body}".lower():
            continue
        items.append(_question_out(question, version))
    return {
        "data": {"items": items, "total": total, "page": page, "size": size},
        "error": None,
    }


@router.post("", status_code=201)
async def create_question(
    body: QuestionIn,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    errors = structural_errors(body.qtype, body.config)
    if errors:
        raise HTTPException(422, {"code": "invalid_structure", "details": errors})
    question = Question(
        org_id=ctx.org_id, status="active", source="manual", created_by=ctx.user.id
    )
    db.add(question)
    await db.flush()
    version = QuestionVersion(question_id=question.id, version=1, **body.model_dump())
    db.add(version)
    await db.flush()
    question.current_version_id = version.id
    flags = await _record_quality_flags(db, ctx.org_id, version, question.id)
    await db.commit()
    out = _question_out(question, version)
    out["quality_flags"] = flags
    return {"data": out, "error": None}


@router.get("/{question_id}")
async def get_question(
    question_id: str,
    ctx: AdminContext = Depends(require_roles("test_creator", "hr_admin", "evaluator")),
    db: AsyncSession = Depends(get_db),
):
    question = await _get_question(db, ctx.org_id, question_id)
    version = await _current_version(db, question)
    versions = (
        (
            await db.execute(
                select(QuestionVersion)
                .where(QuestionVersion.question_id == question.id)
                .order_by(QuestionVersion.version)
            )
        )
        .scalars()
        .all()
    )
    flags = []
    if version:
        flags = [
            {"kind": f.kind, "detail": f.detail}
            for f in (
                await db.execute(
                    select(QuestionQualityFlag).where(
                        QuestionQualityFlag.question_version_id == version.id
                    )
                )
            ).scalars()
        ]
    out = _question_out(question, version)
    out["versions"] = [{"id": v.id, "version": v.version} for v in versions]
    out["quality_flags"] = flags
    return {"data": out, "error": None}


@router.put("/{question_id}")
async def update_question(
    question_id: str,
    body: QuestionIn,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    question = await _get_question(db, ctx.org_id, question_id)
    errors = structural_errors(body.qtype, body.config)
    if errors:
        raise HTTPException(422, {"code": "invalid_structure", "details": errors})
    current = await _current_version(db, question)
    next_version = (current.version + 1) if current else 1
    version = QuestionVersion(
        question_id=question.id, version=next_version, **body.model_dump()
    )
    db.add(version)
    await db.flush()
    question.current_version_id = version.id
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="question.edited",
        entity_type="question",
        entity_id=question.id,
        after={"version": next_version},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": _question_out(question, version), "error": None}


class StatusIn(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in ("active", "inactive", "archived"):
            raise ValueError("status must be active, inactive, or archived")
        return v


@router.post("/{question_id}/status")
async def set_status(
    question_id: str,
    body: StatusIn,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    question = await _get_question(db, ctx.org_id, question_id)
    if question.status == "draft" and question.source == "ai" and body.status == "active":
        raise HTTPException(409, "ai_draft_requires_approval")
    before = question.status
    question.status = body.status
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="question.status_changed",
        entity_type="question",
        entity_id=question.id,
        before={"status": before},
        after={"status": body.status},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": {"id": question.id, "status": question.status}, "error": None}


@router.post("/{question_id}/approve")
async def approve_question(
    question_id: str,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    question = await _get_question(db, ctx.org_id, question_id)
    if question.status != "draft":
        raise HTTPException(409, "not_a_draft")
    question.status = "active"
    question.approved_by = ctx.user.id
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="question.approved",
        entity_type="question",
        entity_id=question.id,
        after={"approved_by": ctx.user.id},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": {"id": question.id, "status": "active"}, "error": None}


@router.delete("/{question_id}")
async def delete_question(
    question_id: str,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    question = await _get_question(db, ctx.org_id, question_id)
    # blocked when any version is pinned inside a frozen assessment version (FR: 409)
    pinned = (
        await db.execute(
            select(SectionQuestion)
            .join(QuestionVersion, QuestionVersion.id == SectionQuestion.question_version_id)
            .join(Section, Section.id == SectionQuestion.section_id)
            .join(AssessmentVersion, AssessmentVersion.id == Section.assessment_version_id)
            .where(
                QuestionVersion.question_id == question.id,
                AssessmentVersion.frozen.is_(True),
            )
        )
    ).first()
    if pinned:
        raise HTTPException(409, "pinned_in_frozen_version")
    question.deleted_at = now_utc()
    question.status = "archived"
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="question.deleted",
        entity_type="question",
        entity_id=question.id,
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {"data": {"id": question.id, "deleted": True}, "error": None}


class AIGenerateIn(BaseModel):
    prompt: str = Field(min_length=3)
    qtype: str = "mcq"
    count: int = Field(5, ge=1, le=30)
    difficulty: str = "medium"
    topic: str = "general"
    skills: list[str] = []


@router.post("/ai-generate", status_code=202)
async def ai_generate(
    body: AIGenerateIn,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    generation = AIGeneration(
        org_id=ctx.org_id,
        created_by=ctx.user.id,
        prompt=body.prompt,
        params=body.model_dump(),
    )
    db.add(generation)
    await db.commit()
    # inline job execution (research R16 dispatcher; ARQ worker in production)
    try:
        questions, model = ai_service.generate_questions(
            body.prompt, body.qtype, body.count, body.difficulty, body.topic, body.skills
        )
        created_ids = []
        for item in questions:
            question = Question(
                org_id=ctx.org_id,
                status="draft",  # FR-043: AI output is never immediately publishable
                source="ai",
                created_by=ctx.user.id,
                ai_generation_id=generation.id,
            )
            db.add(question)
            await db.flush()
            version = QuestionVersion(
                question_id=question.id,
                version=1,
                qtype=item.get("qtype", body.qtype),
                answer_type=item.get("answer_type", "single_choice"),
                difficulty=item.get("difficulty", body.difficulty),
                title=str(item.get("title", "Untitled"))[:300],
                body=str(item.get("body", "")),
                config=item.get("config") or {},
                topic=str(item.get("topic", body.topic)),
                skills=item.get("skills") or body.skills,
            )
            db.add(version)
            await db.flush()
            question.current_version_id = version.id
            created_ids.append(question.id)
        generation.status = "completed"
        generation.model = model
        await db.commit()
    except Exception as exc:  # AI failure must not 500 the admin panel
        log.warning("ai_generation_failed", error=str(exc))
        generation.status = "failed"
        generation.error = str(exc)
        await db.commit()
        created_ids = []
    return {
        "data": {
            "generation_id": generation.id,
            "status": generation.status,
            "question_ids": created_ids,
        },
        "error": None,
    }


@router.get("/ai-generations/{generation_id}")
async def get_generation(
    generation_id: str,
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    generation = (
        await db.execute(
            select(AIGeneration).where(
                AIGeneration.id == generation_id, AIGeneration.org_id == ctx.org_id
            )
        )
    ).scalar_one_or_none()
    if generation is None:
        raise HTTPException(404, "not_found")
    questions = (
        (
            await db.execute(
                select(Question).where(Question.ai_generation_id == generation.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "data": {
            "id": generation.id,
            "status": generation.status,
            "model": generation.model,
            "error": generation.error,
            "question_ids": [q.id for q in questions],
        },
        "error": None,
    }
