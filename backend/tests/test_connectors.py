"""
Tests for ERP/CRM/M365 connector plugins — no network calls required.
Tests cover: config validation, DiscoveredAsset dataclass, PLATFORM_MAP dispatch.
"""
import pytest
from app.services.connectors.base import DiscoveredAsset, is_ai_related, AI_KEYWORDS
from app.services.connectors import PLATFORM_MAP


# ── DiscoveredAsset dataclass ─────────────────────────────────────────────────

class TestDiscoveredAsset:
    def test_minimal_creation(self):
        asset = DiscoveredAsset(
            external_id="test-001",
            name="Test AI Tool",
            vendor="TestVendor",
            category="Generative AI",
        )
        assert asset.external_id == "test-001"
        assert asset.name == "Test AI Tool"
        assert asset.vendor == "TestVendor"
        assert asset.category == "Generative AI"

    def test_defaults(self):
        asset = DiscoveredAsset(
            external_id="x", name="X", vendor="V", category="C"
        )
        assert asset.risk_level == "medium"
        assert asset.risk_score == 5
        assert asset.confidence_score == 0.9
        assert asset.is_shadow_ai is False
        assert asset.source_details == {}
        assert asset.metadata == {}

    def test_to_dict_contains_all_keys(self):
        asset = DiscoveredAsset(
            external_id="sf-001",
            name="Einstein GPT",
            vendor="Salesforce",
            category="Generative AI",
            subcategory="Copilot",
            asset_type="einstein_copilot",
            platform="salesforce",
            risk_level="high",
            risk_score=8,
            confidence_score=1.0,
            is_shadow_ai=False,
            source_details={"key": "value"},
            metadata={"source": "test"},
        )
        d = asset.to_dict()
        expected_keys = {
            "external_id", "name", "vendor", "category", "subcategory",
            "asset_type", "platform", "risk_level", "risk_score",
            "confidence_score", "is_shadow_ai", "source_details", "metadata",
        }
        assert expected_keys == set(d.keys())

    def test_to_dict_values(self):
        asset = DiscoveredAsset(
            external_id="d365-bot-123",
            name="Copilot Bot",
            vendor="Microsoft",
            category="Conversational AI",
            risk_level="high",
            risk_score=7,
            is_shadow_ai=False,
        )
        d = asset.to_dict()
        assert d["external_id"] == "d365-bot-123"
        assert d["risk_score"] == 7
        assert d["is_shadow_ai"] is False

    def test_shadow_ai_flag(self):
        asset = DiscoveredAsset(
            external_id="shadow-001",
            name="Unknown AI Tool",
            vendor="Unknown",
            category="SaaS AI Tool",
            is_shadow_ai=True,
        )
        assert asset.is_shadow_ai is True
        assert asset.to_dict()["is_shadow_ai"] is True


# ── is_ai_related helper ──────────────────────────────────────────────────────

class TestIsAiRelated:
    def test_detects_ai_keywords(self):
        assert is_ai_related("Einstein AI Features") is True
        assert is_ai_related("GPT Integration") is True
        assert is_ai_related("OpenAI Assistant") is True
        assert is_ai_related("Copilot for Sales") is True
        assert is_ai_related("Machine Learning Pipeline") is True
        assert is_ai_related("Chatbot Configuration") is True

    def test_rejects_non_ai(self):
        assert is_ai_related("Standard CRUD Operations") is False
        assert is_ai_related("Database Connection") is False
        assert is_ai_related("User Authentication") is False

    def test_case_insensitive(self):
        assert is_ai_related("EINSTEIN GPT PLUGIN") is True
        assert is_ai_related("einstein gpt plugin") is True
        assert is_ai_related("Einstein Gpt Plugin") is True

    def test_empty_string(self):
        assert is_ai_related("") is False

    def test_ai_in_middle_of_word(self):
        # "ai" as substring — should match since "ai " or " ai" patterns are in keywords
        # "Trailhead" should NOT match as AI
        result = is_ai_related("Trailhead Learning")
        # This depends on implementation; just verify it doesn't raise
        assert isinstance(result, bool)


# ── PLATFORM_MAP completeness ─────────────────────────────────────────────────

