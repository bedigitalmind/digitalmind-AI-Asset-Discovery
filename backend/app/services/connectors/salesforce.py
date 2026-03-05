"""
Salesforce connector — discovers Einstein AI, Agentforce, AppExchange AI packages,
Flow AI decisions, and ML models.

Auth:  OAuth2 Connected App — Client Credentials Flow
       POST {instance_url}/services/oauth2/token
       grant_type=client_credentials  |  client_id  |  client_secret

Required config keys:
  instance_url   – e.g. https://mycompany.my.salesforce.com
  client_id      – Connected App Consumer Key
  client_secret  – Connected App Consumer Secret

Optional config keys:
  api_version    – Salesforce API version (default: "60.0")
"""
import logging
import httpx
from .base import DiscoveredAsset, is_ai_related

logger = logging.getLogger(__name__)

# ── Known Einstein / AI features to probe ─────────────────────────────────────

EINSTEIN_STATIC_FEATURES = [
    {
        "id": "sf-einstein-gpt",
        "name": "Einstein Copilot (Generative AI)",
        "asset_type": "einstein_copilot",
        "category": "Generative AI",
        "subcategory": "Copilot",
        "risk_level": "high", "risk_score": 8,
        "description": "Salesforce native generative AI assistant across all Clouds",
    },
    {
        "id": "sf-agentforce",
        "name": "Agentforce AI Agents",
        "asset_type": "agentforce_agent",
        "category": "Generative AI",
        "subcategory": "AI Agents",
        "risk_level": "critical", "risk_score": 9,
        "description": "Autonomous AI agents that perform business tasks (Agentforce 2.0)",
    },
    {
        "id": "sf-einstein-prediction",
        "name": "Einstein Prediction Builder",
        "asset_type": "einstein_prediction",
        "category": "Machine Learning",
        "subcategory": "Predictive AI",
        "risk_level": "medium", "risk_score": 5,
        "description": "No-code ML predictions on Salesforce objects",
    },
    {
        "id": "sf-einstein-analytics",
        "name": "CRM Analytics (Einstein Analytics)",
        "asset_type": "analytics_ai",
        "category": "Analytics AI",
        "subcategory": "BI AI",
        "risk_level": "low", "risk_score": 3,
        "description": "AI-powered analytics dashboards and smart predictions",
    },
    {
        "id": "sf-einstein-vision",
        "name": "Einstein Vision & Language",
        "asset_type": "einstein_vision_nlp",
        "category": "Machine Learning",
        "subcategory": "Computer Vision / NLP",
        "risk_level": "medium", "risk_score": 5,
        "description": "Image classification and NLP API for Salesforce apps",
    },
]

AI_PACKAGE_KEYWORDS = {
    "einstein", "agentforce", "gpt", "openai", "copilot", "ai ", " ai",
    "predict", "intelligence", "vision", "nlp", "language", "chatbot",
    "virtual agent", "automation ai", "ml ", " ml", "neural", "insight",
    "cognitive", "sentiment", "recommendation",
}


# ── Auth ───────────────────────────────────────────────────────────────────────

