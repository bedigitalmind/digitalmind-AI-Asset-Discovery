from sqlalchemy import String, Boolean, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.database import Base
from .base import TimestampMixin
import enum

class WorkspaceStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"

class WorkspaceRole(str, enum.Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"

class Workspace(Base, TimestampMixin):
    """A client workspace — fully isolated environment."""
    __tablename__ = "workspaces"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[WorkspaceStatus] = mapped_column(
        String(20), default=WorkspaceStatus.ACTIVE, nullable=False
    )
    schema_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    memberships: Mapped[list["WorkspaceMembership"]] = relationship(back_populates="workspace")

    def __repr__(self):
        return f"<Workspace {self.slug}>"

class WorkspaceMembership(Base, TimestampMixin):
    """Links a platform user to a workspace with a specific role."""
    __tablename__ = "workspace_memberships"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("public.users.id"), nullable=False)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("public.workspaces.id"), nullable=False)
    role: Mapped[WorkspaceRole] = mapped_column(
        String(20), default=WorkspaceRole.ANALYST, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="memberships")
    workspace: Mapped["Workspace"] = relationship(back_populates="memberships")
