from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, pk

ASSIGNMENT_STATUSES = (
    "invited",
    "not_started",
    "in_progress",
    "completed",
    "expired",
    "removed",
)


class Candidate(Base, TimestampMixin):
    __tablename__ = "candidates"
    __table_args__ = (UniqueConstraint("org_id", "email"),)

    id: Mapped[str] = pk()
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))  # stored lowercase
    phone: Mapped[str] = mapped_column(String(30), default="")


class TestAssignment(Base, TimestampMixin):
    __tablename__ = "test_assignments"
    __table_args__ = (UniqueConstraint("assessment_id", "candidate_id"),)

    id: Mapped[str] = pk()
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    window_start_at: Mapped[datetime] = mapped_column(DateTime)
    window_end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="not_started", index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    credentials_expired: Mapped[bool] = mapped_column(Boolean, default=False)
    send_email: Mapped[bool] = mapped_column(Boolean, default=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ImportBatch(Base, TimestampMixin):
    __tablename__ = "import_batches"

    id: Mapped[str] = pk()
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), index=True)
    uploaded_by: Mapped[str] = mapped_column(String(36))
    file_ref: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="processing")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
