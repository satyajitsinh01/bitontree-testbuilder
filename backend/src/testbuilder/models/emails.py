from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, pk

EMAIL_KINDS = ("invitation", "reminder_24h", "reminder_1h", "resend", "credentials_update")
EMAIL_STATUSES = ("queued", "sent", "delivered", "bounced", "failed")


class EmailMessage(Base, TimestampMixin):
    __tablename__ = "email_messages"

    id: Mapped[str] = pk()
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    assignment_id: Mapped[str | None] = mapped_column(
        ForeignKey("test_assignments.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    to_email: Mapped[str] = mapped_column(String(320))
    resend_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
