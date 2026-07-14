from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, pk

QTYPES = ("mcq", "text", "coding")
DIFFICULTIES = ("easy", "medium", "hard")
QUESTION_STATUSES = ("draft", "active", "inactive", "archived")
QUESTION_SOURCES = ("manual", "ai", "import")


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[str] = pk()
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ai_generation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuestionVersion(Base, TimestampMixin):
    __tablename__ = "question_versions"
    __table_args__ = (UniqueConstraint("question_id", "version"),)

    id: Mapped[str] = pk()
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    qtype: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(100), default="general")
    answer_type: Mapped[str] = mapped_column(String(30))
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    topic: Mapped[str] = mapped_column(String(100), default="")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    expected_duration_sec: Mapped[int] = mapped_column(Integer, default=120)
    language: Mapped[str] = mapped_column(String(10), default="en")
    tags: Mapped[list] = mapped_column(JSON, default=list)


class AIGeneration(Base, TimestampMixin):
    __tablename__ = "ai_generations"

    id: Mapped[str] = pk()
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    created_by: Mapped[str] = mapped_column(String(36))
    prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_response_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|completed|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class QuestionQualityFlag(Base, TimestampMixin):
    __tablename__ = "question_quality_flags"

    id: Mapped[str] = pk()
    question_version_id: Mapped[str] = mapped_column(
        ForeignKey("question_versions.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
