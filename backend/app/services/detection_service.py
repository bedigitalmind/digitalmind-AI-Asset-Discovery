"""
Detection Service — Sprint 3
Orchestrates the full detection pipeline:
  1. Parse uploaded file → RawSignals
  2. Enrich signals with LLM (Claude) in batches
  3. Persist discovered assets to workspace schema
  4. Update ingestion file status
"""
import logging
import uuid
from dataclasses import asdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..core.tenant import get_schema_name
from ..core.llm import batch_enrich_assets
from .parser_service import parse_file, RawSignal

logger = logging.getLogger(__name__)


# ─── Risk mapping ─────────────────────────────────────────────────────────────

def _normalize_risk_level(risk_level: str | None) -> str:
    mapping = {
        "low": "low", "medium": "medium", "high": "high", "critical": "critical",
        "LOW": "low", "MEDIUM": "medium", "HIGH": "high", "CRITICAL": "critical",
    }
    return mapping.get(risk_level or "", "medium")


def _normalize_analyst_status(recommended_action: str | None) -> str:
    mapping = {
        "monitor": "pending_review",
        "review_with_owner": "pending_review",
        "request_approval": "pending_review",
        "block_immediately": "pending_review",
    }
    return mapping.get(recommended_action or "", "pending_review")


def _build_asset_row(
    signal: RawSignal,
    enrichment: dict[str, Any],
    ingestion_file_id: int | None,
) -> dict[str, Any]:
    """Merge parser signal + LLM enrichment into a DB row dict."""
    # LLM fields override taxonomy fields when available
    name        = signal.name
    vendor      = enrichment.get("vendor_confirmed") or signal.vendor
    category    = enrichment.get("confirmed_category") or signal.category
    subcategory = enrichment.get("confirmed_subcategory") or signal.subcategory
    description = enrichment.get("description", signal.signal_value[:200] if signal.signal_value else "")
    is_shadow   = enrichment.get("is_shadow_ai", signal.is_shadow_ai)
    risk_level  = _normalize_risk_level(enrichment.get("risk_level", "medium"))
    risk_score  = int(enrichment.get("risk_score", 5))
    confidence  = float(enrichment.get("confidence_score", signal.confidence_score))
    analyst_status = _normalize_analyst_status(enrichment.get("recommended_action"))

    # Stable external_id: hash of name+vendor+signal_value so re-runs deduplicate
    ext_id = f"file_{signal.signal_type}_{signal.signal_value[:64]}"

    return {
        "external_id":      ext_id,
        "name":             name,
        "vendor":           vendor,
        "category":         category,
        "subcategory":      subcategory,
        "description":      description,
        "asset_type":       signal.signal_type,
        "platform":         "file_import",
        "risk_level":       risk_level,
        "risk_score":       min(10, max(1, risk_score)),
        "confidence_score": min(1.0, max(0.0, confidence)),
        "is_shadow_ai":     bool(is_shadow),
        "analyst_status":   analyst_status,
        "scan_job_id":      None,  # file-based, no connector scan job
        "metadata":         {
            "source_file_id": ingestion_file_id,
            "signal_type": signal.signal_type,
            "signal_value": signal.signal_value,
            "shadow_ai_reason": enrichment.get("shadow_ai_reason"),
            "risk_justification": enrichment.get("risk_justification"),
            "recommended_action": enrichment.get("recommended_action"),
            "llm_enriched": bool(enrichment),
            **{k: v for k, v in signal.raw_context.items() if isinstance(v, (str, int, float, bool))},
        },
    }


async def _upsert_assets(
    db: AsyncSession,
    schema: str,
    asset_rows: list[dict[str, Any]],
) -> int:
    """Insert or update discovered assets. Returns count of new assets."""
    saved = 0
    for row in asset_rows:
        try:
            result = await db.execute(text(f"""
                INSERT INTO "{schema}".discovered_assets (
                    external_id, name, vendor, category, subcategory,
                    description, asset_type, platform,
                    risk_level, risk_score, confidence_score,
                    is_shadow_ai, analyst_status, scan_job_id, metadata,
                    first_seen_at, last_seen_at
                ) VALUES (
                    :external_id, :name, :vendor, :category, :subcategory,
                    :description, :asset_type, :platform,
                    :risk_level, :risk_score, :confidence_score,
                    :is_shadow_ai, :analyst_status, :scan_job_id, :metadata::jsonb,
                    NOW(), NOW()
                )
                ON CONFLICT (external_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    vendor = EXCLUDED.vendor,
                    category = EXCLUDED.category,
                    subcategory = EXCLUDED.subcategory,
                    description = EXCLUDED.description,
                    risk_level = EXCLUDED.risk_level,
                    risk_score = EXCLUDED.risk_score,
                    confidence_score = EXCLUDED.confidence_score,
                    is_shadow_ai = EXCLUDED.is_shadow_ai,
                    last_seen_at = NOW(),
                    metadata = "{schema}".discovered_assets.metadata || EXCLUDED.metadata
                RETURNING (xmax = 0) AS is_new
            """), {**row, "metadata": __import__("json").dumps(row["metadata"])})
            row_result = result.fetchone()
            if row_result and row_result[0]:  # is_new
                saved += 1
        except Exception as e:
            logger.error(f"Asset upsert error for {row.get('name')}: {e}")
    return saved


