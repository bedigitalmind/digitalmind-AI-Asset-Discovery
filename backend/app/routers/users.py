from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..models.workspace import WorkspaceRole
from ..services.user_service import UserService
from ..services.workspace_service import WorkspaceService
from ..schemas.user import UserCreate, UserRead, WorkspaceMemberCreate, WorkspaceMemberRead, WorkspaceMemberUpdate

router = APIRouter(tags=["Usuários"])

@router.post("/users", response_model=UserRead, status_code=201)
async def create_platform_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Apenas admins da plataforma podem criar usuários")
    return await UserService.create(db, data)

@router.get("/workspaces/{workspace_id}/members", response_model=list[WorkspaceMemberRead])
async def list_members(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await WorkspaceService.get_by_id(db, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    return await UserService.list_workspace_members(db, workspace_id)

@router.post("/workspaces/{workspace_id}/members", response_model=WorkspaceMemberRead, status_code=201)
async def add_member(
    workspace_id: int,
    data: WorkspaceMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = await UserService.get_user_role_in_workspace(db, current_user.id, workspace_id)
    if not current_user.is_platform_admin and role != WorkspaceRole.ADMIN:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")
    return await UserService.add_workspace_member(db, workspace_id, data)

@router.patch("/workspaces/{workspace_id}/members/{membership_id}", response_model=WorkspaceMemberRead)
async def update_member(
    workspace_id: int,
    membership_id: int,
    data: WorkspaceMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = await UserService.get_user_role_in_workspace(db, current_user.id, workspace_id)
    if not current_user.is_platform_admin and role != WorkspaceRole.ADMIN:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")
    return await UserService.update_workspace_member(db, membership_id, workspace_id, data)
