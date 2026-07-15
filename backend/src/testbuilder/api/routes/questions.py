import json

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
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
from ...services import harness
from ...services.audit import write_audit
from ...services.quality import (
    DUPLICATE_THRESHOLD,
    find_duplicates,
    similarity,
    structural_errors,
)
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
    if body.qtype == "coding" and body.config.get("signature"):
        body.config = harness.autofill_coding_config(body.config)
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


# Canonical JSON import format ("perfect format"): a top-level {"questions": [...]}
# array. Per item: qtype + title + config are required; everything else defaults.
IMPORT_TEMPLATE = {
    "questions": [
        {
            "qtype": "mcq",
            "title": "Which HTTP method is idempotent?",
            "body": "Choose the best answer.",
            "difficulty": "easy",
            "category": "Web",
            "topic": "http",
            "skills": ["backend"],
            "tags": ["http", "rest"],
            "expected_duration_sec": 60,
            "answer_type": "single_choice",
            "config": {
                "options": [
                    {"id": "a", "text": "PUT"},
                    {"id": "b", "text": "POST"},
                    {"id": "c", "text": "PATCH"},
                ],
                "correct_option_ids": ["a"],
            },
        },
        {
            "qtype": "mcq",
            "title": "Select ALL valid HTTP success codes",
            "difficulty": "medium",
            "answer_type": "multi_choice",
            "config": {
                "options": [
                    {"id": "a", "text": "200"},
                    {"id": "b", "text": "201"},
                    {"id": "c", "text": "404"},
                    {"id": "d", "text": "204"},
                    {"id": "e", "text": "500"},
                ],
                "correct_option_ids": ["a", "b", "d"],
            },
        },
        {
            "qtype": "text",
            "title": "Explain database indexing",
            "difficulty": "medium",
            "answer_type": "long_text",
            "config": {
                "rubric": "Mentions B-tree structure, read speedup, write cost",
                "expected_answer": "Indexes are auxiliary structures that speed up lookups...",
            },
        },
        {
            "qtype": "coding",
            "title": "Two Sum",
            "difficulty": "easy",
            "category": "Algorithms",
            "topic": "arrays",
            "tags": ["array", "hash-table"],
            "answer_type": "code",
            "config": {
                # starter_code is generated from the signature — you may omit it.
                "signature": {
                    "function_name": "twoSum",
                    "params": [
                        {"name": "nums", "type": "int[]"},
                        {"name": "target", "type": "int"},
                    ],
                    "return_type": "int[]",
                },
                "allowed_languages": ["python", "javascript", "java", "cpp"],
                "description": (
                    "Given an array of integers `nums` and an integer `target`, "
                    "return the **indices** of the two numbers such that they add up "
                    "to `target`.\n\nYou may assume that each input has *exactly one* "
                    "solution, and you may not use the same element twice."
                ),
                "input_format": "- `nums`: array of integers\n- `target`: integer",
                "output_format": "An array `[i, j]` of the two indices (`i < j`).",
                "constraints": (
                    "- `2 <= nums.length <= 10^4`\n"
                    "- `-10^9 <= nums[i], target <= 10^9`\n"
                    "- Exactly one valid answer exists."
                ),
                "notes": "Try to solve it in **O(n)** time with a hash map.",
                "examples": [
                    {
                        "input": "nums = [2,7,11,15], target = 9",
                        "output": "[0,1]",
                        "explanation": "`nums[0] + nums[1] == 9`, so return `[0, 1]`.",
                    },
                    {
                        "input": "nums = [3,2,4], target = 6",
                        "output": "[1,2]",
                        "explanation": "`nums[1] + nums[2] == 6`.",
                    },
                ],
                "test_cases": [
                    {"id": "s1", "args": [[2, 7, 11, 15], 9], "expected": [0, 1],
                     "is_hidden": False, "weight": 1},
                    {"id": "s2", "args": [[3, 2, 4], 6], "expected": [1, 2],
                     "is_hidden": False, "weight": 1},
                    {"id": "h1", "args": [[3, 3], 6], "expected": [0, 1],
                     "is_hidden": True, "weight": 1},
                    {"id": "h2", "args": [[0, 4, 3, 0], 0], "expected": [0, 3],
                     "is_hidden": True, "weight": 1},
                    {"id": "h3", "args": [[-1, -2, -3, -4], -6], "expected": [1, 3],
                     "is_hidden": True, "weight": 1},
                ],
                "time_limit_ms": 5000,
                "memory_limit_kb": 256000,
                "show_case_results": "visible_only",
            },
        },
    ]
}

DEFAULT_ANSWER_TYPE = {"mcq": "single_choice", "text": "long_text", "coding": "code"}


@router.get("/import-template")
async def import_template(
    ctx: AdminContext = Depends(require_roles("test_creator")),
):
    return {"data": IMPORT_TEMPLATE, "error": None}


