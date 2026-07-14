from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, pk

SUBMISSION_STATUSES = (
    "queued",
    "running",
    "completed",
    "compile_error",
    "runtime_error",
    "timeout",
    "failed",
)
SUPPORTED_LANGUAGES = ("javascript", "python", "java", "cpp", "c")


class CodeSubmission(Base, TimestampMixin):
    __tablename__ = "code_submissions"

    id: Mapped[str] = pk()
    session_question_id: Mapped[str] = mapped_column(
        ForeignKey("session_questions.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))  # run | submit
    language: Mapped[str] = mapped_column(String(20))
    source_code: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    judge0_tokens: Mapped[list] = mapped_column(JSON, default=list)
    results: Mapped[list] = mapped_column(JSON, default=list)
    exec_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    memory_kb: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
