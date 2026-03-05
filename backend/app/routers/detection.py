"""
Detection Router — Sprint 3
Endpoints:
  POST /workspaces/{id}/detect/file/{file_id}   — trigger detection on an ingested file
  GET  /workspaces/{id}/detect/stats            — detection stats for workspace
  GET  /workspaces/{id}/detect/categories       — asset count by category
"""
import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..services.detection_service import (
    process_ingested_file,
    get_detection_stats,
    get_category_breakdown,
)
from ..services.workspace_service import WorkspaceService
from ..services.file_service import FileService
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["detection"])


# ─── Background pipeline wrapper ─────────────────────────────────────────────

async def _run_detection_pipeline(
    workspace_slug: str,
    file_id: int,
    filename: str,
    content_bytes: bytes,
    db: AsyncSession,
) -> None:
    """Called in background to avoid blocking the HTTP response."""
    try:
        summary = await process_ingested_file(
            db=db,
            workspace_slug=workspace_slug,
            file_id=file_id,
            filename=filename,
            content_bytes=content_bytes,
            use_llm=True,
        )
        logger.info(f"Detection pipeline complete: {summary}")
    except Exception as e:
        logger.exception(f"Background detection failed: {e}")


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/detect/file/{file_id}")
async def trigger_file_detection(
    workspace_id: int,
    file_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger the detection pipeline on an already-uploaded file.
    Returns immediately; detection runs in the background.
    """
    # Validate workspace access
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")

    membership = await WorkspaceService.get_membership(db, workspace_id, current_user.id)
    if not membership and not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")

    if membership and membership.role == "viewer":
        raise HTTPException(status_code=403, detail="Viewers não podem iniciar detecção")

    # Fetch file from MinIO for re-processing
    file_service = FileService()
    try:
        file_info = await file_service.get_file_info(db, ws.slug, file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado")
        content_bytes = await file_service.download_file(ws.slug, file_info["storage_key"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar arquivo: {e}")

    # Audit
    await AuditService.log(
        db, ws.slug,
        user_id=current_user.id, user_email=current_user.email,
        action="detection_triggered",
        resource_type="ingestion_file", resource_id=str(file_id),
        detail={"filename": file_info["original_filename"]},
    )
    await db.commit()

    # Run detection in background
    background_tasks.add_task(
        _run_detection_pipeline,
        workspace_slug=ws.slug,
        file_id=file_id,
        filename=file_info["original_filename"],
        content_bytes=content_bytes,
        db=db,
    )

    return {
        "message": "Detecção iniciada em background",
        "file_id": file_id,
        "filename": file_info["original_filename"],
        "status": "processing",
    }


@router.post("/workspaces/{workspace_id}/detect/file/{file_id}/sync")
async def trigger_file_detection_sync(
    workspace_id: int,
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Synchronous version — waits for the pipeline to complete.
    Use for small files or testing. Not recommended for large logs.
    """
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")

    membership = await WorkspaceService.get_membership(db, workspace_id, current_user.id)
    if not membership and not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")

    file_service = FileService()
    try:
        file_info = await file_service.get_file_info(db, ws.slug, file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado")
        content_bytes = await file_service.download_file(ws.slug, file_info["storage_key"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar arquivo: {e}")

    summary = await process_ingested_file(
        db=db,
        workspace_slug=ws.slug,
        file_id=file_id,
        filename=file_info["original_filename"],
        content_bytes=content_bytes,
        use_llm=True,
    )

    await AuditService.log(
        db, ws.slug,
        user_id=current_user.id, user_email=current_user.email,
        action="detection_completed",
        resource_type="ingestion_file", resource_id=str(file_id),
        detail=summary,
    )
    await db.commit()

    return summary


@router.get("/workspaces/{workspace_id}/detect/stats")
async def get_workspace_detection_stats(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return high-level detection statistics for the workspace."""
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")

    membership = await WorkspaceService.get_membership(db, workspace_id, current_user.id)
    if not membership and not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")

    stats = await get_detection_stats(db, ws.slug)
    categories = await get_category_breakdown(db, ws.slug)
    return {
        "workspace_id": workspace_id,
        "workspace_name": ws.name,
        **stats,
        "category_breakdown": categories,
    }


@router.get("/workspaces/{workspace_id}/detect/categories")
async def get_asset_categories(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return assets grouped by category."""
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")

    membership = await WorkspaceService.get_membership(db, workspace_id, current_user.id)
    if not membership and not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return await get_category_breakdown(db, ws.slug)