@router.post("/import", status_code=202)
async def import_questions(
    file: UploadFile = File(...),
    ctx: AdminContext = Depends(require_roles("test_creator")),
    db: AsyncSession = Depends(get_db),
):
    """Bulk import from a .json file. Every valid item lands as a draft
    (source=import) that must be approved before use, mirroring the AI flow."""
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(422, "file_too_large")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            422, {"code": "invalid_json", "details": [str(exc)]}
        ) from None
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise HTTPException(
            422,
            {"code": "invalid_format",
             "details": ['expected {"questions": [...]} — download the template']},
        )
    created_ids: list[str] = []
    errors: list[dict] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append({"index": index, "error": "item must be an object"})
            continue
        qtype = item.get("qtype")
        title = str(item.get("title") or "").strip()
        config = item.get("config") or {}
        difficulty = item.get("difficulty", "medium")
        problems: list[str] = []
        if qtype not in QTYPES:
            problems.append(f"qtype must be one of {QTYPES}")
        if len(title) < 3:
            problems.append("title is required (min 3 chars)")
        if difficulty not in DIFFICULTIES:
            problems.append(f"difficulty must be one of {DIFFICULTIES}")
        if qtype == "coding" and config.get("signature"):
            config = harness.autofill_coding_config(config)
        if qtype in QTYPES:
            problems.extend(structural_errors(qtype, config))
        if problems:
            errors.append({"index": index, "title": title, "error": "; ".join(problems)})
            continue
        question = Question(
            org_id=ctx.org_id, status="draft", source="import", created_by=ctx.user.id
        )
        db.add(question)
        await db.flush()
        version = QuestionVersion(
            question_id=question.id,
            version=1,
            qtype=qtype,
            answer_type=item.get("answer_type", DEFAULT_ANSWER_TYPE[qtype]),
            category=str(item.get("category", "general")),
            difficulty=difficulty,
            title=title[:300],
            body=str(item.get("body", "")),
            config=config,
            topic=str(item.get("topic", "")),
            skills=item.get("skills") or [],
            expected_duration_sec=int(item.get("expected_duration_sec", 120)),
            tags=item.get("tags") or [],
        )
        db.add(version)
        await db.flush()
        question.current_version_id = version.id
        created_ids.append(question.id)
    await write_audit(
        db,
        org_id=ctx.org_id,
        actor_type="user",
        actor_id=ctx.user.id,
        action="question.bulk_imported",
        entity_type="question_bank",
        entity_id=ctx.org_id,
        after={"imported": len(created_ids), "failed": len(errors)},
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    await db.commit()
    return {
        "data": {
            "imported": len(created_ids),
            "failed": len(errors),
            "errors": errors,
            "question_ids": created_ids,
        },
        "error": None,
    }


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
    if body.qtype == "coding" and body.config.get("signature"):
        body.config = harness.autofill_coding_config(body.config)
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

    @field_validator("difficulty")
    @classmethod
    def difficulty_valid(cls, v: str) -> str:
        if v not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}")
        return v

    @field_validator("qtype")
    @classmethod
    def qtype_valid(cls, v: str) -> str:
        if v not in QTYPES:
            raise ValueError(f"qtype must be one of {QTYPES}")
        return v


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
    # existing bank titles feed the prompt so the model avoids repeats
    existing_titles = [
        version.title
        for version in (
            await db.execute(
                select(QuestionVersion)
                .join(Question, Question.current_version_id == QuestionVersion.id)
                .where(
                    Question.org_id == ctx.org_id,
                    Question.status.in_(("active", "draft")),
                    Question.deleted_at.is_(None),
                )
                .order_by(QuestionVersion.created_at.desc())
                .limit(60)
            )
        ).scalars()
    ]
    # inline job execution (research R16 dispatcher; ARQ worker in production)
    skipped_duplicates = 0
    try:
        questions, model = ai_service.generate_questions(
            body.prompt, body.qtype, body.count, body.difficulty, body.topic, body.skills,
            avoid_titles=existing_titles,
        )
        created_ids = []
        batch_titles: list[str] = []
        for item in questions:
            item_title = str(item.get("title", ""))
            # title-based dedupe: near-identical titles mean a repeated question,
            # while distinct questions on one topic still differ in their titles
            is_duplicate = any(
                similarity(item_title, seen) >= DUPLICATE_THRESHOLD
                for seen in (*existing_titles, *batch_titles)
            )
            if is_duplicate:
                skipped_duplicates += 1
                continue
            batch_titles.append(item_title)
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
                config=harness.autofill_coding_config(item.get("config") or {})
                if item.get("qtype", body.qtype) == "coding"
                else (item.get("config") or {}),
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
            "skipped_duplicates": skipped_duplicates,
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
