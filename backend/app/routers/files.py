from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..services.file_service import FileService
from ..services.workspace_service import WorkspaceService
from ..services.audit_service import AuditService

router = APIRouter(tags=["Arquivos"])

@router.post("/workspaces/{workspace_id}/files", status_code=201)
async def upload_file(
    workspace_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")

    allowed_extensions = {
        "csv", "json", "xml", "txt", "log", "zip", "gz",
        "parquet", "ndjson", "jsonl"
    }
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=415,
            detail=f"Tipo de arquivo não suportado. Permitidos: {', '.join(sorted(allowed_extensions))}"
        )

    record = await FileService.upload_file(
        db=db,
        workspace_slug=ws.slug,
        file=file,
        uploaded_by_id=current_user.id,
        uploaded_by_email=current_user.email,
    )

    await AuditService.log(
        db=db,
        workspace_slug=ws.slug,
        action="file.upload",
        user_id=current_user.id,
        user_email=current_user.email,
        resource_type="ingestion_file",
        resource_id=str(record["id"]),
        detail={"filename": record["original_filename"], "size": record["file_size"]},
    )

    return record

@router.get("/workspaces/{workspace_id}/files")
async def list_files(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    files = await FileService.list_files(db, ws.slug)
    return {"total": len(files), "items": files}

@router.delete("/workspaces/{workspace_id}/files/{file_id}", status_code=204)
async def delete_file(
    workspace_id: int,
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    await FileService.delete_file(db, ws.slug, file_id)
    await AuditService.log(
        db=db,
        workspace_slug=ws.slug,
        action="file.delete",
        user_id=current_user.id,
        user_email=current_user.email,
        resource_type="ingestion_file",
        resource_id=str(file_id),
    )

@router.get("/workspaces/{workspace_id}/audit-logs")
async def list_audit_logs(
    workspace_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    from ..services.audit_service import AuditService
    logs = await AuditService.list_logs(db, ws.slug, limit=limit)
    return {"total": len(logs), "items": logs}
