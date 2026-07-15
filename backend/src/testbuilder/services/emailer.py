"""Email delivery. Transport priority: SMTP (TB_SMTP_HOST set) > Resend
(TB_RESEND_API_KEY set) > console logging, so dev/test flows never break."""

import asyncio
import smtplib
from email.message import EmailMessage as MimeMessage
from email.utils import parseaddr

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import IST, get_settings
from ..models import Candidate, EmailMessage, TestAssignment
from ..models.base import now_utc

log = structlog.get_logger()

RESEND_API = "https://api.resend.com/emails"


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
            "You must share your entire screen; screenshots are taken on violations.",
            "The exam runs in full screen; leaving full screen is recorded.",
            "Switching to any other app, tab or window is recorded as a red flag.",
            "Developer tools, right-click, copy/paste and screenshots are disabled; "
            "attempts are recorded as red flags.",
            "Keep the browser window at its starting size; shrinking it is flagged.",
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


def _smtp_from_address(settings) -> tuple[str, str]:
    """Returns (display_name, address). Gmail rewrites the From header to the
    authenticated account, so for Gmail we send as the SMTP username directly —
    anything else risks DMARC failure or silent rewriting."""
    display, address = parseaddr(settings.email_from)
    if not address:
        address = settings.smtp_username
    if "gmail" in settings.smtp_host.lower():
        address = settings.smtp_username
    return display or "TestBuilder", address


def _smtp_send_sync(settings, to_email: str, subject: str, text_body: str) -> None:
    """Blocking SMTP send; run via asyncio.to_thread. Raises on failure."""
    display, from_address = _smtp_from_address(settings)
    mime = MimeMessage()
    mime["From"] = f"{display} <{from_address}>"
    mime["To"] = to_email
    mime["Subject"] = subject
    mime.set_content(text_body)

    if settings.smtp_use_ssl:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
    try:
        server.ehlo()
        if settings.smtp_use_tls and not settings.smtp_use_ssl:
            server.starttls()
            server.ehlo()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(mime, from_addr=from_address, to_addrs=[to_email])
    finally:
        server.quit()


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

    if settings.smtp_host:
        try:
            await asyncio.to_thread(_smtp_send_sync, settings, candidate.email,
                                    subject, body)
            message.status = "sent"
            message.sent_at = now_utc()
        except (smtplib.SMTPException, OSError) as exc:
            message.status = "failed"
            log.warning("email_smtp_error", error=str(exc), to=candidate.email)
        return message

    if not settings.resend_api_key:
        log.info("email_console_transport", to=candidate.email, subject=subject)
        message.status = "sent"
        message.sent_at = now_utc()
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