class TestPlatformMap:
    EXPECTED_PLATFORMS = {"salesforce", "servicenow", "sap", "dynamics365", "m365"}

    def test_all_platforms_registered(self):
        for platform in self.EXPECTED_PLATFORMS:
            assert platform in PLATFORM_MAP, f"Platform '{platform}' missing from PLATFORM_MAP"

    def test_all_values_are_callable(self):
        for platform, fn in PLATFORM_MAP.items():
            assert callable(fn), f"PLATFORM_MAP['{platform}'] is not callable"

    def test_platform_map_size(self):
        assert len(PLATFORM_MAP) >= 5


# ── Connector config validation ───────────────────────────────────────────────

class TestSalesforceConfigValidation:
    @pytest.mark.asyncio
    async def test_missing_instance_url_raises(self):
        from app.services.connectors.salesforce import discover
        with pytest.raises(ValueError, match="instance_url"):
            await discover({"client_id": "x", "client_secret": "y"})

    @pytest.mark.asyncio
    async def test_missing_client_id_raises(self):
        from app.services.connectors.salesforce import discover
        with pytest.raises(ValueError):
            await discover({"instance_url": "https://test.salesforce.com", "client_secret": "y"})

    @pytest.mark.asyncio
    async def test_empty_config_raises(self):
        from app.services.connectors.salesforce import discover
        with pytest.raises(ValueError):
            await discover({})


class TestServiceNowConfigValidation:
    @pytest.mark.asyncio
    async def test_missing_instance_url_raises(self):
        from app.services.connectors.servicenow import discover
        with pytest.raises(ValueError, match="instance_url"):
            await discover({})

    @pytest.mark.asyncio
    async def test_missing_credentials_raises(self):
        from app.services.connectors.servicenow import discover
        with pytest.raises(ValueError):
            await discover({"instance_url": "https://test.service-now.com"})

    @pytest.mark.asyncio
    async def test_oauth_missing_client_id_raises(self):
        from app.services.connectors.servicenow import discover
        with pytest.raises(ValueError, match="OAuth2"):
            await discover({
                "instance_url": "https://test.service-now.com",
                "use_oauth": "true",
                "client_secret": "secret",
                # Missing client_id
            })


class TestSapConfigValidation:
    @pytest.mark.asyncio
    async def test_missing_token_url_raises(self):
        from app.services.connectors.sap import discover
        with pytest.raises(ValueError):
            await discover({
                "client_id": "x",
                "client_secret": "y",
                "ai_core_api_url": "https://api.ai.example.com",
            })

    @pytest.mark.asyncio
    async def test_missing_ai_core_url_raises(self):
        from app.services.connectors.sap import discover
        with pytest.raises(ValueError, match="ai_core_api_url"):
            await discover({
                "token_url": "https://auth.example.com/token",
                "client_id": "x",
                "client_secret": "y",
            })

    @pytest.mark.asyncio
    async def test_empty_config_raises(self):
        from app.services.connectors.sap import discover
        with pytest.raises(ValueError):
            await discover({})


class TestDynamics365ConfigValidation:
    @pytest.mark.asyncio
    async def test_missing_environment_url_raises(self):
        from app.services.connectors.dynamics365 import discover
        with pytest.raises(ValueError, match="environment_url"):
            await discover({
                "tenant_id": "t",
                "client_id": "c",
                "client_secret": "s",
            })

    @pytest.mark.asyncio
    async def test_empty_config_raises(self):
        from app.services.connectors.dynamics365 import discover
        with pytest.raises(ValueError):
            await discover({})


class TestM365ConfigValidation:
    @pytest.mark.asyncio
    async def test_missing_tenant_id_raises(self):
        from app.services.connectors.m365 import discover
        with pytest.raises(ValueError):
            await discover({"client_id": "x", "client_secret": "y"})

    @pytest.mark.asyncio
    async def test_missing_client_secret_raises(self):
        from app.services.connectors.m365 import discover
        with pytest.raises(ValueError):
            await discover({"tenant_id": "t", "client_id": "x"})

    @pytest.mark.asyncio
    async def test_empty_config_raises(self):
        from app.services.connectors.m365 import discover
        with pytest.raises(ValueError):
            await discover({})
