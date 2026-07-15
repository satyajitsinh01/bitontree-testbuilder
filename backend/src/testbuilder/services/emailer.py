"""Email delivery via Resend, SMTP, or a local console transport."""

import asyncio
import smtplib
from email.message import EmailMessage as SMTPMessage

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import IST, get_settings
from ..models import Candidate, EmailMessage, TestAssignment
from ..models.base import now_utc

log = structlog.get_logger()

RESEND_API = "https://api.resend.com/emails"


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = SMTPMessage()
    message["From"] = settings.email_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_use_tls and not settings.smtp_use_ssl:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def _invitation_payload(
    assignment: TestAssignment, candidate: Candidate, password: str | None, title: str
) -> dict:
    settings = get_settings()
    start_ist = assignment.window_start_at.replace(tzinfo=None)
    end_ist = assignment.window_end_at.replace(tzinfo=None)
    return {
        "assessment_title": title,
        "candidate_name": candidate.full_name,
        "login_url": f"{settings.frontend_base_url}/login",
        "login_email": candidate.email,
        "password": password,  # None on resends (credentials already delivered)
        "window_start_ist": start_ist.isoformat() + " (IST is server time reference)",
        "window_end_ist": end_ist.isoformat(),
        "rules": [
            "Camera and microphone access is required for the entire exam.",
            "The exam runs in full screen; leaving full screen is recorded.",
            "Tab switches, window changes and copy/paste attempts are recorded.",
            "Each section is timed and auto-submits when time expires.",
        ],
        "system_requirements": [
            "Latest Chrome or Edge browser",
            "Webcam + microphone",
            "Stable internet connection (>= 1 Mbps)",
        ],
    }


def _render_text(kind: str, payload: dict) -> str:
    lines = [
        f"Hello {payload.get('candidate_name', '')},",
        "",
        f"You are invited to the assessment: {payload.get('assessment_title', '')}",
        f"Sign in at: {payload.get('login_url', '')}",
        f"Email: {payload.get('login_email', '')}",
    ]
    if payload.get("password"):
        lines.append(f"Password: {payload['password']}")
    else:
        lines.append("Password: use the password from your most recent invitation email")
    lines += [
        f"Window (IST): {payload.get('window_start_ist')} -> {payload.get('window_end_ist')}",
        "",
        "Rules:",
        *[f"- {r}" for r in payload.get("rules", [])],
        "",
        "System requirements:",
        *[f"- {r}" for r in payload.get("system_requirements", [])],
    ]
    return "\n".join(lines)


async def send_email(
    db: AsyncSession,
    *,
    org_id: str,
    assignment: TestAssignment,
    candidate: Candidate,
    kind: str,
    payload: dict,
) -> EmailMessage:
    settings = get_settings()
    message = EmailMessage(
        org_id=org_id,
        assignment_id=assignment.id,
        kind=kind,
        to_email=candidate.email,
        payload={k: v for k, v in payload.items() if k != "password"},
    )
    db.add(message)
    subject = f"[TestBuilder] {payload.get('assessment_title', 'Assessment')} — {kind}"
    body = _render_text(kind, payload)
    if not settings.resend_api_key and not settings.smtp_host:
        log.info("email_console_transport", to=candidate.email, subject=subject)
        message.status = "sent"
        message.sent_at = now_utc()
        return message
    if not settings.resend_api_key:
        try:
            await asyncio.to_thread(_send_smtp, candidate.email, subject, body)
            message.status = "sent"
            message.sent_at = now_utc()
        except (OSError, smtplib.SMTPException) as exc:
            message.status = "failed"
            log.warning("smtp_send_error", error=str(exc))
        return message
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                RESEND_API,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [candidate.email],
                    "subject": subject,
                    "text": body,
                },
            )
        if response.status_code < 300:
            message.status = "sent"
            message.sent_at = now_utc()
            message.resend_message_id = response.json().get("id")
        else:
            message.status = "failed"
            log.warning("email_send_failed", status=response.status_code)
    except httpx.HTTPError as exc:
        message.status = "failed"
        log.warning("email_send_error", error=str(exc))
    return message


async def send_invitation(
    db: AsyncSession,
    *,
    org_id: str,
    assignment: TestAssignment,
    candidate: Candidate,
    assessment_title: str,
    password: str | None,
    kind: str = "invitation",
) -> EmailMessage:
    payload = _invitation_payload(assignment, candidate, password, assessment_title)
    return await send_email(
        db,
        org_id=org_id,
        assignment=assignment,
        candidate=candidate,
        kind=kind,
        payload=payload,
    )


def ist_display(dt) -> str:
    return dt.replace(tzinfo=None).astimezone(IST).isoformat() if dt.tzinfo else dt.isoformat()
