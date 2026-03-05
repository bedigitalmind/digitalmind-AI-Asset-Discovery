from pydantic import BaseModel, EmailStr
from datetime import datetime
from ..models.workspace import WorkspaceRole

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    is_platform_admin: bool = False

class UserRead(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    is_platform_admin: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class WorkspaceMemberCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: WorkspaceRole = WorkspaceRole.ANALYST
    password: str

class WorkspaceMemberRead(BaseModel):
    id: int
    user_id: int
    workspace_id: int
    role: WorkspaceRole
    is_active: bool
    user: UserRead
    created_at: datetime
    model_config = {"from_attributes": True}

class WorkspaceMemberUpdate(BaseModel):
    role: WorkspaceRole | None = None
    is_active: bool | None = None
