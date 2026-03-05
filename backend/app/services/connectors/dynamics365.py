"""
Dynamics 365 connector — discovers Copilot for Sales/Service/Finance,
Power Virtual Agents (Copilot Studio), AI Builder models, and
Power Automate AI flows.

Auth:  Azure AD OAuth2 — Client Credentials
       POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
       grant_type=client_credentials  |  client_id  |  client_secret
       scope = https://{environment_url}/.default

Required config keys:
  tenant_id         – Azure AD tenant ID
  client_id         – App registration client ID (needs Dynamics CRM user_impersonation)
  client_secret     – App registration client secret
  environment_url   – Dynamics 365 environment URL
                      e.g. https://myorg.crm.dynamics.com

Optional config keys:
  api_version       – Dataverse OData API version (default: "9.2")
"""
import logging
import httpx
from .base import DiscoveredAsset, is_ai_related

logger = logging.getLogger(__name__)

AZURE_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

# ── Dataverse tables that hold AI assets ──────────────────────────────────────

D365_AI_TABLES = [
    # (entity, select_fields, label, category, subcategory, risk_level, risk_score, is_shadow)
    (
        "bots",
        "botid,name,schemaname,statecode,bottype",
        "Power Virtual Agent / Copilot Studio Bot",
        "Conversational AI", "Chatbot",
        "high", 7, False,
    ),
    (
        "msdyn_aimodels",
        "msdyn_aimodelid,msdyn_name,msdyn_trainrunid,statecode,msdyn_modeltype",
        "AI Builder Model",
        "Machine Learning", "AutoML",
        "medium", 5, False,
    ),
    (
        "msdyn_aiconfigurations",
        "msdyn_aiconfigurationid,msdyn_name,statecode,msdyn_modelcreatedon",
        "AI Builder Configuration",
        "Machine Learning", "AI Configuration",
        "low", 3, False,
    ),
    (
        "msdyn_copilotinteractions",
        "msdyn_copilotinteractionid,msdyn_name,statecode",
        "Copilot Interaction Log",
        "Generative AI", "Copilot",
        "high", 7, False,
    ),
]

# Copilot features that may be enabled at the org level (static check)
COPILOT_ORG_FEATURES = [
    {
        "id": "d365-copilot-sales",
        "name": "Copilot for Sales",
        "category": "Generative AI",
        "subcategory": "Copilot",
        "risk_level": "high", "risk_score": 8,
        "setting_key": "msdyn_CopilotForSalesEnabled",
    },
    {
        "id": "d365-copilot-service",
        "name": "Copilot for Customer Service",
        "category": "Generative AI",
        "subcategory": "Copilot",
        "risk_level": "high", "risk_score": 8,
        "setting_key": "msdyn_CopilotForCustomerServiceEnabled",
    },
    {
        "id": "d365-copilot-finance",
        "name": "Copilot for Finance",
        "category": "Generative AI",
        "subcategory": "Copilot",
        "risk_level": "high", "risk_score": 7,
        "setting_key": "msdyn_CopilotForFinanceEnabled",
    },
    {
        "id": "d365-copilot-field-service",
        "name": "Copilot for Field Service",
        "category": "Generative AI",
        "subcategory": "Copilot",
        "risk_level": "medium", "risk_score": 6,
        "setting_key": "msdyn_CopilotForFieldServiceEnabled",
    },
    {
        "id": "d365-power-virtual-agents",
        "name": "Power Virtual Agents / Copilot Studio",
        "category": "Conversational AI",
        "subcategory": "Chatbot Platform",
        "risk_level": "high", "risk_score": 7,
        "setting_key": None,  # Always add if bots table accessible
    },
]

# AI Builder model type display names
AIBUILDER_MODEL_TYPES = {
    "100000000": "Category Classification",
    "100000001": "Entity Extraction",
    "100000002": "Form Processing",
    "100000003": "Object Detection",
    "100000004": "Prediction",
    "100000005": "Sentiment Analysis",
    "100000006": "Language Detection",
    "100000007": "Key Phrase Extraction",
    "100000009": "Text Recognition (OCR)",
    "100000010": "Business Card Reader",
    "100000012": "Text Translation",
    "100000013": "Document Processing",
    "100000014": "Receipt Processing",
    "100000015": "Invoice Processing",
    "100000016": "ID Reader",
    "100000017": "Azure OpenAI",
    "100000018": "Custom Prompt (GPT)",
}


