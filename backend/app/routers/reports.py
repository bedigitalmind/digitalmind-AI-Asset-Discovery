"""
Reports Router — Sprint 4
Endpoints:
  POST /workspaces/{id}/reports           — create & trigger report generation
  GET  /workspaces/{id}/reports           — list reports for workspace
  GET  /workspaces/{id}/reports/{rid}     — get report status/metadata
  GET  /workspaces/{id}/reports/{rid}/download — get presigned download URL
  DELETE /workspaces/{id}/reports/{rid}   — delete a report
"""
import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..core.database import get_db
from ..core.security import get_current_user
from ..core.tenant import get_schema_name
from ..models.user import User
from ..services.workspace_service import WorkspaceService
from ..services.audit_service import AuditService
from ..services.report_service import (
    generate_report,
    list_reports,
    get_report_download_url,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reports"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CreateReportRequest(BaseModel):
    title: str = ""
    report_type: str = "full_discovery"  # full_discovery | executive_summary | shadow_ai_only


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_ws_and_check_access(
    db: AsyncSession,
    workspace_id: int,
    current_user: User,
    min_role: str = "analyst",
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")

    membership = await WorkspaceService.get_membership(db, workspace_id, current_user.id)
    if not membership and not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")

    if membership and min_role == "analyst" and membership.role == "viewer":
        raise HTTPException(status_code=403, detail="Viewers não podem gerar relatórios")

    return ws, membership


async def _create_report_record(
    db: AsyncSession,
    schema: str,
    title: str,
    report_type: str,
    user_id: int,
    user_email: str,
) -> int:
    result = await db.execute(text(f"""
        INSERT INTO "{schema}".reports
            (title, report_type, format, status, generated_by_id, generated_by_email)
        VALUES (:title, :report_type, 'pdf', 'generating', :uid, :email)
        RETURNING id
    """), {
        "title": title, "report_type": report_type,
        "uid": user_id, "email": user_email,
    })
    await db.commit()
    return result.scalar_one()


# ─── Background wrapper ───────────────────────────────────────────────────────

async def _bg_generate(
    workspace_slug: str,
    workspace_name: str,
    report_id: int,
    title: str,
    db: AsyncSession,
) -> None:
    try:
        await generate_report(db, workspace_slug, workspace_name, report_id, title)
    except Exception as e:
        logger.exception(f"Background report generation failed: {e}")


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/reports", status_code=202)
async def create_report(
    workspace_id: int,
    body: CreateReportRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger generation of a new discovery report.
    Returns immediately (202 Accepted); generation runs in background.
    """
    ws, _ = await _get_ws_and_check_access(db, workspace_id, current_user)
    schema = get_schema_name(ws.slug)

    title = body.title.strip() or f"AI Discovery Report — {ws.name}"
    report_id = await _create_report_record(
        db, schema, title, body.report_type,
        current_user.id, current_user.email,
    )

    await AuditService.log(
        db, ws.slug,
        user_id=current_user.id, user_email=current_user.email,
        action="report_generation_triggered",
        resource_type="report", resource_id=str(report_id),
        detail={"title": title, "report_type": body.report_type},
    )
    await db.commit()

    background_tasks.add_task(
        _bg_generate,
        workspace_slug=ws.slug,
        workspace_name=ws.name,
        report_id=report_id,
        title=title,
        db=db,
    )

    return {
        "report_id": report_id,
        "title": title,
        "status": "generating",
        "message": "Relatório sendo gerado em background. Atualize em alguns segundos.",
    }


@router.get("/workspaces/{workspace_id}/reports")
async def list_workspace_reports(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all reports for the workspace."""
    ws, _ = await _get_ws_and_check_access(db, workspace_id, current_user, min_role="viewer")
    reports = await list_reports(db, ws.slug)

    # Serialize datetime fields
    for r in reports:
        for k in ("created_at", "updated_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
        if r.get("snapshot") and isinstance(r["snapshot"], str):
            import json
            try:
                r["snapshot"] = json.loads(r["snapshot"])
            except Exception:
                pass

    return {"total": len(reports), "items": reports}


@router.get("/workspaces/{workspace_id}/reports/{report_id}")
async def get_report(
    workspace_id: int,
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get status and metadata for a specific report."""
    ws, _ = await _get_ws_and_check_access(db, workspace_id, current_user, min_role="viewer")
    schema = get_schema_name(ws.slug)

    result = await db.execute(text(f"""
        SELECT id, title, report_type, format, status, file_size,
               generated_by_email, snapshot, error_message, created_at, updated_at
        FROM "{schema}".reports WHERE id = :id
    """), {"id": report_id})
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")

    r = dict(row)
    for k in ("created_at", "updated_at"):
        if r.get(k) and hasattr(r[k], "isoformat"):
            r[k] = r[k].isoformat()
    return r


@router.get("/workspaces/{workspace_id}/reports/{report_id}/download")
async def download_report(
    workspace_id: int,
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a presigned download URL for a ready report (valid 1 hour)."""
    ws, _ = await _get_ws_and_check_access(db, workspace_id, current_user, min_role="viewer")

    result = await get_report_download_url(db, ws.slug, report_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Relatório não encontrado ou ainda não está pronto"
        )

    url, filename = result
    await AuditService.log(
        db, ws.slug,
        user_id=current_user.id, user_email=current_user.email,
        action="report_downloaded",
        resource_type="report", resource_id=str(report_id),
    )
    await db.commit()

    return {"download_url": url, "filename": filename, "expires_in_seconds": 3600}


@router.delete("/workspaces/{workspace_id}/reports/{report_id}", status_code=204)
async def delete_report(
    workspace_id: int,
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a report record (and remove from storage if possible)."""
    ws, membership = await _get_ws_and_check_access(db, workspace_id, current_user)
    if membership and membership.role not in ("admin",) and not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Apenas admins podem excluir relatórios")

    schema = get_schema_name(ws.slug)
    result = await db.execute(text(f"""
        SELECT storage_key FROM "{schema}".reports WHERE id = :id
    """), {"id": report_id})
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")

    # Try to remove from storage
    if row["storage_key"]:
        from ..services.file_service import get_s3_client, get_bucket_name
        try:
            s3 = get_s3_client()
            s3.delete_object(Bucket=get_bucket_name(ws.slug), Key=row["storage_key"])
        except Exception:
            pass

    await db.execute(text(f'DELETE FROM "{schema}".reports WHERE id = :id'), {"id": report_id})
    await AuditService.log(
        db, ws.slug,
        user_id=current_user.id, user_email=current_user.email,
        action="report_deleted", resource_type="report", resource_id=str(report_id),
    )
    await db.commit()
