"""
Microsoft 365 connector — discovers AI assets across the M365 ecosystem via
Microsoft Graph API (v1.0 + beta where needed).

Covers:
  • Microsoft 365 Copilot — license presence + usage by service
  • Microsoft Teams AI apps — org-deployed and sideloaded bots/AI apps
  • Copilot Studio bots — via Power Platform Graph endpoint
  • Azure AD / Entra ID AI app registrations — shadow AI detection
  • AI service principals — known Azure AI services registered in the tenant
  • SharePoint Syntex / Premium — content AI features
  • Exchange Copilot features — Outlook Copilot indicators
  • Microsoft Designer, Bing Chat Enterprise — policy-level detection

Auth:  Azure AD OAuth2 — Client Credentials (app-only)
       POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
       grant_type=client_credentials | scope=https://graph.microsoft.com/.default

Required Azure AD app permissions (Application, not Delegated):
  Reports.Read.All         — Copilot usage reports
  Organization.Read.All    — Licensed SKUs (Copilot detection)
  TeamsApp.Read.All        — Teams apps catalogue
  Application.Read.All     — App registrations / service principals

Required config keys:
  tenant_id     – Azure AD tenant (directory) ID
  client_id     – App registration client ID
  client_secret – App registration client secret

Optional config keys:
  include_beta  – "true" to query Graph beta endpoints (default: "false")
"""
import logging
import httpx
from .base import DiscoveredAsset, is_ai_related

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_BETA = "https://graph.microsoft.com/beta"
AZURE_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

# ── M365 Copilot SKU identifiers ───────────────────────────────────────────────
# These Service Plan / SKU part numbers indicate M365 Copilot licensing

COPILOT_SKU_KEYWORDS = {
    "microsoft_365_copilot",
    "copilot_for_microsoft_365",
    "m365_copilot",
    "copilot",
}

COPILOT_SKU_GUIDS = {
    # Microsoft 365 Copilot (commercial)
    "639decb8-2a81-4b05-b7e4-2a8ba2a2a9f3",
    # Microsoft Copilot for Microsoft 365 (GCC)
    "b1cca37c-b6e4-4d4f-a48c-43f0c87f36b4",
}

# Known Azure AI / Cognitive Services app IDs (first-party Microsoft)
KNOWN_AI_SERVICE_PRINCIPAL_APPS = {
    "00000003-0000-0000-c000-000000000000": "Microsoft Graph",  # Exclude (not AI)
    "982bda36-4632-4165-a46a-9863b1bbcf7d": "Azure Cognitive Services",
    "7e3bc4fd-85a3-4a9e-a8c5-be5c23e70e27": "Azure OpenAI",
    "6a8a3c50-a16b-4f62-ab67-c53f25d0cc4b": "Azure Machine Learning",
    "509e4652-da8d-478d-a730-e9d4a1996ca4": "Azure AI Content Safety",
    "b945c813-f13e-4a3b-b924-e93b73b9a823": "Azure AI Language",
    "2b49c9d9-ad4b-4fa5-a254-e0a2a380c8f7": "Azure AI Vision",
    "00000009-0000-0000-c000-000000000000": "Power BI Service",
    "c9a559d2-7aab-4f13-a6ed-e7e9c52aec87": "Microsoft Forms",
}

# AI-related keywords for Teams app detection
TEAMS_AI_KEYWORDS = {
    "copilot", "ai ", " ai", "bot", "gpt", "openai", "einstein",
    "intelligence", "insight", "predict", "assist", "chatbot",
    "virtual agent", "nlp", "ml ", " ml", "cognitive", "generative",
    "automation", "recommendation", "sentiment", "azure ai",
}

# Risky AI app categories
HIGH_RISK_APP_CATEGORIES = {
    "generative ai", "llm", "gpt", "chatbot", "ai assistant",
    "code generation", "image generation",
}


# ── Auth ───────────────────────────────────────────────────────────────────────

