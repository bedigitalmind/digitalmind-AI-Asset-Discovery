"""
ServiceNow connector — discovers Now Intelligence, Virtual Agent, ML Solutions,
Document Intelligence, and AI Platform activities.

Auth:  Basic Authentication (username + password) — most common for service accounts
       OR OAuth2 (client_id + client_secret + token_url) — for production

Required config keys:
  instance_url  – e.g. https://mycompany.service-now.com
  username      – Service account username
  password      – Service account password

Optional config keys:
  use_oauth     – "true" to switch to OAuth2 (requires client_id + client_secret)
  client_id     – OAuth2 client ID
  client_secret – OAuth2 client secret
"""
import base64
import logging
import httpx
from .base import DiscoveredAsset, is_ai_related

logger = logging.getLogger(__name__)

# ── ServiceNow table → asset mapping ──────────────────────────────────────────

SN_AI_TABLES = [
    # (table, name_field, label, category, subcategory, risk_level, risk_score, is_shadow)
    (
        "sys_virtual_agent_topic",
        "name",
        "Virtual Agent Topic",
        "Conversational AI", "Chatbot / Virtual Agent",
        "medium", 5, False,
    ),
    (
        "ml_solution",
        "name",
        "Now Intelligence ML Solution",
        "Machine Learning", "Predictive AI",
        "high", 7, False,
    ),
    (
        "sn_aipf_activity_definition",
        "name",
        "AI Platform Activity",
        "Machine Learning", "AI Automation",
        "medium", 5, False,
    ),
    (
        "sys_document_intelligence_extraction",
        "name",
        "Document Intelligence",
        "Machine Learning", "Document AI",
        "medium", 5, False,
    ),
    (
        "sn_si_skill",
        "name",
        "Now Intelligence Skill",
        "Machine Learning", "Intelligent Automation",
        "low", 3, False,
    ),
    (
        "sn_aca_configuration",
        "name",
        "Assignment Intelligence Config",
        "Machine Learning", "AutoML",
        "medium", 5, False,
    ),
]

# Third-party AI integrations (scanned from sys_plugins / v_plugin table)
AI_PLUGIN_KEYWORDS = {
    "einstein", "openai", "gpt", "azure ai", "ml", "intelligence",
    "chatgpt", "copilot", "ai assist", "nlp", "predict", "cognitive",
    "sentiment", "generative",
}


# ── Auth ───────────────────────────────────────────────────────────────────────

