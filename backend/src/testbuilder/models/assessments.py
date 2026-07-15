from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, pk


class Assessment(Base, TimestampMixin):
    __tablename__ = "assessments"

    id: Mapped[str] = pk()
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    window_start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    window_end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|published|archived
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class AssessmentVersion(Base, TimestampMixin):
    __tablename__ = "assessment_versions"
    __table_args__ = (UniqueConstraint("assessment_id", "version"),)

    id: Mapped[str] = pk()
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    total_duration_min: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Section(Base, TimestampMixin):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("assessment_version_id", "order_index"),)

    id: Mapped[str] = pk()
    assessment_version_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_versions.id"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    duration_min: Mapped[int] = mapped_column(Integer, default=10)
    weightage_pct: Mapped[float] = mapped_column(Float, default=0.0)
    allowed_qtypes: Mapped[list] = mapped_column(JSON, default=list)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    navigation: Mapped[str] = mapped_column(String(20), default="free")
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)


class SectionQuestion(Base):
    __tablename__ = "section_questions"

    id: Mapped[str] = pk()
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"), index=True)
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"))
    pool_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    points: Mapped[float] = mapped_column(Float, default=1.0)


class SectionPoolRule(Base):
    __tablename__ = "section_pool_rules"

    id: Mapped[str] = pk()
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"), index=True)
    pool_group: Mapped[str] = mapped_column(String(50))
    select_count: Mapped[int] = mapped_column(Integer, default=1)