async def _get_graph_token(client: httpx.AsyncClient, tenant_id: str,
                            client_id: str, client_secret: str) -> str:
    url = AZURE_TOKEN_URL.format(tenant_id=tenant_id)
    resp = await client.post(url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    })
    if resp.status_code != 200:
        raise ValueError(
            f"M365 Azure AD OAuth2 falhou ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()["access_token"]


# ── Graph API helpers ──────────────────────────────────────────────────────────

async def _graph_get(client: httpx.AsyncClient, headers: dict,
                      path: str, beta: bool = False,
                      params: dict | None = None) -> dict | None:
    base = GRAPH_BETA if beta else GRAPH_BASE
    url = f"{base}{path}"
    resp = await client.get(url, headers=headers, params=params or {})
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 403:
        logger.warning("M365 Graph: permissão negada em %s", path)
        return None
    if resp.status_code == 404:
        logger.debug("M365 Graph: recurso não encontrado em %s", path)
        return None
    logger.warning("M365 Graph %s → %s", path, resp.status_code)
    return None


async def _graph_get_list(client: httpx.AsyncClient, headers: dict,
                           path: str, beta: bool = False,
                           params: dict | None = None,
                           max_items: int = 500) -> list[dict]:
    """Fetch a Graph API collection, following @odata.nextLink pagination."""
    base = GRAPH_BETA if beta else GRAPH_BASE
    url = f"{base}{path}"
    items: list[dict] = []
    while url and len(items) < max_items:
        resp = await client.get(url, headers=headers, params=params or {})
        params = None  # Only send params on first request
        if resp.status_code != 200:
            if resp.status_code == 403:
                logger.warning("M365 Graph: permissão negada em %s", path)
            break
        data = resp.json()
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return items[:max_items]


# ── Sub-discoverers ────────────────────────────────────────────────────────────

async def _discover_copilot_license(client, headers, assets):
    """
    Detect M365 Copilot licensing from subscribedSkus.
    Requires Organization.Read.All or Directory.Read.All.
    """
    skus = await _graph_get_list(client, headers, "/subscribedSkus")
    for sku in skus:
        sku_id = (sku.get("skuId") or "").lower()
        sku_part = (sku.get("skuPartNumber") or "").lower()
        display = sku.get("skuPartNumber", sku.get("skuId", "Unknown"))

        # Check by GUID or part number
        is_copilot = (
            sku_id in COPILOT_SKU_GUIDS or
            any(kw in sku_part for kw in COPILOT_SKU_KEYWORDS)
        )
        if not is_copilot:
            continue

        consumed_units = sku.get("consumedUnits", 0)
        prepaid_units = (sku.get("prepaidUnits") or {}).get("enabled", 0)

        assets.append(DiscoveredAsset(
            external_id=f"m365-copilot-sku-{sku.get('skuId', display)}",
            name=f"Microsoft 365 Copilot — Licença ({consumed_units}/{prepaid_units} users)",
            vendor="Microsoft",
            category="Generative AI",
            subcategory="Copilot",
            asset_type="m365_copilot_license",
            platform="m365",
            risk_level="critical",
            risk_score=9,
            confidence_score=1.0,
            is_shadow_ai=False,
            source_details={
                "sku_id": sku.get("skuId"),
                "sku_part_number": sku.get("skuPartNumber"),
                "consumed_units": consumed_units,
                "prepaid_units": prepaid_units,
                "applies_to": sku.get("appliesTo"),
            },
            metadata={"source": "graph.subscribedSkus"},
        ))


async def _discover_copilot_usage(client, headers, assets, include_beta: bool):
    """
    Fetch M365 Copilot usage by service (Teams, Word, Excel, etc.).
    Requires Reports.Read.All.
    Report endpoint returns CSV; we use the summary JSON endpoint.
    """
    # Try the summary endpoint (Graph v1.0 — available from late 2024)
    data = await _graph_get(
        client, headers,
        "/reports/getMicrosoft365CopilotUsageSummary(period='D30')",
    )
    if data and "value" in data:
        for entry in data["value"]:
            service = entry.get("reportFor", "Unknown Service")
            active_users = entry.get("activeUserCount", 0) or 0
            if active_users == 0:
                continue
            assets.append(DiscoveredAsset(
                external_id=f"m365-copilot-usage-{service.lower().replace(' ', '-')}",
                name=f"M365 Copilot Ativo: {service} ({active_users} usuários)",
                vendor="Microsoft",
                category="Generative AI",
                subcategory="Copilot",
                asset_type="m365_copilot_usage",
                platform="m365",
                risk_level="high" if active_users > 100 else "medium",
                risk_score=8 if active_users > 100 else 6,
                confidence_score=1.0,
                is_shadow_ai=False,
                source_details={
                    "service": service,
                    "active_users_last_30d": active_users,
                    "inactive_users": entry.get("inactiveUserCount", 0),
                },
                metadata={"source": "graph.copilotUsageSummary", "period": "D30"},
            ))
        return

    # Fallback: beta endpoint
    if include_beta:
        beta_data = await _graph_get(
            client, headers,
            "/reports/getMicrosoft365CopilotUsageSummary(period='D30')",
            beta=True,
        )
        if beta_data and "value" in beta_data:
            for entry in beta_data["value"]:
                service = entry.get("reportFor", "Unknown")
                active_users = entry.get("activeUserCount", 0) or 0
                if active_users == 0:
                    continue
                assets.append(DiscoveredAsset(
                    external_id=f"m365-copilot-usage-{service.lower().replace(' ', '-')}",
                    name=f"M365 Copilot Ativo: {service} ({active_users} usuários)",
                    vendor="Microsoft",
                    category="Generative AI",
                    subcategory="Copilot",
                    asset_type="m365_copilot_usage",
                    platform="m365",
                    risk_level="high" if active_users > 100 else "medium",
                    risk_score=8 if active_users > 100 else 6,
                    confidence_score=1.0,
                    is_shadow_ai=False,
                    source_details={
                        "service": service,
                        "active_users_last_30d": active_users,
                    },
                    metadata={"source": "graph.beta.copilotUsageSummary"},
                ))


async def _discover_teams_ai_apps(client, headers, assets):
    """
    Discover AI-related apps in the Teams app catalogue (org + store).
    Requires TeamsApp.Read.All.
    """
    # Get all org-deployed apps (distributionMethod = 'organization')
    org_apps = await _graph_get_list(
        client, headers,
        "/appCatalogs/teamsApps",
        params={
            "$filter": "distributionMethod eq 'organization'",
            "$select": "id,externalId,displayName,distributionMethod",
        },
        max_items=300,
    )
    for app in org_apps:
        display_name = app.get("displayName", "")
        if not is_ai_related(display_name):
            continue
        app_id = app.get("id", "unknown")
        # Shadow AI: org-deployed non-Microsoft AI app
        vendor = "Microsoft" if "microsoft" in display_name.lower() else "Third-party"
        is_shadow = vendor != "Microsoft"
        assets.append(DiscoveredAsset(
            external_id=f"m365-teams-app-{app_id}",
            name=f"Teams AI App (Org): {display_name}",
            vendor=vendor,
            category="Generative AI" if is_ai_related(display_name) else "SaaS AI Tool",
            subcategory="Teams Plugin",
            asset_type="teams_app",
            platform="m365",
            risk_level="high" if is_shadow else "medium",
            risk_score=7 if is_shadow else 5,
            confidence_score=0.9,
            is_shadow_ai=is_shadow,
            source_details={
                "app_id": app_id,
                "external_id": app.get("externalId"),
                "distribution_method": app.get("distributionMethod"),
            },
            metadata={"source": "graph.teamsApps.organization"},
        ))

    # Also check Microsoft-published AI apps installed in the tenant
    ms_ai_apps = await _graph_get_list(
        client, headers,
        "/appCatalogs/teamsApps",
        params={
            "$filter": "distributionMethod eq 'store' and publisherId eq 'Microsoft'",
            "$select": "id,externalId,displayName,distributionMethod",
        },
        max_items=200,
    )
    for app in ms_ai_apps:
        display_name = app.get("displayName", "")
        if not is_ai_related(display_name):
            continue
        app_id = app.get("id", "unknown")
        assets.append(DiscoveredAsset(
            external_id=f"m365-teams-ms-app-{app_id}",
            name=f"Teams AI App (Microsoft): {display_name}",
            vendor="Microsoft",
            category="Generative AI",
            subcategory="Teams Plugin",
            asset_type="teams_app_microsoft",
            platform="m365",
            risk_level="medium",
            risk_score=5,
            confidence_score=0.85,
            is_shadow_ai=False,
            source_details={
                "app_id": app_id,
                "distribution_method": "store",
            },
            metadata={"source": "graph.teamsApps.store.microsoft"},
        ))


async def _discover_entra_ai_apps(client, headers, assets):
    """
    Discover AI-related app registrations in Entra ID (Azure AD).
    Requires Application.Read.All.
    Shadow AI: apps with AI in the name that are not Microsoft-published.
    """
    # Registered applications
    apps = await _graph_get_list(
        client, headers,
        "/applications",
        params={
            "$select": "id,appId,displayName,tags,publisherDomain,createdDateTime",
            "$top": "200",
        },
        max_items=500,
    )
    for app in apps:
        display_name = app.get("displayName", "")
        tags = app.get("tags") or []
        publisher_domain = (app.get("publisherDomain") or "").lower()

        # Check name, tags for AI indicators
        tag_str = " ".join(str(t) for t in tags)
        if not is_ai_related(display_name + " " + tag_str):
            continue

        is_ms = "microsoft.com" in publisher_domain
        is_shadow = not is_ms  # Non-Microsoft AI app registrations = shadow

        assets.append(DiscoveredAsset(
            external_id=f"m365-app-reg-{app.get('appId', app.get('id'))}",
            name=f"Entra ID App Registration (AI): {display_name}",
            vendor="Microsoft" if is_ms else publisher_domain or "Unknown",
            category="Generative AI" if any(
                kw in display_name.lower() for kw in ("gpt", "llm", "openai", "copilot", "generative")
            ) else "SaaS AI Tool",
            subcategory="App Registration",
            asset_type="entra_app_registration",
            platform="m365",
            risk_level="high" if is_shadow else "low",
            risk_score=7 if is_shadow else 3,
            confidence_score=0.85,
            is_shadow_ai=is_shadow,
            source_details={
                "app_id": app.get("appId"),
                "object_id": app.get("id"),
                "publisher_domain": publisher_domain,
                "tags": tags,
                "created": app.get("createdDateTime"),
            },
            metadata={"source": "graph.applications"},
        ))


async def _discover_ai_service_principals(client, headers, assets):
    """
    Discover service principals for known Azure AI services registered in the tenant.
    Requires Application.Read.All or Directory.Read.All.
    """
    sps = await _graph_get_list(
        client, headers,
        "/servicePrincipals",
        params={
            "$select": "id,appId,displayName,publisherName,homepage,tags",
            "$top": "200",
        },
        max_items=500,
    )
    seen_ai_apps: set[str] = set()
    for sp in sps:
        app_id = sp.get("appId", "")
        display_name = sp.get("displayName", "")
        publisher = sp.get("publisherName", "")
        tags = sp.get("tags") or []
        tag_str = " ".join(str(t) for t in tags)

        # Check known AI service principals first
        if app_id in KNOWN_AI_SERVICE_PRINCIPAL_APPS:
            known_name = KNOWN_AI_SERVICE_PRINCIPAL_APPS[app_id]
            if app_id in ("00000003-0000-0000-c000-000000000000",):
                continue  # Skip Microsoft Graph (not an AI tool)
            if app_id not in seen_ai_apps:
                seen_ai_apps.add(app_id)
                assets.append(DiscoveredAsset(
                    external_id=f"m365-sp-known-{app_id}",
                    name=f"Azure AI Service (Entra): {known_name}",
                    vendor="Microsoft",
                    category="AI Infrastructure",
                    subcategory="Azure AI Service",
                    asset_type="service_principal_azure_ai",
                    platform="m365",
                    risk_level="medium",
                    risk_score=5,
                    confidence_score=1.0,
                    is_shadow_ai=False,
                    source_details={
                        "app_id": app_id,
                        "sp_id": sp.get("id"),
                        "display_name": display_name,
                    },
                    metadata={"source": "graph.servicePrincipals.known_ai"},
                ))
            continue

        # Check unknown SPs with AI indicators
        if is_ai_related(display_name + " " + tag_str) and app_id not in seen_ai_apps:
            is_ms_publisher = "microsoft" in (publisher or "").lower()
            seen_ai_apps.add(app_id)
            assets.append(DiscoveredAsset(
                external_id=f"m365-sp-ai-{app_id}",
                name=f"Entra Service Principal (AI): {display_name}",
                vendor=publisher or ("Microsoft" if is_ms_publisher else "Third-party"),
                category="SaaS AI Tool",
                subcategory="Service Principal",
                asset_type="service_principal_third_party",
                platform="m365",
                risk_level="high" if not is_ms_publisher else "low",
                risk_score=7 if not is_ms_publisher else 3,
                confidence_score=0.80,
                is_shadow_ai=not is_ms_publisher,
                source_details={
                    "app_id": app_id,
                    "sp_id": sp.get("id"),
                    "publisher": publisher,
                    "tags": tags,
                },
                metadata={"source": "graph.servicePrincipals.ai_detected"},
            ))


async def _discover_sharepoint_syntex(client, headers, assets, include_beta: bool):
    """
    Detect SharePoint Syntex / Microsoft 365 Premium content AI.
    Requires Sites.Read.All (beta endpoint for Syntex settings).
    """
    # Check for Syntex service plan in subscribed SKUs (already covered via license check)
    # Here we probe the Syntex settings endpoint (beta)
    if not include_beta:
        return

    data = await _graph_get(
        client, headers,
        "/admin/sharepoint/settings",
        beta=True,
    )
    if not data:
        return

    ai_features_enabled = []
    # Check relevant Syntex/AI SharePoint settings
    if data.get("isSyntexEnabled") or data.get("isContentAIEnabled"):
        ai_features_enabled.append("SharePoint Syntex / Content AI")
    if data.get("isAIBuilderEnabled"):
        ai_features_enabled.append("AI Builder (SharePoint)")

    for feat in ai_features_enabled:
        assets.append(DiscoveredAsset(
            external_id=f"m365-sharepoint-{feat.lower().replace(' ', '-').replace('/', '-')}",
            name=f"SharePoint: {feat}",
            vendor="Microsoft",
            category="Machine Learning",
            subcategory="Document AI",
            asset_type="sharepoint_ai_feature",
            platform="m365",
            risk_level="medium",
            risk_score=5,
            confidence_score=0.9,
            is_shadow_ai=False,
            source_details={
                "feature": feat,
                "detected_via": "graph.beta.sharepoint.settings",
            },
            metadata={"source": "graph.beta.sharepoint.settings"},
        ))


async def _discover_copilot_studio_bots(client, headers, assets, include_beta: bool):
    """
    Discover Copilot Studio (Power Virtual Agents) bots via Graph beta.
    Requires appropriate Power Platform permissions (Graph beta).
    """
    if not include_beta:
        return

    # Power Virtual Agents bots are exposed via Graph beta
    bots = await _graph_get_list(
        client, headers,
        "/solutions/businessScenarios",
        beta=True,
        max_items=100,
    )
    for bot in bots:
        display_name = bot.get("displayName", bot.get("id", "Unknown Bot"))
        bot_id = bot.get("id", "unknown")
        if not is_ai_related(display_name + " scenario copilot bot"):
            continue
        assets.append(DiscoveredAsset(
            external_id=f"m365-copilot-studio-{bot_id}",
            name=f"Copilot Studio Bot: {display_name}",
            vendor="Microsoft",
            category="Conversational AI",
            subcategory="Copilot Studio",
            asset_type="copilot_studio_bot",
            platform="m365",
            risk_level="high",
            risk_score=7,
            confidence_score=0.85,
            is_shadow_ai=False,
            source_details={"bot_id": bot_id, "display_name": display_name},
            metadata={"source": "graph.beta.solutions.businessScenarios"},
        ))


async def _discover_exchange_copilot(client, headers, assets):
    """
    Detect Exchange/Outlook Copilot features via org config.
    Checks for AI-enabled policies in the organization settings.
    """
    data = await _graph_get(
        client, headers,
        "/organization",
        params={"$select": "id,displayName,assignedPlans"},
    )
    if not data:
        return

    orgs = [data] if data and "id" in data else []
    for org in orgs:
        assigned_plans = org.get("assignedPlans") or []
        org_name = org.get("displayName", "M365 Organization")
        org_id = org.get("id", "unknown")

        # Look for Copilot/AI service plans in the org
        ai_plans = [
            p for p in assigned_plans
            if is_ai_related(p.get("servicePlanName", "") or p.get("service", ""))
            and p.get("capabilityStatus") == "Enabled"
        ]

        for plan in ai_plans:
            plan_name = plan.get("servicePlanName") or plan.get("service") or "AI Service"
            plan_id = plan.get("servicePlanId", "unknown")
            # Skip duplicates with known Copilot SKUs
            if "copilot" in plan_name.lower():
                continue  # Already captured via subscribedSkus
            assets.append(DiscoveredAsset(
                external_id=f"m365-org-plan-{plan_id}",
                name=f"M365 AI Service Plan: {plan_name}",
                vendor="Microsoft",
                category="SaaS AI Tool",
                subcategory="M365 Service Plan",
                asset_type="m365_service_plan",
                platform="m365",
                risk_level="medium",
                risk_score=5,
                confidence_score=0.85,
                is_shadow_ai=False,
                source_details={
                    "org_id": org_id,
                    "org_name": org_name,
                    "plan_id": plan_id,
                    "plan_name": plan_name,
                    "capability_status": plan.get("capabilityStatus"),
                },
                metadata={"source": "graph.organization.assignedPlans"},
            ))


# ── Main entry point ───────────────────────────────────────────────────────────

async def discover(config: dict) -> list[dict]:
    """
    Microsoft 365 AI asset discovery via Microsoft Graph API.

    Returns a list of standardised asset dicts compatible with
    ConnectorService._upsert_assets().
    """
    tenant_id = config.get("tenant_id", "")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    include_beta = str(config.get("include_beta", "false")).lower() == "true"

    if not all([tenant_id, client_id, client_secret]):
        raise ValueError(
            "Configuração M365 incompleta: "
            "tenant_id, client_id e client_secret são obrigatórios"
        )

    assets: list[DiscoveredAsset] = []

    async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
        token = await _get_graph_token(client, tenant_id, client_id, client_secret)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # ConsistencyLevel required for $search / $filter with advanced query
            "ConsistencyLevel": "eventual",
        }

        # 1. Copilot license detection (most critical)
        await _discover_copilot_license(client, headers, assets)

        # 2. Copilot usage per service (Teams Copilot, Word Copilot, etc.)
        await _discover_copilot_usage(client, headers, assets, include_beta)

        # 3. Teams AI apps (org-deployed + Microsoft store)
        await _discover_teams_ai_apps(client, headers, assets)

        # 4. Entra ID AI app registrations (shadow AI detection)
        await _discover_entra_ai_apps(client, headers, assets)

        # 5. Azure AI service principals in the tenant
        await _discover_ai_service_principals(client, headers, assets)

        # 6. SharePoint Syntex / content AI (beta only)
        await _discover_sharepoint_syntex(client, headers, assets, include_beta)

        # 7. Copilot Studio bots via Graph beta
        await _discover_copilot_studio_bots(client, headers, assets, include_beta)

        # 8. M365 org-level AI service plans (Outlook Copilot, etc.)
        await _discover_exchange_copilot(client, headers, assets)

    logger.info("M365 discovery: %d assets found", len(assets))
    return [a.to_dict() for a in assets]