# ── Auth ───────────────────────────────────────────────────────────────────────

async def _get_token(client: httpx.AsyncClient, tenant_id: str,
                      client_id: str, client_secret: str,
                      environment_url: str) -> str:
    scope = f"{environment_url.rstrip('/')}/.default"
    url = AZURE_TOKEN_URL.format(tenant_id=tenant_id)
    resp = await client.post(url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    })
    if resp.status_code != 200:
        raise ValueError(
            f"Dynamics 365 Azure AD OAuth2 falhou ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()["access_token"]


# ── OData query helper ─────────────────────────────────────────────────────────

async def _odata_query(client: httpx.AsyncClient, environment_url: str,
                        headers: dict, entity: str, select: str,
                        api_version: str = "9.2",
                        top: int = 200) -> list[dict]:
    url = f"{environment_url.rstrip('/')}/api/data/v{api_version}/{entity}"
    resp = await client.get(url, headers=headers, params={
        "$select": select,
        "$top": str(top),
    })
    if resp.status_code == 200:
        return resp.json().get("value", [])
    if resp.status_code == 403:
        logger.warning("Dynamics 365: no read access to entity '%s'", entity)
        return []
    if resp.status_code == 404:
        logger.debug("Dynamics 365: entity '%s' not found", entity)
        return []
    logger.warning("Dynamics 365 entity '%s' → %s: %s", entity, resp.status_code, resp.text[:200])
    return []


# ── Sub-discoverers ────────────────────────────────────────────────────────────

async def _discover_entity_table(client, env_url, headers, api_version, assets,
                                   entity, select, label, category, subcategory,
                                   risk_level, risk_score, is_shadow):
    """Generic Dataverse entity → DiscoveredAsset mapper."""
    records = await _odata_query(client, env_url, headers, entity, select, api_version)
    for r in records:
        # Best-effort name extraction (varies per entity)
        rec_id = (
            r.get("botid") or r.get("msdyn_aimodelid") or
            r.get("msdyn_aiconfigurationid") or r.get("msdyn_copilotinteractionid") or
            r.get("workflowid") or "unknown"
        )
        rec_name = (
            r.get("name") or r.get("msdyn_name") or
            r.get("displayname") or rec_id
        )
        statecode = r.get("statecode", 0)
        is_active = statecode == 0  # 0 = Active in Dataverse

        # For AI Builder: refine risk by model type
        model_type_raw = str(r.get("msdyn_modeltype", ""))
        model_type_label = AIBUILDER_MODEL_TYPES.get(model_type_raw, model_type_raw)
        is_genai_aibuilder = model_type_raw in ("100000017", "100000018")  # Azure OpenAI / GPT
        if is_genai_aibuilder:
            risk_level, risk_score = "critical", 9
            category = "Generative AI"
            subcategory = "AI Builder (GPT)"

        assets.append(DiscoveredAsset(
            external_id=f"d365-{entity}-{rec_id}",
            name=f"{label}: {rec_name}",
            vendor="Microsoft",
            category=category,
            subcategory=subcategory,
            asset_type=entity,
            platform="dynamics365",
            risk_level=risk_level,
            risk_score=risk_score,
            confidence_score=1.0,
            is_shadow_ai=is_shadow,
            source_details={
                "entity": entity,
                "record_id": rec_id,
                "statecode": statecode,
                "is_active": is_active,
                "model_type": model_type_label or None,
            },
            metadata={"source": f"dynamics365.{entity}"},
        ))


async def _discover_copilot_org_settings(client, env_url, headers,
                                          api_version, assets):
    """
    Query org settings to detect which Copilot features are enabled.
    Reads from the 'organizations' entity (single row in D365).
    """
    orgs = await _odata_query(
        client, env_url, headers, "organizations",
        select=(
            "organizationid,name,"
            "iscopilotforsalesenabled,isaisuggestionsforcontactsenabled,"
            "isofficegraphshareddocumentenabled,iscopilot"
        ),
        api_version=api_version,
        top=1,
    )
    if not orgs:
        return

    org = orgs[0]
    org_id = org.get("organizationid", "unknown")
    org_name = org.get("name", "Dynamics 365 Org")

    # Check for any Copilot-related true flags
    copilot_flags = {k: v for k, v in org.items()
                     if isinstance(v, bool) and v and
                     any(kw in k.lower() for kw in ["copilot", "ai", "intelligence", "suggest"])}

    if copilot_flags:
        assets.append(DiscoveredAsset(
            external_id=f"d365-org-copilot-{org_id}",
            name=f"Copilot Features Enabled: {org_name}",
            vendor="Microsoft",
            category="Generative AI",
            subcategory="Copilot",
            asset_type="organization_copilot_config",
            platform="dynamics365",
            risk_level="high",
            risk_score=8,
            confidence_score=0.9,
            is_shadow_ai=False,
            source_details={
                "org_id": org_id,
                "enabled_flags": list(copilot_flags.keys()),
            },
            metadata={"source": "dynamics365.organizations"},
        ))


async def _discover_power_automate_ai_flows(client, env_url, headers,
                                             api_version, assets):
    """Discover Power Automate workflows (flows) that use AI actions."""
    records = await _odata_query(
        client, env_url, headers, "workflows",
        select="workflowid,name,statecode,category,description",
        api_version=api_version,
        top=300,
    )
    for r in records:
        name = r.get("name", "")
        description = r.get("description", "")
        if not is_ai_related(name + " " + description):
            continue
        wf_id = r.get("workflowid", "unknown")
        assets.append(DiscoveredAsset(
            external_id=f"d365-workflow-{wf_id}",
            name=f"Power Automate AI Flow: {name}",
            vendor="Microsoft",
            category="Machine Learning",
            subcategory="AI Automation",
            asset_type="workflow_ai",
            platform="dynamics365",
            risk_level="medium",
            risk_score=5,
            confidence_score=0.80,
            is_shadow_ai=False,
            source_details={
                "workflow_id": wf_id,
                "statecode": r.get("statecode"),
                "category": r.get("category"),
            },
            metadata={"source": "dynamics365.workflows", "description": description[:200]},
        ))


# ── Main entry point ───────────────────────────────────────────────────────────

async def discover(config: dict) -> list[dict]:
    """
    Dynamics 365 / Power Platform AI asset discovery.

    Returns a list of standardised asset dicts compatible with
    ConnectorService._upsert_assets().
    """
    tenant_id = config.get("tenant_id", "")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    environment_url = config.get("environment_url", "").rstrip("/")
    api_version = config.get("api_version", "9.2")

    if not all([tenant_id, client_id, client_secret, environment_url]):
        raise ValueError(
            "Configuração Dynamics 365 incompleta: "
            "tenant_id, client_id, client_secret e environment_url são obrigatórios"
        )

    assets: list[DiscoveredAsset] = []

    async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
        token = await _get_token(client, tenant_id, client_id, client_secret, environment_url)
        headers = {
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Prefer": "odata.maxpagesize=200",
        }

        # 1. Discover each Dataverse AI entity
        for (entity, select, label, category, subcategory,
             risk_level, risk_score, is_shadow) in D365_AI_TABLES:
            await _discover_entity_table(
                client, environment_url, headers, api_version, assets,
                entity, select, label, category, subcategory,
                risk_level, risk_score, is_shadow,
            )

        # 2. Org-level Copilot settings
        await _discover_copilot_org_settings(client, environment_url, headers, api_version, assets)

        # 3. Power Automate flows with AI actions
        await _discover_power_automate_ai_flows(client, environment_url, headers, api_version, assets)

    logger.info("Dynamics 365 discovery: %d assets found", len(assets))
    return [a.to_dict() for a in assets]
