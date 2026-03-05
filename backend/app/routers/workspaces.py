from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..services.workspace_service import WorkspaceService
from ..schemas.workspace import WorkspaceCreate, WorkspaceUpdate, WorkspaceRead

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])

def require_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Apenas admins da plataforma podem realizar esta ação")
    return current_user

@router.get("", response_model=list[WorkspaceRead])
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.is_platform_admin:
        return await WorkspaceService.list_all(db)
    return await WorkspaceService.list_for_user(db, current_user.id)

@router.post("", response_model=WorkspaceRead, status_code=201)
async def create_workspace(
    data: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_platform_admin),
):
    return await WorkspaceService.create(db, data)

@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    return ws

@router.patch("/{workspace_id}", response_model=WorkspaceRead)
async def update_workspace(
    workspace_id: int,
    data: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_platform_admin),
):
    return await WorkspaceService.update(db, workspace_id, data)

@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_platform_admin),
):
    await WorkspaceService.delete(db, workspace_id)
