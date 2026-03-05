"""
Tests for the AI Asset Taxonomy — the core knowledge base.
These are pure unit tests with no database dependency.
"""
import pytest
from app.core.taxonomy import (
    TaxonomyEntry,
    ALL_ENTRIES,
    TAXONOMY_BY_ID,
    CATEGORIES,
    classify_by_domain,
    classify_by_api_endpoint,
    classify_by_azure_resource_type,
)


# ── Loading & integrity ───────────────────────────────────────────────────────

class TestTaxonomyLoading:
    def test_taxonomy_loaded(self):
        """Taxonomy must have at least 30 entries."""
        assert len(ALL_ENTRIES) >= 30, f"Expected ≥30 entries, got {len(ALL_ENTRIES)}"

    def test_taxonomy_by_id_index(self):
        """Every entry in ALL_ENTRIES must appear in TAXONOMY_BY_ID."""
        for entry in ALL_ENTRIES:
            assert entry.id in TAXONOMY_BY_ID, f"Entry '{entry.id}' missing from TAXONOMY_BY_ID"

    def test_categories_dict_has_all_taxonomy_cats(self):
        """CATEGORIES dict must contain all unique category keys used in entries."""
        used_categories = {e.category for e in ALL_ENTRIES}
        for cat in used_categories:
            assert cat in CATEGORIES, f"Category '{cat}' used in entries but missing from CATEGORIES dict"

    def test_no_duplicate_ids(self):
        """All taxonomy entry IDs must be unique."""
        ids = [e.id for e in ALL_ENTRIES]
        assert len(ids) == len(set(ids)), "Duplicate taxonomy IDs detected"

    def test_categories_values_non_empty(self):
        """Every CATEGORIES value (Portuguese label) must be non-empty."""
        for key, label in CATEGORIES.items():
            assert label.strip(), f"CATEGORIES['{key}'] has empty label"


# ── Data quality ──────────────────────────────────────────────────────────────

class TestTaxonomyDataQuality:
    VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}
    REQUIRED_CATEGORY_KEYS = {
        "conversational_ai", "copilot", "ai_agent",
        "embedded_saas", "erp_crm_ai", "ai_api", "own_model",
    }

    def test_risk_levels_valid(self):
        """All entries must use one of the four valid risk levels."""
        for entry in ALL_ENTRIES:
            assert entry.risk_level in self.VALID_RISK_LEVELS, (
                f"Entry '{entry.id}' has invalid risk_level: '{entry.risk_level}'"
            )

    def test_risk_scores_in_range(self):
        """Risk scores must be between 1 and 10."""
        for entry in ALL_ENTRIES:
            assert 1 <= entry.risk_score <= 10, (
                f"Entry '{entry.id}' has out-of-range risk_score: {entry.risk_score}"
            )

    def test_required_fields_not_empty(self):
        """Every entry must have non-empty id, name, vendor, category, description."""
        for entry in ALL_ENTRIES:
            assert entry.id.strip(), "Entry has empty id"
            assert entry.name.strip(), f"Entry '{entry.id}' has empty name"
            assert entry.vendor.strip(), f"Entry '{entry.id}' has empty vendor"
            assert entry.category.strip(), f"Entry '{entry.id}' has empty category"
            assert entry.description.strip(), f"Entry '{entry.id}' has empty description"

    def test_required_categories_present(self):
        """All 7 required category keys must exist in CATEGORIES."""
        for key in self.REQUIRED_CATEGORY_KEYS:
            assert key in CATEGORIES, f"Required category '{key}' missing from CATEGORIES"

    def test_critical_entries_have_signals(self):
        """Critical-risk SaaS entries should have at least one detection signal."""
        for entry in ALL_ENTRIES:
            if entry.risk_level == "critical" and entry.is_saas:
                has_signals = bool(
                    entry.domains or entry.api_endpoints or
                    entry.package_names or entry.process_names
                )
                assert has_signals, (
                    f"Critical SaaS entry '{entry.id}' has no detection signals"
                )


