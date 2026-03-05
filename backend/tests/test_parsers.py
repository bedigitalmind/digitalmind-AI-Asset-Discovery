"""
Tests for the file parser service — no database required.
Tests cover: auto-detection logic, CSV/JSON parsing, signal extraction.

Note: parse_file() is async and returns ParserResult.
Individual parsers take (content: str, result: ParserResult) and mutate in-place.
"""
import pytest
from app.services.parser_service import (
    RawSignal,
    ParserResult,
    parse_file,
    M365AuditLogParser,
    ProxyLogParser,
    AzureActivityLogParser,
    GenericCSVParser,
)


# ── RawSignal dataclass ───────────────────────────────────────────────────────

class TestRawSignal:
    def test_raw_signal_creation(self):
        sig = RawSignal(
            name="ChatGPT",
            vendor="OpenAI",
            category="conversational_ai",
            subcategory="general_purpose_llm",
            signal_type="domain_access",
            signal_value="chat.openai.com",
            confidence_score=0.85,
            source_file="audit.csv",
        )
        assert sig.name == "ChatGPT"
        assert sig.vendor == "OpenAI"
        assert sig.confidence_score == 0.85
        assert sig.is_shadow_ai is False  # default

    def test_raw_signal_shadow_ai_flag(self):
        sig = RawSignal(
            name="Unknown AI",
            vendor=None,
            category="conversational_ai",
            subcategory=None,
            signal_type="domain_access",
            signal_value="shadow-ai-tool.example.com",
            confidence_score=0.5,
            source_file="proxy.log",
            is_shadow_ai=True,
        )
        assert sig.is_shadow_ai is True


# ── ParserResult ──────────────────────────────────────────────────────────────

class TestParserResult:
    def test_add_signal_sets_source_file(self):
        result = ParserResult("test.csv")
        sig = RawSignal(
            name="Test", vendor="V", category="cat", subcategory=None,
            signal_type="domain_access", signal_value="example.com",
            confidence_score=0.8, source_file="",
        )
        result.add(sig)
        assert sig.source_file == "test.csv"

    def test_deduplicate_removes_exact_duplicates(self):
        result = ParserResult("test.csv")
        for _ in range(3):
            result.add(RawSignal(
                name="ChatGPT", vendor="OpenAI", category="conversational_ai",
                subcategory=None, signal_type="domain_access",
                signal_value="chat.openai.com", confidence_score=0.85,
                source_file="",
            ))
        result.deduplicate()
        assert len(result.signals) == 1


# ── Auto-detection (parse_file dispatcher) ────────────────────────────────────

class TestParseFileDispatch:
    @pytest.mark.asyncio
    async def test_parse_m365_csv(self, sample_m365_audit_csv):
        result = await parse_file(
            "audit_log_20240115.csv",
            sample_m365_audit_csv,
            use_llm_fallback=False,
        )
        assert isinstance(result, ParserResult)
        assert isinstance(result.signals, list)
        assert all(isinstance(s, RawSignal) for s in result.signals)

    @pytest.mark.asyncio
    async def test_parse_proxy_csv(self, sample_proxy_log_csv):
        result = await parse_file(
            "proxy_log_jan2024.csv",
            sample_proxy_log_csv,
            use_llm_fallback=False,
        )
        assert isinstance(result, ParserResult)
        assert isinstance(result.signals, list)
        assert all(isinstance(s, RawSignal) for s in result.signals)

    @pytest.mark.asyncio
    async def test_parse_azure_json(self, sample_azure_activity_json):
        result = await parse_file(
            "azure_activity_2024.json",
            sample_azure_activity_json,
            use_llm_fallback=False,
        )
        assert isinstance(result, ParserResult)
        assert isinstance(result.signals, list)
        assert all(isinstance(s, RawSignal) for s in result.signals)

    @pytest.mark.asyncio
    async def test_parse_generic_csv(self, sample_generic_csv):
        result = await parse_file(
            "ai_tools_inventory.csv",
            sample_generic_csv,
            use_llm_fallback=False,
        )
        assert isinstance(result, ParserResult)
        assert isinstance(result.signals, list)
        assert all(isinstance(s, RawSignal) for s in result.signals)

    @pytest.mark.asyncio
    async def test_parse_empty_csv(self):
        result = await parse_file("empty.csv", b"col1,col2\n", use_llm_fallback=False)
        assert isinstance(result, ParserResult)
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_parse_corrupted_bytes(self):
        """Parser must not raise on corrupted/binary content."""
        result = await parse_file(
            "corrupted.csv",
            b"\xff\xfe\x00\x01\x02\x03garbage",
            use_llm_fallback=False,
        )
        assert isinstance(result, ParserResult)


# ── ProxyLogParser ────────────────────────────────────────────────────────────