def _basic_headers(username: str, password: str) -> dict:
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _oauth_token(client: httpx.AsyncClient, instance_url: str,
                        client_id: str, client_secret: str) -> str:
    resp = await client.post(
        f"{instance_url}/oauth_token.do",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        raise ValueError(
            f"ServiceNow OAuth2 falhou ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()["access_token"]


# ── Table query helper ─────────────────────────────────────────────────────────

async def _table_query(client: httpx.AsyncClient, instance_url: str,
                        headers: dict, table: str,
                        fields: str = "sys_id,name,sys_created_on",
                        limit: int = 200) -> list[dict]:
    url = f"{instance_url}/api/now/table/{table}"
    resp = await client.get(url, headers=headers, params={
        "sysparm_fields": fields,
        "sysparm_limit": str(limit),
        "sysparm_display_value": "true",
    })
    if resp.status_code == 200:
        return resp.json().get("result", [])
    if resp.status_code == 403:
        logger.warning("ServiceNow: no read access to table '%s'", table)
        return []
    if resp.status_code == 404:
        logger.debug("ServiceNow: table '%s' not found (plugin not installed)", table)
        return []
    logger.warning("ServiceNow table '%s' error %s", table, resp.status_code)
    return []


# ── Sub-discoverers ────────────────────────────────────────────────────────────

async def _discover_ai_tables(client, instance_url, headers, assets):
    """Query each known AI table and create asset records."""
    for (table, name_field, label, category, subcategory,
         risk_level, risk_score, is_shadow) in SN_AI_TABLES:
        records = await _table_query(
            client, instance_url, headers, table,
            fields=f"sys_id,{name_field},sys_created_on,sys_updated_on",
        )
        for r in records:
            record_name = r.get(name_field) or r.get("name") or r.get("sys_id", "Unknown")
            if isinstance(record_name, dict):
                record_name = record_name.get("display_value", str(record_name))
            assets.append(DiscoveredAsset(
                external_id=f"sn-{table}-{r['sys_id']}",
                name=f"{label}: {record_name}",
                vendor="ServiceNow",
                category=category,
                subcategory=subcategory,
                asset_type=table,
                platform="servicenow",
                risk_level=risk_level,
                risk_score=risk_score,
                confidence_score=1.0,
                is_shadow_ai=is_shadow,
                source_details={
                    "sys_id": r["sys_id"],
                    "table": table,
                    "created_on": r.get("sys_created_on"),
                },
                metadata={"source": f"servicenow.{table}"},
            ))


async def _discover_copilot_plugin(client, instance_url, headers, assets):
    """Check for Now Assist / Generative AI plugin activation."""
    # Now Assist for ITSM / HR / CSM is tracked via sn_gai_configuration table
    records = await _table_query(
        client, instance_url, headers, "sn_gai_configuration",
        fields="sys_id,name,llm_provider,active,scope",
        limit=50,
    )
    for r in records:
        is_active = str(r.get("active", "false")).lower() in ("true", "1", "yes")
        provider = r.get("llm_provider", {})
        if isinstance(provider, dict):
            provider = provider.get("display_value", "Unknown")
        record_name = r.get("name") or "Now Assist Configuration"
        if isinstance(record_name, dict):
            record_name = record_name.get("display_value", "Now Assist Configuration")
        assets.append(DiscoveredAsset(
            external_id=f"sn-gai-{r['sys_id']}",
            name=f"Now Assist (Generative AI): {record_name}",
            vendor="ServiceNow",
            category="Generative AI",
            subcategory="Copilot",
            asset_type="sn_gai_configuration",
            platform="servicenow",
            risk_level="high" if is_active else "medium",
            risk_score=8 if is_active else 5,
            confidence_score=1.0,
            is_shadow_ai=False,
            source_details={
                "sys_id": r["sys_id"],
                "llm_provider": provider,
                "active": is_active,
                "scope": r.get("scope"),
            },
            metadata={"source": "sn_gai_configuration"},
        ))


async def _discover_third_party_integrations(client, instance_url, headers, assets):
    """Scan active integrations / spokes with AI indicators."""
    records = await _table_query(
        client, instance_url, headers, "sys_hub_spoke",
        fields="sys_id,name,scope,active",
        limit=300,
    )
    for r in records:
        name = r.get("name", "")
        if isinstance(name, dict):
            name = name.get("display_value", "")
        scope = r.get("scope", "")
        if isinstance(scope, dict):
            scope = scope.get("display_value", "")
        if not is_ai_related(name + " " + scope):
            continue
        is_active = str(r.get("active", "false")).lower() in ("true", "1", "yes")
        assets.append(DiscoveredAsset(
            external_id=f"sn-spoke-{r['sys_id']}",
            name=f"Integration Hub Spoke (AI): {name}",
            vendor="ServiceNow / Third-party",
            category="SaaS AI Tool",
            subcategory="Integration Spoke",
            asset_type="sys_hub_spoke",
            platform="servicenow",
            risk_level="high",
            risk_score=7,
            confidence_score=0.80,
            is_shadow_ai=True,  # third-party integration = potential shadow AI
            source_details={
                "sys_id": r["sys_id"],
                "active": is_active,
                "scope": scope,
            },
            metadata={"source": "sys_hub_spoke", "name": name},
        ))


# ── Main entry point ───────────────────────────────────────────────────────────

async def discover(config: dict) -> list[dict]:
    """
    ServiceNow AI asset discovery.

    Returns a list of standardised asset dicts compatible with
    ConnectorService._upsert_assets().
    """
    instance_url = config.get("instance_url", "").rstrip("/")
    username = config.get("username", "")
    password = config.get("password", "")
    use_oauth = str(config.get("use_oauth", "false")).lower() == "true"
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")

    if not instance_url:
        raise ValueError("Configuração ServiceNow incompleta: instance_url é obrigatório")

    if use_oauth:
        if not all([client_id, client_secret]):
            raise ValueError("ServiceNow OAuth2 requer client_id e client_secret")
    else:
        if not all([username, password]):
            raise ValueError("ServiceNow Basic Auth requer username e password")

    assets: list[DiscoveredAsset] = []

    async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
        if use_oauth:
            token = await _oauth_token(client, instance_url, client_id, client_secret)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        else:
            headers = _basic_headers(username, password)

        await _discover_ai_tables(client, instance_url, headers, assets)
        await _discover_copilot_plugin(client, instance_url, headers, assets)
        await _discover_third_party_integrations(client, instance_url, headers, assets)

    logger.info("ServiceNow discovery: %d assets found", len(assets))
    return [a.to_dict() for a in assets]
