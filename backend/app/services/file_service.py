import hashlib
import uuid
from datetime import datetime
from typing import BinaryIO
import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..core.config import get_settings
from ..core.tenant import get_schema_name

settings = get_settings()

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if settings.MINIO_SECURE else 'http'}://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
    )

def get_bucket_name(workspace_slug: str) -> str:
    return f"ws-{workspace_slug.replace('_', '-')}"

def ensure_bucket(s3_client, bucket_name: str) -> None:
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError:
        s3_client.create_bucket(Bucket=bucket_name)

class FileService:

    @staticmethod
    async def upload_file(
        db: AsyncSession,
        workspace_slug: str,
        file: UploadFile,
        uploaded_by_id: int,
        uploaded_by_email: str,
    ) -> dict:
        max_bytes = settings.MINIO_MAX_FILE_SIZE_MB * 1024 * 1024
        content = await file.read()

        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Arquivo excede o limite de {settings.MINIO_MAX_FILE_SIZE_MB}MB"
            )

        # Calculate checksum
        checksum = hashlib.sha256(content).hexdigest()

        # Generate unique storage key
        ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
        stored_filename = f"{uuid.uuid4().hex}.{ext}"
        storage_key = f"ingestion/{stored_filename}"

        # Upload to MinIO
        s3 = get_s3_client()
        bucket = get_bucket_name(workspace_slug)
        ensure_bucket(s3, bucket)

        s3.put_object(
            Bucket=bucket,
            Key=storage_key,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
            Metadata={
                "original-filename": file.filename,
                "uploaded-by": uploaded_by_email,
                "checksum-sha256": checksum,
            }
        )

        # Insert record in workspace schema
        schema = get_schema_name(workspace_slug)
        result = await db.execute(
            text(f"""
                INSERT INTO "{schema}".ingestion_files
                  (original_filename, stored_filename, file_size, mime_type,
                   source_type, status, uploaded_by_id, uploaded_by_email,
                   storage_bucket, storage_key, checksum_sha256)
                VALUES
                  (:orig, :stored, :size, :mime, 'upload', 'uploaded',
                   :uid, :uemail, :bucket, :key, :checksum)
                RETURNING id, original_filename, file_size, mime_type,
                          source_type, status, uploaded_by_email,
                          checksum_sha256, created_at
            """),
            {
                "orig": file.filename,
                "stored": stored_filename,
                "size": len(content),
                "mime": file.content_type,
                "uid": uploaded_by_id,
                "uemail": uploaded_by_email,
                "bucket": bucket,
                "key": storage_key,
                "checksum": checksum,
            }
        )
        row = result.mappings().one()
        return dict(row)

    @staticmethod
    async def list_files(db: AsyncSession, workspace_slug: str) -> list[dict]:
        schema = get_schema_name(workspace_slug)
        result = await db.execute(
            text(f"""
                SELECT id, original_filename, file_size, mime_type, source_type,
                       status, uploaded_by_email, checksum_sha256, created_at
                FROM "{schema}".ingestion_files
                ORDER BY created_at DESC
            """)
        )
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    async def get_file_info(db: AsyncSession, workspace_slug: str, file_id: int) -> dict | None:
        """Return file metadata including storage key. Used by detection pipeline."""
        schema = get_schema_name(workspace_slug)
        result = await db.execute(
            text(f"""
                SELECT id, original_filename, stored_filename, file_size, mime_type,
                       source_type, status, storage_bucket, storage_key,
                       uploaded_by_email, checksum_sha256, created_at
                FROM "{schema}".ingestion_files
                WHERE id = :id
            """),
            {"id": file_id}
        )
        row = result.mappings().one_or_none()
        return dict(row) if row else None

    @staticmethod
    async def download_file(workspace_slug: str, storage_key: str) -> bytes:
        """Download file bytes from MinIO. Used by detection pipeline."""
        s3 = get_s3_client()
        bucket = get_bucket_name(workspace_slug)
        try:
            response = s3.get_object(Bucket=bucket, Key=storage_key)
            return response["Body"].read()
        except ClientError as e:
            raise HTTPException(status_code=404, detail=f"Arquivo não encontrado no storage: {e}")

    @staticmethod
    async def delete_file(db: AsyncSession, workspace_slug: str, file_id: int) -> None:
        schema = get_schema_name(workspace_slug)
        result = await db.execute(
            text(f'SELECT storage_bucket, storage_key FROM "{schema}".ingestion_files WHERE id = :id'),
            {"id": file_id}
        )
        row = result.mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado")

        # Delete from MinIO
        s3 = get_s3_client()
        try:
            s3.delete_object(Bucket=row["storage_bucket"], Key=row["storage_key"])
        except ClientError:
            pass

        await db.execute(
            text(f'DELETE FROM "{schema}".ingestion_files WHERE id = :id'),
            {"id": file_id}
        )
