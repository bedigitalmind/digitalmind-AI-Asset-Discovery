"""
Connector service — manages cloud/SaaS connectors and triggers scans.
Sprint 2: Azure (azure-identity + azure-mgmt-*)
Sprint 5: Salesforce, ServiceNow, SAP AI Core, Dynamics 365
Sprint 6: Microsoft 365 via Graph API
"""
import json
import base64
import os
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException
from ..core.tenant import get_schema_name
from ..core.taxonomy import classify_by_azure_resource_type, TAXONOMY_BY_ID


class ConnectorService:

    @staticmethod
    async def list_connectors(db: AsyncSession, workspace_slug: str) -> list[dict]:
        schema = get_schema_name(workspace_slug)
        result = await db.execute(text(f"""
            SELECT id, name, connector_type, platform, status,
                   last_scan_at, last_scan_status, last_scan_error,
                   created_by_email, created_at, updated_at
            FROM "{schema}".connectors
            ORDER BY created_at DESC
        """))
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def create_connector(
        db: AsyncSession,
        workspace_slug: str,
        name: str,
        connector_type: str,
        platform: str,
        config: dict,
        created_by_id: int,
        created_by_email: str,
    ) -> dict:
        schema = get_schema_name(workspace_slug)
        # Encrypt config with simple base64 for now (replace with Vault in production)
        config_bytes = json.dumps(config).encode()
        config_b64 = base64.b64encode(config_bytes).decode()

        result = await db.execute(text(f"""
            INSERT INTO "{schema}".connectors
              (name, connector_type, platform, status,
               config_encrypted, config_iv,
               created_by_id, created_by_email)
            VALUES (:name, :ctype, :platform, 'configured',
                    :config, :iv, :uid, :uemail)
            RETURNING id, name, connector_type, platform, status,
                      created_by_email, created_at
        """), {
            "name": name, "ctype": connector_type, "platform": platform,
            "config": config_b64, "iv": "base64",
            "uid": created_by_id, "uemail": created_by_email,
        })
        return dict(result.mappings().one())

    @staticmethod
    async def get_connector_config(db: AsyncSession, workspace_slug: str, connector_id: int) -> dict:
        schema = get_schema_name(workspace_slug)
        result = await db.execute(text(f"""
            SELECT config_encrypted, config_iv FROM "{schema}".connectors
            WHERE id = :id
        """), {"id": connector_id})
        row = result.mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Conector não encontrado")
        config_bytes = base64.b64decode(row["config_encrypted"])
        return json.loads(config_bytes)

    @staticmethod
    async def trigger_scan(
        db: AsyncSession,
        workspace_slug: str,
        connector_id: int,
        triggered_by_id: int,
        triggered_by_email: str,
    ) -> dict:
        schema = get_schema_name(workspace_slug)

        # Get connector details
        result = await db.execute(text(f"""
            SELECT id, name, connector_type, platform FROM "{schema}".connectors
            WHERE id = :id
        """), {"id": connector_id})
        connector = result.mappings().one_or_none()
        if not connector:
            raise HTTPException(status_code=404, detail="Conector não encontrado")

        # Create scan job
        job_result = await db.execute(text(f"""
            INSERT INTO "{schema}".scan_jobs
              (connector_id, source_type, status, started_at,
               triggered_by_id, triggered_by_email)
            VALUES (:cid, :stype, 'running', NOW(), :uid, :uemail)
            RETURNING id
        """), {
            "cid": connector_id,
            "stype": connector["platform"],
            "uid": triggered_by_id,
            "uemail": triggered_by_email,
        })
        job_id = job_result.scalar_one()

        await db.commit()  # Commit so scan can read it

        # Execute scan
        config = await ConnectorService.get_connector_config(db, workspace_slug, connector_id)
        platform = connector["platform"]
        try:
            if platform == "azure":
                assets = await ConnectorService._scan_azure(config)
            elif platform in ("salesforce", "servicenow", "sap", "dynamics365", "m365"):
                from .connectors import PLATFORM_MAP
                discover_fn = PLATFORM_MAP[platform]
                assets = await discover_fn(config)
            else:
                assets = []

            # Save discovered assets
            assets_saved = 0
            for asset in assets:
                await db.execute(text(f"""
                    INSERT INTO "{schema}".discovered_assets
                      (external_id, name, vendor, category, subcategory, asset_type,
                       platform, risk_level, risk_score, status, confidence_score,
                       detection_source, source_details, is_shadow_ai,
                       analyst_status, scan_job_id, metadata)
                    VALUES
                      (:eid, :name, :vendor, :category, :subcategory, :atype,
                       :platform, :risk_level, :risk_score, 'active', :confidence,
                       :source, :source_details::jsonb, :shadow,
                       'pending_review', :job_id, :meta::jsonb)
                    ON CONFLICT (external_id) DO UPDATE SET
                      last_seen_at = NOW(),
                      risk_level = EXCLUDED.risk_level,
                      updated_at = NOW()
                """), {
                    "eid": asset.get("external_id"),
                    "name": asset["name"],
                    "vendor": asset.get("vendor", "Unknown"),
                    "category": asset["category"],
                    "subcategory": asset.get("subcategory"),
                    "atype": asset.get("asset_type"),
                    "platform": platform,
                    "risk_level": asset.get("risk_level", "medium"),
                    "risk_score": asset.get("risk_score", 5),
                    "confidence": asset.get("confidence_score", 1.0),
                    "source": f"{platform}_connector",
                    "source_details": json.dumps(asset.get("source_details", {})),
                    "shadow": asset.get("is_shadow_ai", False),
                    "job_id": job_id,
                    "meta": json.dumps(asset.get("metadata", {})),
                })
                assets_saved += 1

            # Update job as complete
            await db.execute(text(f"""
                UPDATE "{schema}".scan_jobs
                SET status = 'completed', completed_at = NOW(), assets_found = :count
                WHERE id = :id
            """), {"count": assets_saved, "id": job_id})

            # Update connector last scan
            await db.execute(text(f"""
                UPDATE "{schema}".connectors
                SET last_scan_at = NOW(), last_scan_status = 'success', last_scan_error = NULL
                WHERE id = :id
            """), {"id": connector_id})

            await db.commit()
            return {"job_id": job_id, "assets_found": assets_saved, "status": "completed"}

        except Exception as e:
            await db.execute(text(f"""
                UPDATE "{schema}".scan_jobs
                SET status = 'failed', completed_at = NOW(), error_message = :err
                WHERE id = :id
            """), {"err": str(e), "id": job_id})
            await db.execute(text(f"""
                UPDATE "{schema}".connectors
                SET last_scan_status = 'error', last_scan_error = :err WHERE id = :id
            """), {"err": str(e)[:500], "id": connector_id})
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Erro no scan: {str(e)}")

    @staticmethod
    async def _scan_azure(config: dict) -> list[dict]:
        """
        Scan Azure subscription for AI resources using azure-mgmt SDK.
        config: {tenant_id, client_id, client_secret, subscription_id}
        """
        try:
            from azure.identity import ClientSecretCredential
            from azure.mgmt.resource import ResourceManagementClient
            from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="Azure SDK não instalado. Execute: pip install azure-identity azure-mgmt-resource azure-mgmt-cognitiveservices"
            )

        tenant_id = config.get("tenant_id")
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        subscription_id = config.get("subscription_id")

        if not all([tenant_id, client_id, client_secret, subscription_id]):
            raise ValueError("Configuração incompleta: tenant_id, client_id, client_secret, subscription_id são obrigatórios")

        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

        discovered = []

        # 1. Scan ALL resources and classify against taxonomy
        resource_client = ResourceManagementClient(credential, subscription_id)
        for resource in resource_client.resources.list():
            taxonomy_matches = classify_by_azure_resource_type(resource.type or "")
            for entry in taxonomy_matches:
                discovered.append({
                    "external_id": f"azure:{resource.id}",
                    "name": f"{entry.name} — {resource.name}",
                    "vendor": entry.vendor,
                    "category": entry.category,
                    "subcategory": entry.subcategory,
                    "asset_type": resource.type,
                    "risk_level": entry.risk_level,
                    "risk_score": entry.risk_score,
                    "confidence_score": 1.0,
                    "is_shadow_ai": False,
                    "source_details": {
                        "resource_id": resource.id,
                        "resource_type": resource.type,
                        "location": resource.location,
                        "resource_group": resource.id.split("/resourceGroups/")[1].split("/")[0] if resource.id else None,
                        "taxonomy_id": entry.id,
                    },
                    "metadata": {
                        "azure_name": resource.name,
                        "azure_location": resource.location,
                        "azure_tags": resource.tags or {},
                    },
                })

        # 2. Detailed scan of Cognitive Services / Azure OpenAI
        try:
            cog_client = CognitiveServicesManagementClient(credential, subscription_id)
            for account in cog_client.accounts.list():
                kind = account.kind or ""
                is_openai = "OpenAI" in kind
                entry_id = "api-azure-openai" if is_openai else "infra-azure-cognitive"
                entry = TAXONOMY_BY_ID.get(entry_id)
                if entry:
                    ext_id = f"azure-cog:{account.id}"
                    # Avoid duplicates from resource scan
                    if not any(d["external_id"] == ext_id for d in discovered):
                        discovered.append({
                            "external_id": ext_id,
                            "name": f"{entry.name} — {account.name}",
                            "vendor": entry.vendor,
                            "category": entry.category,
                            "subcategory": entry.subcategory,
                            "asset_type": "Microsoft.CognitiveServices/accounts",
                            "risk_level": entry.risk_level,
                            "risk_score": entry.risk_score,
                            "confidence_score": 1.0,
                            "is_shadow_ai": False,
                            "source_details": {
                                "account_name": account.name,
                                "kind": account.kind,
                                "sku": account.sku.name if account.sku else None,
                                "location": account.location,
                                "endpoint": account.properties.endpoint if account.properties else None,
                                "taxonomy_id": entry.id,
                            },
                            "metadata": {
                                "azure_kind": account.kind,
                                "azure_tags": account.tags or {},
                            },
                        })
        except Exception:
            pass  # Non-fatal: Cognitive Services scan failure

        return discovered

    @staticmethod
    async def list_assets(
        db: AsyncSession,
        workspace_slug: str,
        category: str | None = None,
        risk_level: str | None = None,
    ) -> list[dict]:
        schema = get_schema_name(workspace_slug)
        filters = ""
        params: dict = {}
        if category:
            filters += " AND category = :category"
            params["category"] = category
        if risk_level:
            filters += " AND risk_level = :risk_level"
            params["risk_level"] = risk_level

        result = await db.execute(text(f"""
            SELECT id, external_id, name, vendor, category, subcategory,
                   asset_type, platform, risk_level, risk_score, status,
                   confidence_score, detection_source, is_shadow_ai,
                   analyst_status, analyst_notes,
                   first_seen_at, last_seen_at, created_at
            FROM "{schema}".discovered_assets
            WHERE 1=1 {filters}
            ORDER BY risk_score DESC, last_seen_at DESC
        """), params)
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def update_asset(
        db: AsyncSession,
        workspace_slug: str,
        asset_id: int,
        analyst_status: str | None = None,
        analyst_notes: str | None = None,
        risk_score: int | None = None,
    ) -> dict:
        schema = get_schema_name(workspace_slug)
        updates = []
        params: dict = {"id": asset_id}
        if analyst_status:
            updates.append("analyst_status = :analyst_status")
            params["analyst_status"] = analyst_status
        if analyst_notes is not None:
            updates.append("analyst_notes = :analyst_notes")
            params["analyst_notes"] = analyst_notes
        if risk_score is not None:
            updates.append("risk_score = :risk_score")
            params["risk_score"] = risk_score

        if not updates:
            raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

        updates.append("updated_at = NOW()")
        result = await db.execute(text(f"""
            UPDATE "{schema}".discovered_assets
            SET {', '.join(updates)}
            WHERE id = :id
            RETURNING id, name, analyst_status, analyst_notes, risk_score, updated_at
        """), params)
        row = result.mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Asset não encontrado")
        return dict(row)
