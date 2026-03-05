"""
Shared base types and utilities for ERP/CRM connectors.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiscoveredAsset:
    """Standardised asset record returned by every connector."""
    external_id: str
    name: str
    vendor: str
    category: str
    subcategory: Optional[str] = None
    asset_type: Optional[str] = None
    platform: Optional[str] = None
    risk_level: str = "medium"
    risk_score: int = 5
    confidence_score: float = 0.9
    is_shadow_ai: bool = False
    source_details: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "external_id": self.external_id,
            "name": self.name,
            "vendor": self.vendor,
            "category": self.category,
            "subcategory": self.subcategory,
            "asset_type": self.asset_type,
            "platform": self.platform,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "confidence_score": self.confidence_score,
            "is_shadow_ai": self.is_shadow_ai,
            "source_details": self.source_details,
            "metadata": self.metadata,
        }


# ── Category/risk constants (mirror taxonomy) ─────────────────────────────────

RISK_MAP = {
    "critical": ("critical", 9),
    "high":     ("high",     7),
    "medium":   ("medium",   5),
    "low":      ("low",      3),
}

AI_KEYWORDS = {
    "einstein", "agentforce", "copilot", "gpt", "openai", "ai", "ml",
    "predict", "intelligence", "insight", "vision", "nlp", "machine",
    "language model", "generative", "chatbot", "virtual agent", "automation",
    "cognitive", "neural", "deep learning", "sentiment", "classification",
    "recommendation", "anomaly", "forecasting", "conversation",
}


def is_ai_related(text: str) -> bool:
    """Return True if any AI keyword is found in text (case-insensitive)."""
    lower = text.lower()
    return any(kw in lower for kw in AI_KEYWORDS)