# ── Known entries ─────────────────────────────────────────────────────────────

class TestKnownEntries:
    def test_chatgpt_entry_exists(self):
        entry = TAXONOMY_BY_ID.get("conv-openai-chatgpt")
        assert entry is not None, "ChatGPT entry missing from taxonomy"
        assert entry.vendor == "OpenAI"
        assert "chat.openai.com" in entry.domains
        assert entry.risk_score >= 7

    def test_claude_entry_exists(self):
        entry = TAXONOMY_BY_ID.get("conv-anthropic-claude")
        assert entry is not None, "Claude entry missing from taxonomy"
        assert entry.vendor == "Anthropic"
        assert "claude.ai" in entry.domains

    def test_github_copilot_entry_exists(self):
        """GitHub Copilot must be in the taxonomy."""
        matches = [
            e for e in ALL_ENTRIES
            if "copilot" in e.name.lower() and "github" in e.vendor.lower()
        ]
        assert len(matches) >= 1, "GitHub Copilot not found in taxonomy"

    def test_azure_ai_entry_exists(self):
        """Azure AI services must be in the taxonomy."""
        matches = [
            e for e in ALL_ENTRIES
            if "azure" in e.id.lower() and
            any(kw in e.id.lower() for kw in ("openai", "cognitive", "ml"))
        ]
        assert len(matches) >= 1, "Azure AI (OpenAI/Cognitive/ML) not found in taxonomy"

    def test_conversational_ai_category_populated(self):
        conv_entries = [e for e in ALL_ENTRIES if e.category == "conversational_ai"]
        assert len(conv_entries) >= 5, (
            f"Expected ≥5 conversational_ai entries, got {len(conv_entries)}"
        )


# ── Classifier functions ──────────────────────────────────────────────────────

class TestClassifyByDomain:
    def test_classify_chatgpt_domain(self):
        results = classify_by_domain("chat.openai.com")
        assert len(results) >= 1
        assert any("OpenAI" in e.vendor for e in results)

    def test_classify_claude_domain(self):
        results = classify_by_domain("claude.ai")
        assert len(results) >= 1
        assert any("Anthropic" in e.vendor for e in results)

    def test_classify_unknown_domain_returns_empty(self):
        results = classify_by_domain("totally-unknown-company-xyz.io")
        assert results == []

    def test_classify_empty_domain_returns_empty(self):
        results = classify_by_domain("")
        assert results == []

    def test_returns_list_of_taxonomy_entries(self):
        results = classify_by_domain("chat.openai.com")
        for r in results:
            assert isinstance(r, TaxonomyEntry)


class TestClassifyByApiEndpoint:
    def test_classify_openai_api(self):
        results = classify_by_api_endpoint("api.openai.com/v1/chat/completions")
        assert len(results) >= 1
        assert any("OpenAI" in e.vendor for e in results)

    def test_classify_anthropic_api(self):
        results = classify_by_api_endpoint("api.anthropic.com/v1/messages")
        assert len(results) >= 1

    def test_classify_unknown_endpoint_returns_empty(self):
        results = classify_by_api_endpoint("api.completely-unknown-xyz.example.com/v99/predict")
        assert results == []


class TestClassifyByAzureResourceType:
    def test_classify_cognitive_services(self):
        results = classify_by_azure_resource_type("Microsoft.CognitiveServices/accounts")
        assert isinstance(results, list)
        assert len(results) >= 1, "CognitiveServices resource should match taxonomy"

    def test_classify_ml_workspace(self):
        results = classify_by_azure_resource_type("Microsoft.MachineLearningServices/workspaces")
        assert isinstance(results, list)
        assert len(results) >= 1, "MachineLearningServices workspace should match taxonomy"

    def test_classify_unknown_resource_returns_list(self):
        results = classify_by_azure_resource_type("Microsoft.Storage/storageAccounts")
        assert isinstance(results, list)

    def test_classify_empty_string(self):
        results = classify_by_azure_resource_type("")
        assert isinstance(results, list)
