"""
SAP connector — discovers SAP AI Core deployments/scenarios, SAP Joule,
and SAP BTP AI services (Document Information Extraction, Business Entity
Recognition, etc.)

Auth:  OAuth2 Client Credentials (SAP BTP Service Key)
       POST {token_url}  |  grant_type=client_credentials  |  client_id  |  client_secret

Required config keys:
  token_url         – BTP XSUAA token URL
                      e.g. https://my-subaccount.authentication.eu10.hana.ondemand.com/oauth/token
  client_id         – BTP service key clientid
  client_secret     – BTP service key clientsecret
  ai_core_api_url   – SAP AI Core API base URL
                      e.g. https://api.ai.prod.eu-central-1.aws.ml.hana.ondemand.com

Optional config keys:
  resource_group    – SAP AI Core resource group (default: "default")
"""
import logging
import httpx
from .base import DiscoveredAsset

logger = logging.getLogger(__name__)

# ── Known SAP BTP AI services ─────────────────────────────────────────────────

SAP_BTP_AI_SERVICES = [
    {
        "id": "sap-doc-info-extraction",
        "name": "Document Information Extraction (BTP)",
        "category": "Machine Learning",
        "subcategory": "Document AI",
        "risk_level": "medium", "risk_score": 5,
    },
    {
        "id": "sap-business-entity-recognition",
        "name": "Business Entity Recognition (BTP)",
        "category": "Machine Learning",
        "subcategory": "NLP",
        "risk_level": "medium", "risk_score": 5,
    },
    {
        "id": "sap-data-attribute-recommendation",
        "name": "Data Attribute Recommendation (BTP)",
        "category": "Machine Learning",
        "subcategory": "Predictive AI",
        "risk_level": "low", "risk_score": 3,
    },
    {
        "id": "sap-joule",
        "name": "SAP Joule (Generative AI Copilot)",
        "category": "Generative AI",
        "subcategory": "Copilot",
        "risk_level": "high", "risk_score": 8,
    },
    {
        "id": "sap-ai-core-foundation",
        "name": "SAP AI Core (Foundation Model Platform)",
        "category": "AI Infrastructure",
        "subcategory": "LLM Platform",
        "risk_level": "high", "risk_score": 7,
    },
]

# Model executable IDs that indicate generative AI workloads
GENAI_EXECUTABLE_PATTERNS = {
    "gpt", "llm", "foundation", "generative", "text-generation",
    "chat", "instruct", "embedding", "claude", "gemini", "llama",
    "mistral", "falcon", "titan", "palm",
}

# Risk mapping by deployment status
DEPLOYMENT_RISK_MAP = {
    "RUNNING":  ("high",   7),
    "STOPPED":  ("low",    3),
    "UNKNOWN":  ("medium", 5),
    "DEAD":     ("low",    2),
    "PENDING":  ("medium", 4),
}


# ── Auth ───────────────────────────────────────────────────────────────────────

