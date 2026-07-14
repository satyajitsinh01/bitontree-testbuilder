from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...models import AuditLog
from ..deps import AdminContext, require_roles

router = APIRouter(prefix="/admin/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    actor_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    ctx: AdminContext = Depends(require_roles("hr_admin")),
    db: AsyncSession = Depends(get_db),
):
    q = select(AuditLog).where(AuditLog.org_id == ctx.org_id)
    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if action:
        q = q.where(AuditLog.action == action)
    if date_from:
        q = q.where(AuditLog.created_at >= date_from)
    if date_to:
        q = q.where(AuditLog.created_at <= date_to)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        (
            await db.execute(
                q.order_by(AuditLog.created_at.desc()).offset((page - 1) * size).limit(size)
            )
        )
        .scalars()
        .all()
    )
    items = [
        {
            "id": r.id,
            "actor_type": r.actor_type,
            "actor_id": r.actor_id,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "before": r.before,
            "after": r.after,
            "created_at": r.created_at.isoformat(),
            "ip": r.ip,
        }
        for r in rows
    ]
    return {
        "data": {"items": items, "total": total, "page": page, "size": size},
        "error": None,
    }
