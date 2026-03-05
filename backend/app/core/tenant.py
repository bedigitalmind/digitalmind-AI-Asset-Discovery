"""
Multi-tenant schema management.
Each workspace gets its own PostgreSQL schema: ws_{workspace_slug}
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import re

def sanitize_slug(slug: str) -> str:
    return re.sub(r'[^a-z0-9_]', '_', slug.lower())

def get_schema_name(workspace_slug: str) -> str:
    return f"ws_{sanitize_slug(workspace_slug)}"

async def create_workspace_schema(db: AsyncSession, workspace_slug: str) -> None:
    schema = get_schema_name(workspace_slug)
    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # Audit log
    await db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".audit_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER,
            user_email VARCHAR(255),
            action VARCHAR(100) NOT NULL,
            resource_type VARCHAR(100),
            resource_id VARCHAR(255),
            detail JSONB,
            ip_address VARCHAR(45),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # Uploaded files
    await db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".ingestion_files (
            id BIGSERIAL PRIMARY KEY,
            original_filename VARCHAR(500) NOT NULL,
            stored_filename VARCHAR(500) NOT NULL,
            file_size BIGINT NOT NULL,
            mime_type VARCHAR(200),
            source_type VARCHAR(100) NOT NULL DEFAULT 'upload',
            status VARCHAR(50) NOT NULL DEFAULT 'uploaded',
            uploaded_by_id INTEGER,
            uploaded_by_email VARCHAR(255),
            storage_bucket VARCHAR(255),
            storage_key VARCHAR(500),
            checksum_sha256 VARCHAR(64),
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # Cloud/SaaS connectors
    await db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".connectors (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            connector_type VARCHAR(100) NOT NULL,
            platform VARCHAR(100) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'configured',
            config_encrypted BYTEA,
            config_iv VARCHAR(100),
            last_scan_at TIMESTAMPTZ,
            last_scan_status VARCHAR(50),
            last_scan_error TEXT,
            created_by_id INTEGER,
            created_by_email VARCHAR(255),
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # Scan jobs
    await db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".scan_jobs (
            id BIGSERIAL PRIMARY KEY,
            connector_id BIGINT REFERENCES "{schema}".connectors(id) ON DELETE CASCADE,
            source_type VARCHAR(100) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            assets_found INTEGER DEFAULT 0,
            error_message TEXT,
            raw_result JSONB,
            triggered_by_id INTEGER,
            triggered_by_email VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # Discovered AI assets
    await db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".discovered_assets (
            id BIGSERIAL PRIMARY KEY,
            external_id VARCHAR(500),
            name VARCHAR(500) NOT NULL,
            vendor VARCHAR(255),
            category VARCHAR(100) NOT NULL,
            subcategory VARCHAR(100),
            asset_type VARCHAR(100),
            platform VARCHAR(100),
            risk_level VARCHAR(20) NOT NULL DEFAULT 'medium',
            risk_score INTEGER DEFAULT 5,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            confidence_score FLOAT DEFAULT 1.0,
            detection_source VARCHAR(100),
            source_details JSONB,
            users_count INTEGER,
            departments JSONB,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_shadow_ai BOOLEAN DEFAULT FALSE,
            analyst_notes TEXT,
            analyst_status VARCHAR(50) DEFAULT 'pending_review',
            metadata JSONB,
            scan_job_id BIGINT REFERENCES "{schema}".scan_jobs(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_asset_external_id UNIQUE(external_id)
        )
    """))

    # Generated reports
    await db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".reports (
            id BIGSERIAL PRIMARY KEY,
            title VARCHAR(500) NOT NULL,
            report_type VARCHAR(50) NOT NULL DEFAULT 'full_discovery',
            format VARCHAR(10) NOT NULL DEFAULT 'pdf',
            status VARCHAR(50) NOT NULL DEFAULT 'generating',
            storage_key VARCHAR(500),
            file_size BIGINT,
            generated_by_id INTEGER,
            generated_by_email VARCHAR(255),
            snapshot JSONB,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    await db.commit()

async def drop_workspace_schema(db: AsyncSession, workspace_slug: str) -> None:
    schema = get_schema_name(workspace_slug)
    await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await db.commit()
