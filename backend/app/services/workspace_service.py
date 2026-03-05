from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from ..models.workspace import Workspace, WorkspaceStatus
from ..schemas.workspace import WorkspaceCreate, WorkspaceUpdate
from ..core.tenant import create_workspace_schema, drop_workspace_schema

class WorkspaceService:

    @staticmethod
    async def get_by_id(db: AsyncSession, workspace_id: int) -> Workspace | None:
        result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Workspace | None:
        result = await db.execute(select(Workspace).where(Workspace.slug == slug))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession) -> list[Workspace]:
        result = await db.execute(
            select(Workspace).order_by(Workspace.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_user(db: AsyncSession, user_id: int) -> list[Workspace]:
        from ..models.workspace import WorkspaceMembership
        result = await db.execute(
            select(Workspace)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.is_active == True,
            )
            .order_by(Workspace.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_membership(
        db: AsyncSession,
        workspace_id: int,
        user_id: int,
    ):
        """Return the WorkspaceMembership for a user, or None if not a member."""
        from ..models.workspace import WorkspaceMembership
        result = await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: WorkspaceCreate) -> Workspace:
        existing = await WorkspaceService.get_by_slug(db, data.slug)
        if existing:
            raise HTTPException(status_code=409, detail="Slug já em uso")

        workspace = Workspace(**data.model_dump())
        db.add(workspace)
        await db.flush()

        # Create tenant schema
        await create_workspace_schema(db, data.slug)
        workspace.schema_created = True

        return workspace

    @staticmethod
    async def update(db: AsyncSession, workspace_id: int, data: WorkspaceUpdate) -> Workspace:
        workspace = await WorkspaceService.get_by_id(db, workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace não encontrado")

        for field, value in data.model_dump(exclude_none=True).items():
            setattr(workspace, field, value)

        await db.flush()
        return workspace

    @staticmethod
    async def delete(db: AsyncSession, workspace_id: int) -> None:
        workspace = await WorkspaceService.get_by_id(db, workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace não encontrado")

        await drop_workspace_schema(db, workspace.slug)
        await db.delete(workspace)
