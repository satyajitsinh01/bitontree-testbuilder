from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, now_utc, pk

SESSION_STATUSES = ("active", "submitted", "auto_submitted", "terminated", "abandoned")
SECTION_STATUSES = ("locked", "active", "submitted", "auto_submitted")
QUESTION_STATES = ("unseen", "seen", "answered", "marked_review")
CHECKPOINT_KINDS = (
    "autosave",
    "next_question",
    "run_code",
    "submit_code",
    "section_submit",
    "final_submit",
)


class ExamSession(Base, TimestampMixin):
    __tablename__ = "exam_sessions"
    # One active session per assignment (FR-023): partial unique index, works on
    # both SQLite and PostgreSQL.
    __table_args__ = (
        Index(
            "uq_exam_sessions_one_active",
            "assignment_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = pk()
    assignment_id: Mapped[str] = mapped_column(ForeignKey("test_assignments.id"), index=True)
    assessment_version_id: Mapped[str] = mapped_column(ForeignKey("assessment_versions.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    current_section_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_admin: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # heartbeat for concurrent-login rejection (research R2 TTL analogue)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class SessionSection(Base):
    __tablename__ = "session_sections"
    __table_args__ = (UniqueConstraint("session_id", "section_id"),)

    id: Mapped[str] = pk()
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="locked")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    time_spent_sec: Mapped[int] = mapped_column(Integer, default=0)


class SessionQuestion(Base):
    __tablename__ = "session_questions"

    id: Mapped[str] = pk()
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"), index=True)
    question_version_id: Mapped[str] = mapped_column(ForeignKey("question_versions.id"))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    option_order: Mapped[list | None] = mapped_column(JSON, nullable=True)
    points: Mapped[float] = mapped_column(Float, default=1.0)
    state: Mapped[str] = mapped_column(String(20), default="unseen")


class Answer(Base, TimestampMixin):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("session_id", "session_question_id"),)

    id: Mapped[str] = pk()
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    session_question_id: Mapped[str] = mapped_column(ForeignKey("session_questions.id"))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class AnswerCheckpoint(Base):
    __tablename__ = "answer_checkpoints"

    id: Mapped[str] = pk()
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    code_submission_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