async def _mark_file_status(
    db: AsyncSession,
    schema: str,
    file_id: int,
    status: str,
    assets_found: int = 0,
) -> None:
    await db.execute(text(f"""
        UPDATE "{schema}".ingestion_files
        SET status = :status,
            metadata = COALESCE(metadata, '{{}}'::jsonb) || jsonb_build_object(
                'assets_found', :assets_found,
                'processed_at', NOW()::text
            )
        WHERE id = :file_id
    """), {"status": status, "assets_found": assets_found, "file_id": file_id})


# ─── Public API ───────────────────────────────────────────────────────────────

async def process_ingested_file(
    db: AsyncSession,
    workspace_slug: str,
    file_id: int,
    filename: str,
    content_bytes: bytes,
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    Full pipeline: parse file → enrich with LLM → persist assets.

    Returns summary dict with counts and any errors.
    """
    schema = get_schema_name(workspace_slug)
    summary: dict[str, Any] = {
        "file_id": file_id,
        "filename": filename,
        "signals_extracted": 0,
        "assets_saved": 0,
        "assets_updated": 0,
        "errors": [],
        "log_type": "unknown",
    }

    # Mark file as processing
    await _mark_file_status(db, schema, file_id, "processing")
    await db.commit()

    try:
        # Step 1: Parse
        parse_result = await parse_file(filename, content_bytes, use_llm_fallback=use_llm)
        summary["signals_extracted"] = len(parse_result.signals)
        summary["log_type"] = parse_result.log_type_detected
        summary["errors"].extend(parse_result.errors)

        if not parse_result.signals:
            await _mark_file_status(db, schema, file_id, "processed", 0)
            await db.commit()
            return summary

        # Step 2: LLM enrichment (batched)
        signals = parse_result.signals
        enrichments: list[dict[str, Any]] = [{}] * len(signals)
        if use_llm:
            asset_dicts = [
                {
                    "name": s.name,
                    "vendor": s.vendor,
                    "category": s.category,
                    "subcategory": s.subcategory,
                    "raw_data": s.raw_context,
                }
                for s in signals
            ]
            try:
                enrichments = await batch_enrich_assets(asset_dicts, concurrency=3)
            except Exception as e:
                logger.error(f"Batch enrichment failed: {e}")
                summary["errors"].append(f"LLM enrichment failed: {e}")
                enrichments = [{}] * len(signals)

        # Step 3: Build asset rows + persist
        asset_rows = [
            _build_asset_row(signal, enrichment, file_id)
            for signal, enrichment in zip(signals, enrichments)
        ]
        new_count = await _upsert_assets(db, schema, asset_rows)
        total_count = len(asset_rows)
        summary["assets_saved"] = new_count
        summary["assets_updated"] = total_count - new_count

        await _mark_file_status(db, schema, file_id, "processed", total_count)
        await db.commit()

    except Exception as e:
        logger.exception(f"Detection pipeline failed for file {file_id}: {e}")
        summary["errors"].append(str(e))
        try:
            await _mark_file_status(db, schema, file_id, "error")
            await db.commit()
        except Exception:
            pass

    return summary


async def get_detection_stats(
    db: AsyncSession,
    workspace_slug: str,
) -> dict[str, Any]:
    """Return high-level detection stats for the workspace."""
    schema = get_schema_name(workspace_slug)
    try:
        result = await db.execute(text(f"""
            SELECT
                COUNT(*) AS total_assets,
                COUNT(*) FILTER (WHERE is_shadow_ai = true) AS shadow_ai,
                COUNT(*) FILTER (WHERE risk_level IN ('high', 'critical')) AS high_risk,
                COUNT(*) FILTER (WHERE risk_level = 'critical') AS critical_risk,
                COUNT(*) FILTER (WHERE analyst_status = 'pending_review') AS pending_review,
                COUNT(*) FILTER (WHERE analyst_status = 'confirmed') AS confirmed,
                COUNT(DISTINCT category) AS categories,
                MAX(last_seen_at) AS last_seen_at
            FROM "{schema}".discovered_assets
        """))
        row = result.fetchone()
        if row:
            return {
                "total_assets":   row[0],
                "shadow_ai":      row[1],
                "high_risk":      row[2],
                "critical_risk":  row[3],
                "pending_review": row[4],
                "confirmed":      row[5],
                "categories":     row[6],
                "last_seen_at":   row[7].isoformat() if row[7] else None,
            }
    except Exception as e:
        logger.error(f"Detection stats error: {e}")
    return {}


async def get_category_breakdown(
    db: AsyncSession,
    workspace_slug: str,
) -> list[dict[str, Any]]:
    """Assets grouped by category with counts."""
    schema = get_schema_name(workspace_slug)
    try:
        result = await db.execute(text(f"""
            SELECT
                category,
                COUNT(*) AS count,
                COUNT(*) FILTER (WHERE is_shadow_ai) AS shadow_count,
                COUNT(*) FILTER (WHERE risk_level IN ('high','critical')) AS high_risk_count,
                AVG(risk_score)::numeric(4,1) AS avg_risk_score
            FROM "{schema}".discovered_assets
            GROUP BY category
            ORDER BY count DESC
        """))
        return [
            {
                "category": row[0],
                "count": row[1],
                "shadow_count": row[2],
                "high_risk_count": row[3],
                "avg_risk_score": float(row[4]) if row[4] else 0,
            }
            for row in result.fetchall()
        ]
    except Exception as e:
        logger.error(f"Category breakdown error: {e}")
        return []
