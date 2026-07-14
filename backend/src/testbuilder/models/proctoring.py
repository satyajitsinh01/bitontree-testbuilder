from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, now_utc, pk

CLIENT_EVENT_KINDS = (
    "tab_switch",
    "window_blur",
    "fullscreen_exit",
    "copy_attempt",
    "paste_attempt",
    "camera_lost",
    "mic_lost",
    "capture_failed",
    "devtools_open",
    "multi_display",
)
AI_EVENT_KINDS = ("face_missing", "multiple_faces", "gaze_away", "object_detected")
SEVERITIES = ("info", "warning", "red_flag")


class ProctoringEvent(Base):
    __tablename__ = "proctoring_events"

    id: Mapped[str] = pk()
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10), default="info")
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ProctoringEvidence(Base, TimestampMixin):
    __tablename__ = "proctoring_evidence"

    id: Mapped[str] = pk()
    session_id: Mapped[str] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="screenshot")
    object_key: Mapped[str] = mapped_column(String(300))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
