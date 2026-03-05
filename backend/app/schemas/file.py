from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class FileRead(BaseModel):
    id: int
    original_filename: str
    file_size: int
    mime_type: Optional[str]
    source_type: str
    status: str
    uploaded_by_email: Optional[str]
    checksum_sha256: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}

class FileListResponse(BaseModel):
    total: int
    items: list[FileRead]
