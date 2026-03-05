from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Any
from ..core.tenant import get_schema_name

class AuditService:

    @staticmethod
    async def log(
        db: AsyncSession,
        workspace_slug: str,
        action: str,
        user_id: int | None = None,
        user_email: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> None:
        schema = get_schema_name(workspace_slug)
        await db.execute(
            text(f"""
                INSERT INTO "{schema}".audit_logs
                  (user_id, user_email, action, resource_type, resource_id, detail, ip_address)
                VALUES (:uid, :uemail, :action, :rtype, :rid, :detail::jsonb, :ip)
            """),
            {
                "uid": user_id,
                "uemail": user_email,
                "action": action,
                "rtype": resource_type,
                "rid": str(resource_id) if resource_id else None,
                "detail": __import__("json").dumps(detail) if detail else None,
                "ip": ip_address,
            }
        )

    @staticmethod
    async def list_logs(db: AsyncSession, workspace_slug: str, limit: int = 100) -> list[dict]:
        schema = get_schema_name(workspace_slug)
        result = await db.execute(
            text(f"""
                SELECT id, user_id, user_email, action, resource_type, resource_id,
                       detail, ip_address, created_at
                FROM "{schema}".audit_logs
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit}
        )
        return [dict(row) for row in result.mappings().all()]
