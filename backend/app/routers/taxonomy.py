from fastapi import APIRouter
from ..core.taxonomy import get_taxonomy_summary, ALL_ENTRIES, CATEGORIES

router = APIRouter(prefix="/taxonomy", tags=["Taxonomy"])


@router.get("")
async def get_taxonomy():
    """Return full taxonomy summary."""
    return get_taxonomy_summary()


@router.get("/categories")
async def list_categories():
    return [{"id": k, "label": v} for k, v in CATEGORIES.items()]


@router.get("/entries")
async def list_entries(category: str | None = None):
    entries = ALL_ENTRIES if not category else [e for e in ALL_ENTRIES if e.category == category]
    return {
        "total": len(entries),
        "items": [
            {
                "id": e.id, "name": e.name, "vendor": e.vendor,
                "category": e.category, "subcategory": e.subcategory,
                "risk_level": e.risk_level, "risk_score": e.risk_score,
                "description": e.description, "is_saas": e.is_saas,
                "detection_signals": {
                    "domains": e.domains,
                    "api_endpoints": e.api_endpoints,
                    "package_names": e.package_names,
                    "process_names": e.process_names,
                    "azure_resource_types": e.azure_resource_types,
                }
            }
            for e in entries
        ]
    }
