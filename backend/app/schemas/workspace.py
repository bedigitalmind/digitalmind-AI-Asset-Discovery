from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional
import re
from ..models.workspace import WorkspaceStatus

class WorkspaceCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    contact_email: Optional[str] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.lower().strip()
        if not re.match(r'^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$', v):
            raise ValueError("Slug deve ter 3–50 chars, apenas letras minúsculas, números e hífens")
        return v

class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    contact_email: Optional[str] = None
    status: Optional[WorkspaceStatus] = None

class WorkspaceRead(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    industry: Optional[str]
    company_size: Optional[str]
    contact_email: Optional[str]
    status: WorkspaceStatus
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