async def _get_oauth_token(client: httpx.AsyncClient, instance_url: str,
                            client_id: str, client_secret: str) -> str:
    resp = await client.post(
        f"{instance_url}/services/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        raise ValueError(
            f"Salesforce OAuth2 falhou ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()["access_token"]


# ── Discovery helpers ──────────────────────────────────────────────────────────

async def _tooling_query(client: httpx.AsyncClient, instance_url: str,
                          headers: dict, api_version: str, soql: str) -> list[dict]:
    """Execute a Salesforce Tooling API SOQL query, return records list."""
    url = f"{instance_url}/services/data/v{api_version}/tooling/query"
    resp = await client.get(url, params={"q": soql}, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("records", [])
    logger.warning("Tooling query failed %s: %s", resp.status_code, resp.text[:200])
    return []


async def _rest_query(client: httpx.AsyncClient, instance_url: str,
                       headers: dict, api_version: str, soql: str) -> list[dict]:
    """Execute a Salesforce REST API SOQL query."""
    url = f"{instance_url}/services/data/v{api_version}/query"
    resp = await client.get(url, params={"q": soql}, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("records", [])
    logger.warning("REST query failed %s: %s", resp.status_code, resp.text[:200])
    return []


# ── Sub-discoverers ────────────────────────────────────────────────────────────

async def _discover_bots(client, instance_url, headers, api_version, assets):
    """Agentforce / Service Cloud bots (BotDefinition)."""
    records = await _tooling_query(
        client, instance_url, headers, api_version,
        "SELECT Id, Label, Type, Status FROM BotDefinition"
    )
    for r in records:
        bot_type = r.get("Type", "Bot")
        is_agent = "Agent" in bot_type or "agentforce" in bot_type.lower()
        assets.append(DiscoveredAsset(
            external_id=f"sf-bot-{r['Id']}",
            name=f"{'Agentforce Agent' if is_agent else 'Einstein Bot'}: {r.get('Label', r['Id'])}",
            vendor="Salesforce",
            category="Generative AI" if is_agent else "Conversational AI",
            subcategory="AI Agents" if is_agent else "Chatbot",
            asset_type=bot_type,
            platform="salesforce",
            risk_level="critical" if is_agent else "high",
            risk_score=9 if is_agent else 7,
            confidence_score=1.0,
            is_shadow_ai=False,
            source_details={"bot_id": r["Id"], "type": bot_type, "status": r.get("Status")},
            metadata={"source": "BotDefinition"},
        ))


async def _discover_ml_models(client, instance_url, headers, api_version, assets):
    """Einstein Prediction / ML Models (MLModel via Tooling API)."""
    records = await _tooling_query(
        client, instance_url, headers, api_version,
        "SELECT Id, MasterLabel, Algorithm, ModelType, PredictionField FROM MLModel"
    )
    for r in records:
        assets.append(DiscoveredAsset(
            external_id=f"sf-mlmodel-{r['Id']}",
            name=f"ML Model: {r.get('MasterLabel', r['Id'])}",
            vendor="Salesforce",
            category="Machine Learning",
            subcategory="Predictive AI",
            asset_type=r.get("ModelType", "MLModel"),
            platform="salesforce",
            risk_level="medium",
            risk_score=5,
            confidence_score=1.0,
            source_details={
                "model_id": r["Id"],
                "algorithm": r.get("Algorithm"),
                "model_type": r.get("ModelType"),
                "prediction_field": r.get("PredictionField"),
            },
            metadata={"source": "MLModel"},
        ))


async def _discover_flow_ai(client, instance_url, headers, api_version, assets):
    """Flows that contain AI/Einstein decision elements."""
    records = await _tooling_query(
        client, instance_url, headers, api_version,
        "SELECT Id, DeveloperName, MasterLabel, ProcessType, TriggerType "
        "FROM FlowDefinition WHERE ProcessType IN ('AutoLaunchedFlow','Flow') "
        "LIMIT 200"
    )
    ai_flows = [
        r for r in records
        if is_ai_related(r.get("MasterLabel", "") + " " + r.get("DeveloperName", ""))
    ]
    for r in ai_flows:
        assets.append(DiscoveredAsset(
            external_id=f"sf-flow-{r['Id']}",
            name=f"Flow AI: {r.get('MasterLabel', r['Id'])}",
            vendor="Salesforce",
            category="Machine Learning",
            subcategory="AutoML / Flow",
            asset_type="Flow",
            platform="salesforce",
            risk_level="medium",
            risk_score=5,
            confidence_score=0.75,
            is_shadow_ai=False,
            source_details={"flow_id": r["Id"], "process_type": r.get("ProcessType")},
            metadata={"source": "FlowDefinition"},
        ))


async def _discover_packages(client, instance_url, headers, api_version, assets):
    """AppExchange installed packages with AI indicators."""
    records = await _tooling_query(
        client, instance_url, headers, api_version,
        "SELECT Id, SubscriberPackage.Name, SubscriberPackage.NamespacePrefix "
        "FROM InstalledSubscriberPackage LIMIT 200"
    )
    for r in records:
        pkg = r.get("SubscriberPackage") or {}
        pkg_name = pkg.get("Name", "")
        ns = pkg.get("NamespacePrefix", "")
        if not is_ai_related(pkg_name + " " + ns):
            continue
        # Shadow AI: third-party AppExchange AI apps are unsanctioned by default
        assets.append(DiscoveredAsset(
            external_id=f"sf-pkg-{r['Id']}",
            name=f"AppExchange AI Package: {pkg_name}",
            vendor="Salesforce AppExchange",
            category="SaaS AI Tool",
            subcategory="Third-party Plugin",
            asset_type="InstalledPackage",
            platform="salesforce",
            risk_level="high",
            risk_score=7,
            confidence_score=0.85,
            is_shadow_ai=True,   # third-party AI = shadow until confirmed
            source_details={"pkg_id": r["Id"], "namespace": ns},
            metadata={"source": "InstalledSubscriberPackage", "name": pkg_name},
        ))


async def _probe_einstein_static(instance_url: str, headers: dict,
                                  client: httpx.AsyncClient,
                                  api_version: str, assets: list) -> None:
    """
    Check if Einstein features are available by querying the org limits
    and looking for known Einstein-related metadata.
    We add static known features as 'detected via org metadata' entries.
    """
    # Probe: query for any existing EinsteinLMSettings or similar
    resp = await client.get(
        f"{instance_url}/services/data/v{api_version}/limits",
        headers=headers,
    )
    if resp.status_code != 200:
        return

    limits = resp.json()
    # If EinsteinRequestsPerMonth limit exists, Einstein is licensed
    if "EinsteinGPTRequestsPerMonth" in limits or "EinsteinRequestsPerMonth" in limits:
        for feat in EINSTEIN_STATIC_FEATURES[:3]:  # GPT, Prediction, Analytics
            assets.append(DiscoveredAsset(
                external_id=f"sf-static-{feat['id']}",
                name=feat["name"],
                vendor="Salesforce",
                category=feat["category"],
                subcategory=feat["subcategory"],
                asset_type=feat["asset_type"],
                platform="salesforce",
                risk_level=feat["risk_level"],
                risk_score=feat["risk_score"],
                confidence_score=0.9,
                is_shadow_ai=False,
                source_details={"detected_via": "org_limits", "feature": feat["id"]},
                metadata={"source": "OrgLimits"},
            ))


# ── Main entry point ───────────────────────────────────────────────────────────

async def discover(config: dict) -> list[dict]:
    """
    Salesforce AI asset discovery.

    Returns a list of standardised asset dicts compatible with
    ConnectorService._upsert_assets().
    """
    instance_url = config.get("instance_url", "").rstrip("/")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    api_version = config.get("api_version", "60.0")

    if not all([instance_url, client_id, client_secret]):
        raise ValueError(
            "Configuração Salesforce incompleta: "
            "instance_url, client_id e client_secret são obrigatórios"
        )

    assets: list[DiscoveredAsset] = []

    async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
        token = await _get_oauth_token(client, instance_url, client_id, client_secret)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Run all sub-discoverers concurrently would require gather;
        # sequential is simpler and avoids rate-limit bursts
        await _probe_einstein_static(instance_url, headers, client, api_version, assets)
        await _discover_bots(client, instance_url, headers, api_version, assets)
        await _discover_ml_models(client, instance_url, headers, api_version, assets)
        await _discover_flow_ai(client, instance_url, headers, api_version, assets)
        await _discover_packages(client, instance_url, headers, api_version, assets)

    logger.info("Salesforce discovery: %d assets found", len(assets))
    return [a.to_dict() for a in assets]
