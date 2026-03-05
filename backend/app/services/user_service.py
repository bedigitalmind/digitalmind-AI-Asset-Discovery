from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from ..models.user import User
from ..models.workspace import WorkspaceMembership, WorkspaceRole, Workspace
from ..schemas.user import UserCreate, WorkspaceMemberCreate, WorkspaceMemberUpdate
from ..core.security import get_password_hash

class UserService:

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        result = await db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: UserCreate) -> User:
        existing = await UserService.get_by_email(db, data.email)
        if existing:
            raise HTTPException(status_code=409, detail="E-mail já cadastrado")

        user = User(
            email=data.email.lower(),
            full_name=data.full_name,
            hashed_password=get_password_hash(data.password),
            is_platform_admin=data.is_platform_admin,
        )
        db.add(user)
        await db.flush()
        return user

    @staticmethod
    async def list_workspace_members(db: AsyncSession, workspace_id: int) -> list[WorkspaceMembership]:
        result = await db.execute(
            select(WorkspaceMembership)
            .where(WorkspaceMembership.workspace_id == workspace_id)
            .join(WorkspaceMembership.user)
        )
        return list(result.scalars().all())

    @staticmethod
    async def add_workspace_member(
        db: AsyncSession, workspace_id: int, data: WorkspaceMemberCreate
    ) -> WorkspaceMembership:
        # Get or create user
        user = await UserService.get_by_email(db, data.email)
        if not user:
            user = User(
                email=data.email.lower(),
                full_name=data.full_name,
                hashed_password=get_password_hash(data.password),
            )
            db.add(user)
            await db.flush()

        # Check if already a member
        result = await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user.id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.is_active:
                raise HTTPException(status_code=409, detail="Usuário já é membro deste workspace")
            existing.is_active = True
            existing.role = data.role
            return existing

        membership = WorkspaceMembership(
            user_id=user.id,
            workspace_id=workspace_id,
            role=data.role,
        )
        db.add(membership)
        await db.flush()
        return membership

    @staticmethod
    async def update_workspace_member(
        db: AsyncSession, membership_id: int, workspace_id: int, data: WorkspaceMemberUpdate
    ) -> WorkspaceMembership:
        result = await db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.id == membership_id,
                WorkspaceMembership.workspace_id == workspace_id,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=404, detail="Membro não encontrado")

        if data.role is not None:
            membership.role = data.role
        if data.is_active is not None:
            membership.is_active = data.is_active

        await db.flush()
        return membership

    @staticmethod
    async def get_user_role_in_workspace(
        db: AsyncSession, user_id: int, workspace_id: int
    ) -> WorkspaceRole | None:
        result = await db.execute(
            select(WorkspaceMembership.role).where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.is_active == True,
            )
        )
        row = result.scalar_one_or_none()
        return WorkspaceRole(row) if row else None