class TestProxyLogParser:
    def _run(self, content_bytes: bytes, filename: str = "proxy.csv") -> ParserResult:
        content = content_bytes.decode("utf-8", errors="replace")
        result = ParserResult(filename)
        ProxyLogParser().parse(content, result)
        return result

    def test_detects_openai_domain(self, sample_proxy_log_csv):
        result = self._run(sample_proxy_log_csv)
        openai_signals = [s for s in result.signals if "openai" in s.signal_value.lower()]
        assert len(openai_signals) >= 1, (
            f"Expected OpenAI signal from proxy log. Got: {[s.signal_value for s in result.signals]}"
        )

    def test_detects_claude_ai(self, sample_proxy_log_csv):
        result = self._run(sample_proxy_log_csv)
        claude_signals = [s for s in result.signals if "claude" in s.signal_value.lower()]
        assert len(claude_signals) >= 1, (
            f"Expected Claude signal from proxy log. Got: {[s.signal_value for s in result.signals]}"
        )

    def test_confidence_scores_valid(self, sample_proxy_log_csv):
        result = self._run(sample_proxy_log_csv)
        for sig in result.signals:
            assert 0.0 <= sig.confidence_score <= 1.0, (
                f"Invalid confidence score {sig.confidence_score} for {sig.signal_value}"
            )

    def test_no_errors_on_valid_csv(self, sample_proxy_log_csv):
        result = self._run(sample_proxy_log_csv)
        assert result.errors == []


# ── AzureActivityLogParser ────────────────────────────────────────────────────

class TestAzureActivityLogParser:
    def _run(self, content_bytes: bytes, filename: str = "activity.json") -> ParserResult:
        content = content_bytes.decode("utf-8", errors="replace")
        result = ParserResult(filename)
        AzureActivityLogParser().parse(content, result)
        return result

    def test_detects_cognitive_services(self, sample_azure_activity_json):
        result = self._run(sample_azure_activity_json)
        cog_signals = [
            s for s in result.signals
            if "cognitive" in s.signal_value.lower() or "openai" in s.signal_value.lower()
        ]
        assert len(cog_signals) >= 1, (
            f"Expected CognitiveServices signal. Got: {[s.signal_value for s in result.signals]}"
        )

    def test_detects_ml_services(self, sample_azure_activity_json):
        result = self._run(sample_azure_activity_json)
        ml_signals = [
            s for s in result.signals
            if "machinelearning" in s.signal_value.lower() or "ml" in s.name.lower()
        ]
        assert len(ml_signals) >= 1, (
            f"Expected ML signal. Got: {[s.signal_value for s in result.signals]}"
        )

    def test_handles_malformed_json(self):
        result = self._run(b"{not valid json}")
        assert isinstance(result.signals, list)
        assert len(result.errors) >= 1  # should log a parse error

    def test_handles_empty_json_array(self):
        result = self._run(b"[]")
        assert result.signals == []
        assert result.errors == []


# ── M365AuditLogParser ────────────────────────────────────────────────────────

class TestM365AuditLogParser:
    def _run(self, content_bytes: bytes, filename: str = "audit.csv") -> ParserResult:
        content = content_bytes.decode("utf-8", errors="replace")
        result = ParserResult(filename)
        M365AuditLogParser().parse(content, result)
        return result

    def test_parses_without_errors(self, sample_m365_audit_csv):
        result = self._run(sample_m365_audit_csv)
        assert result.errors == []

    def test_rows_processed_count(self, sample_m365_audit_csv):
        result = self._run(sample_m365_audit_csv)
        # 4 data rows in fixture
        assert result.rows_processed == 4

    def test_log_type_detected(self, sample_m365_audit_csv):
        result = self._run(sample_m365_audit_csv)
        assert "M365" in result.log_type_detected or "Audit" in result.log_type_detected


# ── GenericCSVParser ──────────────────────────────────────────────────────────

class TestGenericCSVParser:
    def _run(self, content_bytes: bytes, filename: str = "inventory.csv") -> ParserResult:
        content = content_bytes.decode("utf-8", errors="replace")
        result = ParserResult(filename)
        GenericCSVParser().parse(content, result)
        return result

    def test_detects_chatgpt_url(self, sample_generic_csv):
        result = self._run(sample_generic_csv)
        chatgpt_signals = [s for s in result.signals if "openai" in s.signal_value.lower()]
        assert len(chatgpt_signals) >= 1, (
            f"Expected ChatGPT/OpenAI signal. Got: {[s.signal_value for s in result.signals]}"
        )

    def test_does_not_crash_on_empty_csv(self):
        result = self._run(b"col1,col2\n")
        assert isinstance(result.signals, list)
        assert result.errors == []

    def test_confidence_scores_positive(self, sample_generic_csv):
        result = self._run(sample_generic_csv)
        for sig in result.signals:
            assert sig.confidence_score > 0
