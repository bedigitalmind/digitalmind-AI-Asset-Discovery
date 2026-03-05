"""
LLM client wrapper — Anthropic Claude (ADR-009).
All AI enrichment calls go through this module for consistent
error handling, retry logic, and future model swaps.
"""
import asyncio
import logging
from typing import Any
from anthropic import AsyncAnthropic, APIError, RateLimitError

from .config import get_settings
settings = get_settings()

logger = logging.getLogger(__name__)

# Single shared client (thread-safe)
_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# ─── System prompt (reused across calls — benefits from prompt caching) ───────

SYSTEM_PROMPT = """You are an expert AI asset analyst at a cybersecurity and AI governance firm.
Your job is to analyze assets discovered in enterprise infrastructure and:
1. Confirm or refine their AI asset classification
2. Assess their risk profile in a corporate governance context
3. Identify whether they constitute Shadow AI (unsanctioned AI tools)
4. Provide a concise, actionable description for security analysts

You must respond ONLY with valid JSON matching the schema provided.
Never include markdown code fences in your response. Output raw JSON only."""


# ─── Core enrichment call ─────────────────────────────────────────────────────

async def enrich_asset(
    asset_name: str,
    vendor: str | None,
    category: str,
    subcategory: str | None,
    raw_context: dict[str, Any],
    retries: int = 3,
) -> dict[str, Any]:
    """
    Enrich a single discovered asset with Claude.
    Returns a dict with enriched fields or falls back gracefully.
    """
    prompt = f"""Analyze this AI asset discovered in enterprise infrastructure:

Asset name: {asset_name}
Vendor: {vendor or 'Unknown'}
Detected category: {category}
Detected subcategory: {subcategory or 'Unknown'}
Raw context: {str(raw_context)[:800]}

Respond with JSON matching this exact schema:
{{
  "confirmed_category": "string (one of: Conversational AI, Copilots, AI Agents, Embedded SaaS AI, ERP/CRM AI, AI APIs & SDKs, Proprietary Models & Infrastructure)",
  "confirmed_subcategory": "string",
  "vendor_confirmed": "string",
  "description": "string (2-3 sentences, analyst-friendly)",
  "is_shadow_ai": boolean,
  "shadow_ai_reason": "string or null",
  "risk_level": "string (one of: low, medium, high, critical)",
  "risk_score": integer (1-10),
  "risk_justification": "string (1-2 sentences)",
  "confidence_score": number (0.0-1.0),
  "recommended_action": "string (one of: monitor, review_with_owner, request_approval, block_immediately)"
}}"""

    client = get_client()
    last_err: Exception | None = None

    for attempt in range(retries):
        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            content = response.content[0].text.strip()
            # Strip markdown fences if model adds them
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except RateLimitError:
            wait = 2 ** attempt
            logger.warning(f"Rate limit hit, retrying in {wait}s (attempt {attempt+1})")
            await asyncio.sleep(wait)
            last_err = None  # will retry
        except (APIError, Exception) as e:
            last_err = e
            logger.error(f"LLM enrichment error on attempt {attempt+1}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1)

    logger.error(f"LLM enrichment failed after {retries} attempts: {last_err}")
    return {}  # graceful degradation — caller keeps taxonomy-based values


async def batch_enrich_assets(
    assets: list[dict[str, Any]],
    concurrency: int = 3,
) -> list[dict[str, Any]]:
    """
    Enrich a list of assets with controlled concurrency to respect rate limits.
    Returns list of enrichment results in the same order as input.
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict[str, Any]] = [{}] * len(assets)

    async def _enrich_one(idx: int, asset: dict[str, Any]) -> None:
        async with semaphore:
            enriched = await enrich_asset(
                asset_name=asset.get("name", ""),
                vendor=asset.get("vendor"),
                category=asset.get("category", ""),
                subcategory=asset.get("subcategory"),
                raw_context=asset.get("raw_data", {}),
            )
            results[idx] = enriched

    await asyncio.gather(*[_enrich_one(i, a) for i, a in enumerate(assets)])
    return results


# ─── File-based detection call ────────────────────────────────────────────────

async def analyze_log_chunk(
    log_type: str,
    chunk: str,
    retries: int = 2,
) -> list[dict[str, Any]]:
    """
    Ask Claude to extract AI asset signals from a chunk of raw log text.
    Used by the parser engine for file-based discovery.
    Returns a list of potential asset signals.
    """
    prompt = f"""You are analyzing a chunk of enterprise {log_type} logs to identify AI tools in use.

Log chunk (excerpt):
{chunk[:3000]}

Extract ALL references to AI tools, AI services, AI APIs, or AI-powered SaaS applications.
For each one found, respond with a JSON array. If nothing is found, return an empty array [].

Each item in the array must match:
{{
  "name": "string",
  "vendor": "string or null",
  "category": "string",
  "signal_type": "string (e.g. domain_access, api_call, package_import, process_name)",
  "signal_value": "string (the actual URL, domain, package name, etc.)",
  "confidence_score": number (0.0-1.0)
}}

Output raw JSON array only. No markdown."""

    client = get_client()
    for attempt in range(retries):
        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            content = response.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            parsed = json.loads(content)
            return parsed if isinstance(parsed, list) else []
        except Exception as e:
            logger.error(f"Log analysis error attempt {attempt+1}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1)
    return []