async def _get_token(client: httpx.AsyncClient, token_url: str,
                      client_id: str, client_secret: str) -> str:
    resp = await client.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        raise ValueError(
            f"SAP BTP OAuth2 falhou ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()["access_token"]


# ── AI Core API helpers ────────────────────────────────────────────────────────

async def _aicore_get(client: httpx.AsyncClient, api_url: str,
                       path: str, headers: dict,
                       resource_group: str = "default") -> dict | list | None:
    url = f"{api_url}{path}"
    rg_headers = {**headers, "AI-Resource-Group": resource_group}
    resp = await client.get(url, headers=rg_headers)
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 404:
        logger.debug("SAP AI Core: %s not found", path)
        return None
    logger.warning("SAP AI Core %s → %s: %s", path, resp.status_code, resp.text[:200])
    return None


# ── Sub-discoverers ────────────────────────────────────────────────────────────

async def _discover_scenarios(client, api_url, headers, resource_group, assets):
    """Discover SAP AI Core registered scenarios (projects/use-cases)."""
    data = await _aicore_get(client, api_url, "/v2/lm/scenarios", headers, resource_group)
    if not data:
        return
    items = data if isinstance(data, list) else data.get("resources", [])
    for item in items:
        scenario_id = item.get("id", item.get("scenarioId", "unknown"))
        name = item.get("name", scenario_id)
        description = item.get("description", "")
        assets.append(DiscoveredAsset(
            external_id=f"sap-scenario-{scenario_id}",
            name=f"SAP AI Core Scenario: {name}",
            vendor="SAP",
            category="AI Infrastructure",
            subcategory="ML Scenario",
            asset_type="ai_core_scenario",
            platform="sap",
            risk_level="medium",
            risk_score=5,
            confidence_score=1.0,
            is_shadow_ai=False,
            source_details={
                "scenario_id": scenario_id,
                "description": description,
                "resource_group": resource_group,
            },
            metadata={"source": "sap_ai_core.scenarios"},
        ))


async def _discover_deployments(client, api_url, headers, resource_group, assets):
    """Discover running AI model deployments (the most critical finding)."""
    data = await _aicore_get(client, api_url, "/v2/lm/deployments", headers, resource_group)
    if not data:
        return
    items = data if isinstance(data, list) else data.get("resources", [])
    for item in items:
        dep_id = item.get("id", item.get("deploymentId", "unknown"))
        status = item.get("status", "UNKNOWN").upper()
        executable_id = item.get("executableId", "")
        scenario_id = item.get("scenarioId", "")
        configuration_name = item.get("configurationName", "")

        # Determine if this is a generative AI workload
        combined = (executable_id + " " + configuration_name + " " + scenario_id).lower()
        is_genai = any(kw in combined for kw in GENAI_EXECUTABLE_PATTERNS)

        risk_level, risk_score = DEPLOYMENT_RISK_MAP.get(status, ("medium", 5))
        if is_genai and status == "RUNNING":
            risk_level, risk_score = "critical", 9

        assets.append(DiscoveredAsset(
            external_id=f"sap-deployment-{dep_id}",
            name=f"SAP AI Core Deployment: {executable_id or dep_id}",
            vendor="SAP",
            category="Generative AI" if is_genai else "AI Infrastructure",
            subcategory="LLM Deployment" if is_genai else "ML Deployment",
            asset_type="ai_core_deployment",
            platform="sap",
            risk_level=risk_level,
            risk_score=risk_score,
            confidence_score=1.0,
            is_shadow_ai=False,
            source_details={
                "deployment_id": dep_id,
                "status": status,
                "executable_id": executable_id,
                "scenario_id": scenario_id,
                "configuration_name": configuration_name,
                "resource_group": resource_group,
                "is_genai": is_genai,
            },
            metadata={"source": "sap_ai_core.deployments"},
        ))


async def _discover_executions(client, api_url, headers, resource_group, assets):
    """Discover recent AI Core training executions."""
    data = await _aicore_get(client, api_url, "/v2/lm/executions", headers, resource_group)
    if not data:
        return
    items = data if isinstance(data, list) else data.get("resources", [])
    # Only surface RUNNING executions (training jobs in progress)
    for item in items:
        if item.get("status", "").upper() != "RUNNING":
            continue
        exec_id = item.get("id", "unknown")
        executable_id = item.get("executableId", "")
        assets.append(DiscoveredAsset(
            external_id=f"sap-execution-{exec_id}",
            name=f"SAP AI Core Training Execution: {executable_id or exec_id}",
            vendor="SAP",
            category="AI Infrastructure",
            subcategory="ML Training",
            asset_type="ai_core_execution",
            platform="sap",
            risk_level="medium",
            risk_score=5,
            confidence_score=1.0,
            is_shadow_ai=False,
            source_details={
                "execution_id": exec_id,
                "executable_id": executable_id,
                "resource_group": resource_group,
            },
            metadata={"source": "sap_ai_core.executions"},
        ))


async def _check_btp_ai_services(client: httpx.AsyncClient, api_url: str,
                                   headers: dict, assets: list) -> None:
    """
    Probe for SAP BTP AI Service bindings by checking AI Core metadata endpoint.
    If AI Core responds at all, SAP AI Foundation is licensed — add static entries.
    """
    resp = await client.get(f"{api_url}/v2/lm/scenarios", headers=headers)
    if resp.status_code in (200, 404):  # 404 = no scenarios but AI Core is there
        # AI Core is licensed — add BTP AI services as detected
        for svc in SAP_BTP_AI_SERVICES:
            assets.append(DiscoveredAsset(
                external_id=f"sap-btp-{svc['id']}",
                name=svc["name"],
                vendor="SAP",
                category=svc["category"],
                subcategory=svc["subcategory"],
                asset_type="btp_ai_service",
                platform="sap",
                risk_level=svc["risk_level"],
                risk_score=svc["risk_score"],
                confidence_score=0.85,
                is_shadow_ai=False,
                source_details={"detected_via": "ai_core_presence", "service_id": svc["id"]},
                metadata={"source": "sap_btp_ai_services"},
            ))


# ── Main entry point ───────────────────────────────────────────────────────────

async def discover(config: dict) -> list[dict]:
    """
    SAP AI Core + BTP AI Services discovery.

    Returns a list of standardised asset dicts compatible with
    ConnectorService._upsert_assets().
    """
    token_url = config.get("token_url", "")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    ai_core_api_url = config.get("ai_core_api_url", "").rstrip("/")
    resource_group = config.get("resource_group", "default")

    if not all([token_url, client_id, client_secret, ai_core_api_url]):
        raise ValueError(
            "Configuração SAP incompleta: "
            "token_url, client_id, client_secret e ai_core_api_url são obrigatórios"
        )

    assets: list[DiscoveredAsset] = []

    async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
        token = await _get_token(client, token_url, client_id, client_secret)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Probe BTP AI Services presence first
        await _check_btp_ai_services(client, ai_core_api_url, headers, assets)

        # Discover AI Core workloads
        await _discover_scenarios(client, ai_core_api_url, headers, resource_group, assets)
        await _discover_deployments(client, ai_core_api_url, headers, resource_group, assets)
        await _discover_executions(client, ai_core_api_url, headers, resource_group, assets)

    logger.info("SAP AI Core discovery: %d assets found", len(assets))
    return [a.to_dict() for a in assets]
