import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ...db import session_factory
from ...models import ExamSession, SessionSection, TestAssignment
from ...models.base import now_utc
from ...security import decode_token
from ...services.sessions import enforce_deadlines

router = APIRouter(tags=["exam-timer"])


@router.websocket("/exam/timer")
async def exam_timer(websocket: WebSocket, token: str) -> None:
    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=4401)
        return
    if payload.get("typ") != "assignment":
        await websocket.close(code=4403)
        return
    await websocket.accept()
    try:
        while True:
            async with session_factory()() as db:
                assignment = (
                    await db.execute(
                        select(TestAssignment).where(TestAssignment.id == payload["sub"])
                    )
                ).scalar_one_or_none()
                session = (
                    await db.execute(
                        select(ExamSession)
                        .where(ExamSession.assignment_id == payload["sub"])
                        .order_by(ExamSession.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if assignment is None or session is None:
                    await websocket.send_json({"status": "no_session"})
                    await websocket.close(code=4404)
                    return
                if session.status == "active":
                    await enforce_deadlines(db, session)
                active = (
                    await db.execute(
                        select(SessionSection).where(
                            SessionSection.session_id == session.id,
                            SessionSection.status == "active",
                        )
                    )
                ).scalar_one_or_none()
                now = now_utc()
                remaining = 0
                if active is not None and active.deadline_at is not None:
                    remaining = max(0, int((active.deadline_at - now).total_seconds()))
                await db.commit()
                await websocket.send_json(
                    {
                        "status": session.status,
                        "current_section_id": session.current_section_id,
                        "remaining_seconds": remaining,
                        "server_now": now.isoformat(),
                    }
                )
                if session.status != "active":
                    await websocket.close(code=1000)
                    return
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return

