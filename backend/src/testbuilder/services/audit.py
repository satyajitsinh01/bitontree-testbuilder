from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    org_id: str,
    actor_type: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict | None = None,
    after: dict | None = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Append an audit record inside the caller's transaction (Constitution II).

    The row commits or rolls back atomically with the mutation it describes.
    """
    entry = AuditLog(
        org_id=org_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        request_id=request_id,
        ip=ip,
    )
    db.add(entry)
    return entry
