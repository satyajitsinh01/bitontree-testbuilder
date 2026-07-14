from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, pk

EVAL_METHODS = ("auto_mcq", "auto_code", "ai_text", "manual")


class Evaluation(Base, TimestampMixin):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("session_question_id"),)

    id: Mapped[str] = pk()
    session_question_id: Mapped[str] = mapped_column(ForeignKey("session_questions.id"))
    method: Mapped[str] = mapped_column(String(20))
    auto_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float] = mapped_column(Float, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, default=0.0)
    overridden_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Report(Base, TimestampMixin):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("session_id"),)

    id: Mapped[str] = pk()
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"))
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    overall_max: Mapped[float] = mapped_column(Float, default=0.0)
    section_scores: Mapped[list] = mapped_column(JSON, default=list)
    ai_observations: Mapped[str] = mapped_column(Text, default="")
    red_flag_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_review")
    pdf_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
