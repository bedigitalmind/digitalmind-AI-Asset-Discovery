"""
AI Asset Taxonomy — the knowledge base of known AI tools, services and patterns.

Each entry represents a known AI asset with detection signals.
This is the core "DNA" of the discovery product.
"""
from dataclasses import dataclass, field
from typing import Optional
import re

@dataclass
class TaxonomyEntry:
    id: str
    name: str
    vendor: str
    category: str          # One of 7 main categories
    subcategory: str
    risk_level: str        # critical, high, medium, low
    risk_score: int        # 1-10
    description: str
    is_saas: bool = True
    # Detection signals
    domains: list[str] = field(default_factory=list)
    url_patterns: list[str] = field(default_factory=list)
    api_endpoints: list[str] = field(default_factory=list)
    process_names: list[str] = field(default_factory=list)
    package_names: list[str] = field(default_factory=list)
    azure_resource_types: list[str] = field(default_factory=list)
    aws_service_names: list[str] = field(default_factory=list)
    gcp_service_names: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 1: Conversational AI
# ─────────────────────────────────────────────────────────────────────────────
CONVERSATIONAL_AI = [
    TaxonomyEntry(
        id="conv-openai-chatgpt",
        name="ChatGPT", vendor="OpenAI", category="conversational_ai",
        subcategory="general_purpose_llm", risk_level="high", risk_score=8,
        description="Assistente conversacional baseado em GPT-4/GPT-3.5. Risco de envio de dados confidenciais.",
        domains=["chat.openai.com", "chatgpt.com"],
        api_endpoints=["api.openai.com/v1/chat/completions", "api.openai.com/v1/completions"],
        package_names=["openai"],
    ),
    TaxonomyEntry(
        id="conv-anthropic-claude",
        name="Claude", vendor="Anthropic", category="conversational_ai",
        subcategory="general_purpose_llm", risk_level="high", risk_score=8,
        description="Assistente conversacional da Anthropic. Risco de envio de dados confidenciais.",
        domains=["claude.ai", "console.anthropic.com"],
        api_endpoints=["api.anthropic.com/v1/messages"],
        package_names=["anthropic"],
    ),
    TaxonomyEntry(
        id="conv-google-gemini",
        name="Google Gemini", vendor="Google", category="conversational_ai",
        subcategory="general_purpose_llm", risk_level="high", risk_score=7,
        description="Assistente conversacional do Google (ex-Bard).",
        domains=["gemini.google.com", "bard.google.com"],
        api_endpoints=["generativelanguage.googleapis.com"],
        package_names=["google-generativeai"],
    ),
    TaxonomyEntry(
        id="conv-perplexity",
        name="Perplexity AI", vendor="Perplexity", category="conversational_ai",
        subcategory="ai_search", risk_level="high", risk_score=7,
        description="Motor de busca com IA conversacional.",
        domains=["perplexity.ai"],
        api_endpoints=["api.perplexity.ai"],
    ),
    TaxonomyEntry(
        id="conv-mistral",
        name="Mistral Chat", vendor="Mistral AI", category="conversational_ai",
        subcategory="general_purpose_llm", risk_level="medium", risk_score=6,
        description="Assistente conversacional open-source da Mistral AI.",
        domains=["chat.mistral.ai", "console.mistral.ai"],
        api_endpoints=["api.mistral.ai/v1/chat/completions"],
        package_names=["mistralai"],
    ),
    TaxonomyEntry(
        id="conv-meta-llama",
        name="Meta AI / Llama", vendor="Meta", category="conversational_ai",
        subcategory="open_source_llm", risk_level="medium", risk_score=5,
        description="Modelos open-source Llama da Meta. Pode ser rodado localmente.",
        domains=["meta.ai", "llama.meta.com"],
        package_names=["llama-cpp-python", "transformers"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="conv-cohere",
        name="Cohere", vendor="Cohere", category="conversational_ai",
        subcategory="enterprise_llm", risk_level="medium", risk_score=6,
        description="Plataforma de LLMs voltada para enterprise.",
        domains=["cohere.com", "dashboard.cohere.com"],
        api_endpoints=["api.cohere.com/v1/chat", "api.cohere.ai"],
        package_names=["cohere"],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 2: Copilots
# ─────────────────────────────────────────────────────────────────────────────
COPILOTS = [
    TaxonomyEntry(
        id="copilot-ms-365",
        name="Microsoft 365 Copilot", vendor="Microsoft", category="copilot",
        subcategory="productivity_copilot", risk_level="high", risk_score=8,
        description="IA integrada ao Microsoft 365 (Word, Excel, Teams, Outlook). Acessa dados corporativos.",
        domains=["copilot.microsoft.com", "m365.cloud.microsoft"],
        azure_resource_types=["Microsoft.BotService/botServices"],
        process_names=["msedge.exe"],
    ),
    TaxonomyEntry(
        id="copilot-github",
        name="GitHub Copilot", vendor="GitHub/Microsoft", category="copilot",
        subcategory="code_copilot", risk_level="high", risk_score=8,
        description="Assistente de código com IA. Risco de envio de código proprietário para servidores externos.",
        domains=["copilot.github.com", "githubcopilot.com"],
        api_endpoints=["api.githubcopilot.com"],
        process_names=["GitHub.Copilot"],
        package_names=["github-copilot"],
    ),
    TaxonomyEntry(
        id="copilot-salesforce-einstein",
        name="Salesforce Einstein Copilot", vendor="Salesforce", category="copilot",
        subcategory="crm_copilot", risk_level="high", risk_score=8,
        description="Copiloto de IA integrado ao Salesforce CRM.",
        domains=["*.salesforce.com", "*.lightning.force.com"],
    ),
    TaxonomyEntry(
        id="copilot-cursor",
        name="Cursor", vendor="Anysphere", category="copilot",
        subcategory="code_copilot", risk_level="high", risk_score=7,
        description="IDE com IA baseado no VS Code. Envia trechos de código para LLMs externos.",
        domains=["cursor.sh", "cursor.com"],
        api_endpoints=["api2.cursor.sh"],
        process_names=["Cursor", "cursor"],
    ),
    TaxonomyEntry(
        id="copilot-tabnine",
        name="Tabnine", vendor="Tabnine", category="copilot",
        subcategory="code_copilot", risk_level="medium", risk_score=6,
        description="Autocomplete de código com IA. Pode operar localmente ou em nuvem.",
        domains=["tabnine.com", "app.tabnine.com"],
        package_names=["tabnine"],
    ),
    TaxonomyEntry(
        id="copilot-ms-security",
        name="Microsoft Security Copilot", vendor="Microsoft", category="copilot",
        subcategory="security_copilot", risk_level="medium", risk_score=5,
        description="Copiloto de segurança da Microsoft integrado ao Sentinel e Defender.",
        domains=["securitycopilot.microsoft.com"],
        azure_resource_types=["Microsoft.SecurityCopilot/*"],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 3: AI Agents
# ─────────────────────────────────────────────────────────────────────────────
AI_AGENTS = [
    TaxonomyEntry(
        id="agent-n8n-ai",
        name="n8n AI Agents", vendor="n8n", category="ai_agent",
        subcategory="workflow_agent", risk_level="high", risk_score=9,
        description="Plataforma de automação com agentes de IA. Executa ações autônomas.",
        domains=["n8n.io", "*.n8n.cloud"],
        package_names=["n8n"],
        process_names=["n8n"],
    ),
    TaxonomyEntry(
        id="agent-langchain",
        name="LangChain Agents", vendor="LangChain", category="ai_agent",
        subcategory="llm_framework", risk_level="high", risk_score=9,
        description="Framework para construção de agentes LLM com ferramentas e memória.",
        package_names=["langchain", "langchain-core", "langchain-community"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="agent-autogen",
        name="AutoGen", vendor="Microsoft", category="ai_agent",
        subcategory="multi_agent", risk_level="critical", risk_score=10,
        description="Framework multi-agente da Microsoft. Agentes colaboram autonomamente.",
        package_names=["pyautogen", "autogen-agentchat"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="agent-crewai",
        name="CrewAI", vendor="CrewAI", category="ai_agent",
        subcategory="multi_agent", risk_level="critical", risk_score=10,
        description="Framework de agentes colaborativos com papéis definidos.",
        package_names=["crewai"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="agent-ms-copilot-studio",
        name="Microsoft Copilot Studio", vendor="Microsoft", category="ai_agent",
        subcategory="no_code_agent", risk_level="high", risk_score=8,
        description="Plataforma low-code para criação de copilotos e agentes de IA.",
        domains=["copilotstudio.microsoft.com", "powervirtualagents.microsoft.com"],
        azure_resource_types=["Microsoft.BotService/botServices"],
    ),
    TaxonomyEntry(
        id="agent-make-ai",
        name="Make (ex-Integromat) AI", vendor="Make", category="ai_agent",
        subcategory="workflow_agent", risk_level="high", risk_score=7,
        description="Plataforma de automação com módulos de IA.",
        domains=["make.com", "integromat.com"],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 4: Embedded AI in SaaS
# ─────────────────────────────────────────────────────────────────────────────
EMBEDDED_SAAS = [
    TaxonomyEntry(
        id="saas-notion-ai",
        name="Notion AI", vendor="Notion", category="embedded_saas",
        subcategory="productivity", risk_level="medium", risk_score=6,
        description="IA embutida no Notion para escrita e resumo de conteúdo.",
        domains=["notion.so", "www.notion.so"],
        api_endpoints=["notion.so/api/v3"],
    ),
    TaxonomyEntry(
        id="saas-grammarly",
        name="Grammarly", vendor="Grammarly", category="embedded_saas",
        subcategory="writing_assistant", risk_level="medium", risk_score=6,
        description="Assistente de escrita com IA. Processa texto digitado pelo usuário.",
        domains=["grammarly.com", "*.grammarly.com"],
        api_endpoints=["capi.grammarly.com"],
        process_names=["Grammarly", "GrammarlyHelper"],
    ),
    TaxonomyEntry(
        id="saas-slack-ai",
        name="Slack AI", vendor="Salesforce/Slack", category="embedded_saas",
        subcategory="communication", risk_level="medium", risk_score=6,
        description="IA integrada ao Slack para resumo de conversas e busca.",
        domains=["slack.com", "*.slack.com"],
    ),
    TaxonomyEntry(
        id="saas-zoom-ai",
        name="Zoom AI Companion", vendor="Zoom", category="embedded_saas",
        subcategory="video_conferencing", risk_level="medium", risk_score=6,
        description="IA do Zoom para transcrição, resumo e assistência em reuniões.",
        domains=["zoom.us", "*.zoom.us"],
        process_names=["zoom", "Zoom"],
    ),
    TaxonomyEntry(
        id="saas-canva-ai",
        name="Canva AI (Magic Studio)", vendor="Canva", category="embedded_saas",
        subcategory="design", risk_level="low", risk_score=3,
        description="Geração de imagens e conteúdo com IA no Canva.",
        domains=["canva.com", "*.canva.com"],
    ),
    TaxonomyEntry(
        id="saas-figma-ai",
        name="Figma AI", vendor="Figma", category="embedded_saas",
        subcategory="design", risk_level="medium", risk_score=5,
        description="Funcionalidades de IA no Figma para design e prototipagem.",
        domains=["figma.com", "*.figma.com"],
    ),
    TaxonomyEntry(
        id="saas-hubspot-ai",
        name="HubSpot AI (Breeze)", vendor="HubSpot", category="embedded_saas",
        subcategory="marketing_crm", risk_level="medium", risk_score=6,
        description="IA integrada ao HubSpot para automação de marketing e CRM.",
        domains=["*.hubspot.com", "*.hubapi.com"],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 5: AI in ERP/CRM
# ─────────────────────────────────────────────────────────────────────────────
ERP_CRM_AI = [
    TaxonomyEntry(
        id="erp-sap-ai-core",
        name="SAP AI Core", vendor="SAP", category="erp_crm_ai",
        subcategory="erp", risk_level="critical", risk_score=10,
        description="Plataforma de IA do SAP. Processa dados críticos de negócio.",
        domains=["*.ai.prod.us-east-1.aws.ml.hana.ondemand.com"],
        api_endpoints=["*.aicore.prod.us-east-1.aws.ml.hana.ondemand.com"],
    ),
    TaxonomyEntry(
        id="erp-salesforce-einstein",
        name="Salesforce Einstein AI", vendor="Salesforce", category="erp_crm_ai",
        subcategory="crm", risk_level="high", risk_score=8,
        description="IA integrada ao Salesforce CRM para previsões e automação.",
        domains=["*.salesforce.com", "*.lightning.force.com"],
    ),
    TaxonomyEntry(
        id="erp-servicenow-now-intelligence",
        name="ServiceNow Now Intelligence", vendor="ServiceNow", category="erp_crm_ai",
        subcategory="itsm", risk_level="high", risk_score=8,
        description="IA integrada ao ServiceNow para automação de ITSM.",
        domains=["*.servicenow.com", "*.service-now.com"],
    ),
    TaxonomyEntry(
        id="erp-dynamics-copilot",
        name="Microsoft Dynamics 365 Copilot", vendor="Microsoft", category="erp_crm_ai",
        subcategory="erp_crm", risk_level="high", risk_score=8,
        description="Copiloto de IA integrado ao Dynamics 365 ERP e CRM.",
        domains=["*.dynamics.com", "*.crm.dynamics.com"],
        azure_resource_types=["Microsoft.Dynamics365/*"],
    ),
    TaxonomyEntry(
        id="erp-workday-ai",
        name="Workday AI", vendor="Workday", category="erp_crm_ai",
        subcategory="hrm_finance", risk_level="high", risk_score=8,
        description="IA integrada ao Workday para RH e finanças.",
        domains=["*.workday.com", "*.myworkday.com"],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 6: AI APIs & SDKs
# ─────────────────────────────────────────────────────────────────────────────
AI_APIS = [
    TaxonomyEntry(
        id="api-openai",
        name="OpenAI API", vendor="OpenAI", category="ai_api",
        subcategory="llm_api", risk_level="high", risk_score=8,
        description="API direta de LLMs da OpenAI. Indica integração customizada com IA.",
        api_endpoints=["api.openai.com/v1/"],
        package_names=["openai"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="api-anthropic",
        name="Anthropic API", vendor="Anthropic", category="ai_api",
        subcategory="llm_api", risk_level="high", risk_score=8,
        description="API direta de LLMs da Anthropic (Claude).",
        api_endpoints=["api.anthropic.com/v1/"],
        package_names=["anthropic"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="api-azure-openai",
        name="Azure OpenAI Service", vendor="Microsoft/OpenAI", category="ai_api",
        subcategory="llm_api", risk_level="high", risk_score=8,
        description="Modelos OpenAI hospedados na Azure. Dados ficam no tenant Azure do cliente.",
        api_endpoints=["*.openai.azure.com"],
        azure_resource_types=["Microsoft.CognitiveServices/accounts"],
        package_names=["openai"],
    ),
    TaxonomyEntry(
        id="api-google-vertex",
        name="Google Vertex AI", vendor="Google", category="ai_api",
        subcategory="ml_platform_api", risk_level="high", risk_score=7,
        description="Plataforma de ML/AI da Google Cloud.",
        api_endpoints=["*.aiplatform.googleapis.com", "vertexai.googleapis.com"],
        package_names=["google-cloud-aiplatform"],
        gcp_service_names=["aiplatform.googleapis.com"],
    ),
    TaxonomyEntry(
        id="api-huggingface",
        name="Hugging Face Inference API", vendor="Hugging Face", category="ai_api",
        subcategory="model_api", risk_level="medium", risk_score=6,
        description="API de inferência de modelos open-source do Hugging Face.",
        api_endpoints=["api-inference.huggingface.co", "*.api.huggingface.co"],
        package_names=["huggingface-hub", "transformers"],
        domains=["huggingface.co"],
    ),
    TaxonomyEntry(
        id="api-aws-bedrock",
        name="AWS Bedrock", vendor="Amazon", category="ai_api",
        subcategory="llm_api", risk_level="high", risk_score=8,
        description="Serviço de LLMs da AWS (Claude, Llama, Titan, etc.).",
        api_endpoints=["bedrock.*.amazonaws.com", "bedrock-runtime.*.amazonaws.com"],
        aws_service_names=["bedrock", "bedrock-runtime"],
    ),
    TaxonomyEntry(
        id="api-cohere",
        name="Cohere API", vendor="Cohere", category="ai_api",
        subcategory="llm_api", risk_level="medium", risk_score=6,
        description="API de LLMs da Cohere.",
        api_endpoints=["api.cohere.com/v1/", "api.cohere.ai/"],
        package_names=["cohere"],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 7: Own Models & AI Infrastructure
# ─────────────────────────────────────────────────────────────────────────────
OWN_MODELS = [
    TaxonomyEntry(
        id="infra-azure-ml",
        name="Azure Machine Learning", vendor="Microsoft", category="own_model",
        subcategory="ml_platform", risk_level="critical", risk_score=10,
        description="Plataforma de ML da Azure para treinamento e deploy de modelos próprios.",
        azure_resource_types=[
            "Microsoft.MachineLearningServices/workspaces",
            "Microsoft.MachineLearningServices/workspaces/computes",
        ],
        domains=["ml.azure.com", "*.azureml.net"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="infra-azure-cognitive",
        name="Azure Cognitive Services / AI Services", vendor="Microsoft", category="own_model",
        subcategory="ai_services", risk_level="high", risk_score=8,
        description="Serviços de IA pré-treinados da Azure (visão, fala, linguagem, etc.).",
        azure_resource_types=[
            "Microsoft.CognitiveServices/accounts",
            "Microsoft.CognitiveServices/accounts/deployments",
        ],
        domains=["*.cognitiveservices.azure.com", "*.api.cognitive.microsoft.com"],
    ),
    TaxonomyEntry(
        id="infra-mlflow",
        name="MLflow", vendor="Databricks/Open Source", category="own_model",
        subcategory="ml_lifecycle", risk_level="critical", risk_score=10,
        description="Plataforma open-source de ciclo de vida de ML. Indica modelos proprietários.",
        domains=["*.mlflow.org"],
        api_endpoints=["*/api/2.0/mlflow/"],
        package_names=["mlflow"],
        process_names=["mlflow"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="infra-kubeflow",
        name="Kubeflow", vendor="Google/Open Source", category="own_model",
        subcategory="ml_platform", risk_level="critical", risk_score=10,
        description="Plataforma de ML em Kubernetes. Indica infraestrutura de ML em escala.",
        package_names=["kfp", "kubeflow-pipelines"],
        process_names=["kubeflow"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="infra-huggingface-local",
        name="Hugging Face Transformers (local)", vendor="Hugging Face", category="own_model",
        subcategory="local_model", risk_level="critical", risk_score=9,
        description="Modelos Hugging Face rodando localmente. Indica modelos proprietários ou fine-tuned.",
        package_names=["transformers", "diffusers", "peft", "trl"],
        is_saas=False,
    ),
    TaxonomyEntry(
        id="infra-ollama",
        name="Ollama", vendor="Ollama", category="own_model",
        subcategory="local_llm", risk_level="high", risk_score=8,
        description="Ferramenta para rodar LLMs localmente (Llama, Mistral, etc.).",
        api_endpoints=["localhost:11434", "*.11434"],
        process_names=["ollama"],
        package_names=["ollama"],
        is_saas=False,
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# FULL TAXONOMY (all entries)
# ─────────────────────────────────────────────────────────────────────────────
ALL_ENTRIES: list[TaxonomyEntry] = (
    CONVERSATIONAL_AI + COPILOTS + AI_AGENTS + EMBEDDED_SAAS +
    ERP_CRM_AI + AI_APIS + OWN_MODELS
)

TAXONOMY_BY_ID: dict[str, TaxonomyEntry] = {e.id: e for e in ALL_ENTRIES}

CATEGORIES = {
    "conversational_ai": "IA Conversacional",
    "copilot": "Copilotos",
    "ai_agent": "Agentes de IA",
    "embedded_saas": "IA Embarcada em SaaS",
    "erp_crm_ai": "IA em ERP/CRM",
    "ai_api": "APIs e SDKs de IA",
    "own_model": "Modelos e Infraestrutura Própria",
}

def classify_by_domain(domain: str) -> list[TaxonomyEntry]:
    """Find taxonomy entries matching a given domain."""
    matches = []
    domain_lower = domain.lower()
    for entry in ALL_ENTRIES:
        for d in entry.domains:
            pattern = d.replace(".", r"\.").replace("*", ".*")
            if re.match(pattern, domain_lower) or domain_lower.endswith(d.lstrip("*")):
                matches.append(entry)
                break
    return matches

def classify_by_api_endpoint(url: str) -> list[TaxonomyEntry]:
    """Find taxonomy entries matching an API endpoint URL."""
    matches = []
    url_lower = url.lower()
    for entry in ALL_ENTRIES:
        for endpoint in entry.api_endpoints:
            pattern = endpoint.replace(".", r"\.").replace("*", ".*")
            if re.search(pattern, url_lower):
                matches.append(entry)
                break
    return matches

def classify_by_package(package_name: str) -> list[TaxonomyEntry]:
    """Find taxonomy entries matching a Python package name."""
    pkg_lower = package_name.lower()
    return [e for e in ALL_ENTRIES if pkg_lower in [p.lower() for p in e.package_names]]

def classify_by_azure_resource_type(resource_type: str) -> list[TaxonomyEntry]:
    """Find taxonomy entries matching an Azure resource type."""
    rt_lower = resource_type.lower()
    matches = []
    for entry in ALL_ENTRIES:
        for rt in entry.azure_resource_types:
            pattern = rt.replace(".", r"\.").replace("*", ".*").lower()
            if re.match(pattern, rt_lower):
                matches.append(entry)
                break
    return matches

def get_taxonomy_summary() -> dict:
    """Return a summary of the taxonomy for API responses."""
    by_category = {}
    for category, label in CATEGORIES.items():
        entries = [e for e in ALL_ENTRIES if e.category == category]
        by_category[category] = {
            "label": label,
            "count": len(entries),
            "entries": [{"id": e.id, "name": e.name, "vendor": e.vendor,
                         "risk_level": e.risk_level} for e in entries]
        }
    return {"total": len(ALL_ENTRIES), "categories": by_category}
