from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..services.connector_service import ConnectorService
from ..services.workspace_service import WorkspaceService
from ..services.audit_service import AuditService

router = APIRouter(tags=["Conectores & Assets"])


class ConnectorCreate(BaseModel):
    name: str
    connector_type: str = "cloud"
    platform: str  # azure, aws, gcp
    config: dict   # credentials — encrypted at rest


class AssetUpdate(BaseModel):
    analyst_status: Optional[str] = None   # approved, flagged, false_positive
    analyst_notes: Optional[str] = None
    risk_score: Optional[int] = None


@router.get("/workspaces/{workspace_id}/connectors")
async def list_connectors(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    return await ConnectorService.list_connectors(db, ws.slug)


@router.post("/workspaces/{workspace_id}/connectors", status_code=201)
async def create_connector(
    workspace_id: int,
    data: ConnectorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    connector = await ConnectorService.create_connector(
        db=db, workspace_slug=ws.slug,
        name=data.name, connector_type=data.connector_type,
        platform=data.platform, config=data.config,
        created_by_id=current_user.id, created_by_email=current_user.email,
    )
    await AuditService.log(
        db=db, workspace_slug=ws.slug, action="connector.create",
        user_id=current_user.id, user_email=current_user.email,
        resource_type="connector", resource_id=str(connector["id"]),
        detail={"name": data.name, "platform": data.platform},
    )
    return connector


@router.post("/workspaces/{workspace_id}/connectors/{connector_id}/scan")
async def trigger_scan(
    workspace_id: int,
    connector_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    result = await ConnectorService.trigger_scan(
        db=db, workspace_slug=ws.slug, connector_id=connector_id,
        triggered_by_id=current_user.id, triggered_by_email=current_user.email,
    )
    await AuditService.log(
        db=db, workspace_slug=ws.slug, action="scan.trigger",
        user_id=current_user.id, user_email=current_user.email,
        resource_type="connector", resource_id=str(connector_id),
        detail=result,
    )
    return result


@router.get("/workspaces/{workspace_id}/assets")
async def list_assets(
    workspace_id: int,
    category: Optional[str] = None,
    risk_level: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    assets = await ConnectorService.list_assets(db, ws.slug, category=category, risk_level=risk_level)
    return {"total": len(assets), "items": assets}


@router.patch("/workspaces/{workspace_id}/assets/{asset_id}")
async def update_asset(
    workspace_id: int,
    asset_id: int,
    data: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    return await ConnectorService.update_asset(
        db=db, workspace_slug=ws.slug, asset_id=asset_id,
        analyst_status=data.analyst_status,
        analyst_notes=data.analyst_notes,
        risk_score=data.risk_score,
    )
