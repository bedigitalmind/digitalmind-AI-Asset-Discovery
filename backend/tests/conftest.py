"""
Shared pytest fixtures for the AI Asset Discovery test suite.

Unit tests in this suite do NOT require a live database or MinIO — they
test pure business logic, classifiers, parsers, and security functions.
"""
import os
import sys
import pytest

# Ensure the backend app is importable without a running DB
# We set dummy env vars before any import that reads settings.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_ai_discovery")
os.environ.setdefault("DATABASE_SYNC_URL", "postgresql://test:test@localhost:5432/test_ai_discovery")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-minimum-32-chars")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "testkey")
os.environ.setdefault("MINIO_SECRET_KEY", "testsecret")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")

# Add backend/ to sys.path so `from app.xxx import ...` works
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ── Sample data fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_m365_audit_csv() -> bytes:
    """Minimal M365 Unified Audit Log CSV with ChatGPT and GitHub Copilot signals."""
    return b"""CreationTime,UserId,Operation,AuditData
2024-01-15T10:00:00Z,alice@contoso.com,FileAccessed,"{""SiteUrl"":""https://chat.openai.com"",""FileName"":""document.docx""}"
2024-01-15T10:01:00Z,bob@contoso.com,SharingSet,"{""SiteUrl"":""https://api.openai.com"",""FileName"":""report.pdf""}"
2024-01-15T10:02:00Z,carol@contoso.com,FileModified,"{""SiteUrl"":""https://github.com/features/copilot"",""FileName"":""code.py""}"
2024-01-15T10:03:00Z,dave@contoso.com,TeamsSessionStarted,"{""Workload"":""MicrosoftTeams"",""RecordType"":1}"
"""


@pytest.fixture
def sample_proxy_log_csv() -> bytes:
    """Minimal proxy log CSV with AI tool access signals.
    Uses column names recognized by ProxyLogParser: 'URL' and 'Host'.
    """
    return b"""timestamp,user,src_ip,Host,URL,bytes_sent,bytes_received
2024-01-15T09:00:00Z,alice,10.0.0.1,api.openai.com,https://api.openai.com/v1/chat/completions,1024,4096
2024-01-15T09:01:00Z,bob,10.0.0.2,gemini.google.com,https://gemini.google.com/app,512,2048
2024-01-15T09:02:00Z,carol,10.0.0.3,claude.ai,https://claude.ai/chat,256,1024
2024-01-15T09:03:00Z,dave,10.0.0.4,github.com,https://github.com/features/copilot,128,512
"""


@pytest.fixture
def sample_azure_activity_json() -> bytes:
    """Minimal Azure Activity Log JSON with Cognitive Services events."""
    import json
    records = [
        {
            "time": "2024-01-15T10:00:00Z",
            "resourceId": "/subscriptions/sub123/resourceGroups/rg-ai/providers/Microsoft.CognitiveServices/accounts/openai-prod",
            "operationName": "Microsoft.CognitiveServices/accounts/write",
            "caller": "admin@contoso.com",
            "level": "Information",
        },
        {
            "time": "2024-01-15T10:01:00Z",
            "resourceId": "/subscriptions/sub123/resourceGroups/rg-ml/providers/Microsoft.MachineLearningServices/workspaces/ml-workspace",
            "operationName": "Microsoft.MachineLearningServices/workspaces/read",
            "caller": "mlops@contoso.com",
            "level": "Information",
        },
    ]
    return json.dumps(records).encode()


@pytest.fixture
def sample_generic_csv() -> bytes:
    """Generic CSV that should be auto-detected as GenericCSV parser."""
    return b"""date,user_email,tool_name,tool_url,department
2024-01-15,alice@corp.com,ChatGPT,https://chat.openai.com,Engineering
2024-01-15,bob@corp.com,GitHub Copilot,https://github.com/features/copilot,Engineering
2024-01-16,carol@corp.com,Midjourney,https://midjourney.com,Marketing
2024-01-16,dave@corp.com,Grammarly,https://app.grammarly.com,HR
"""
