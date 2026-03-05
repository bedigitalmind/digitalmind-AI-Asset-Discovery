"""
File Parser Service — Sprint 3
Parses uploaded files to extract AI asset signals before LLM enrichment.

Supported formats:
- CSV: Generic, M365 Unified Audit Log, proxy/firewall logs, browser history
- JSON: Azure Activity Logs, generic API response dumps
- TXT/LOG: Plain-text proxy logs

Each parser returns a list of RawSignal dicts that feed into the detection engine.
"""
import csv
import json
import io
import re
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from ..core.taxonomy import (
    classify_by_domain,
    classify_by_api_endpoint,
    ALL_ENTRIES,
    TaxonomyEntry,
)

logger = logging.getLogger(__name__)


@dataclass
class RawSignal:
    """A single extracted signal from a file."""
    name: str
    vendor: str | None
    category: str
    subcategory: str | None
    signal_type: str   # domain_access | api_call | audit_event | package_import | process_name
    signal_value: str  # the raw value (URL, domain, event name, etc.)
    confidence_score: float
    source_file: str
    raw_context: dict[str, Any] = field(default_factory=dict)
    is_shadow_ai: bool = False


# ─── Domain / URL classification helper ──────────────────────────────────────

def _classify_url(url: str) -> list[RawSignal]:
    """Try to match a URL against the taxonomy. Returns 0-N signals."""
    signals: list[RawSignal] = []
    try:
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        domain = parsed.netloc.lower().replace("www.", "")
    except Exception:
        return signals

    # Domain-based match
    entries = classify_by_domain(domain)
    for e in entries:
        signals.append(RawSignal(
            name=e.name, vendor=e.vendor,
            category=e.category, subcategory=e.subcategory,
            signal_type="domain_access", signal_value=domain,
            confidence_score=0.85,
            source_file="",
            raw_context={"url": url, "taxonomy_id": e.id},
        ))

    # API endpoint-based match (if no domain hit)
    if not entries:
        entries = classify_by_api_endpoint(url)
        for e in entries:
            signals.append(RawSignal(
                name=e.name, vendor=e.vendor,
                category=e.category, subcategory=e.subcategory,
                signal_type="api_call", signal_value=url,
                confidence_score=0.90,
                source_file="",
                raw_context={"url": url, "taxonomy_id": e.id},
            ))
    return signals


# ─── Parsers ──────────────────────────────────────────────────────────────────

class ParserResult:
    def __init__(self, file_name: str):
        self.file_name = file_name
        self.signals: list[RawSignal] = []
        self.errors: list[str] = []
        self.rows_processed: int = 0
        self.log_type_detected: str = "unknown"

    def add(self, signal: RawSignal) -> None:
        signal.source_file = self.file_name
        self.signals.append(signal)

    def deduplicate(self) -> None:
        """Keep one signal per (name, signal_type, signal_value) combination."""
        seen: set[tuple[str, str, str]] = set()
        unique: list[RawSignal] = []
        for s in self.signals:
            key = (s.name.lower(), s.signal_type, s.signal_value.lower())
            if key not in seen:
                seen.add(key)
                unique.append(s)
        self.signals = unique


class M365AuditLogParser:
    """
    Parses M365 Unified Audit Log CSV exports.
    Looks for AI-related workloads, operations, and user agents.
    Expected columns: CreationTime, RecordType, Operation, UserId, Workload, ...
    """
    # M365 AI-related operations and workloads
    AI_WORKLOADS = {"CopilotInteraction", "MicrosoftTeamsCopilot", "SharePointCopilot"}
    AI_OPERATIONS = {
        "CopilotInteraction", "AIChatInteraction", "AISuggestionAccepted",
        "AICompletionRequested", "SecurityCopilotInteraction",
    }
    AI_URL_PATTERNS = [
        "api.openai.com", "claude.ai", "copilot.microsoft.com",
        "bard.google.com", "gemini.google.com", "perplexity.ai",
        "github.com/features/copilot",
    ]

    def parse(self, content: str, result: ParserResult) -> None:
        result.log_type_detected = "M365 Unified Audit Log"
        try:
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                result.rows_processed += 1
                workload = row.get("Workload", "")
                operation = row.get("Operation", "")
                user_id = row.get("UserId", "")
                audit_data_raw = row.get("AuditData", "{}")

                # Copilot / AI events from M365 audit
                if workload in self.AI_WORKLOADS or operation in self.AI_OPERATIONS:
                    result.add(RawSignal(
                        name="Microsoft 365 Copilot",
                        vendor="Microsoft",
                        category="Copilots",
                        subcategory="Productivity Copilot",
                        signal_type="audit_event",
                        signal_value=f"{workload}/{operation}",
                        confidence_score=0.95,
                        source_file="",
                        raw_context={
                            "workload": workload, "operation": operation,
                            "user_id": user_id,
                        },
                    ))

                # Parse AuditData JSON for URLs
                try:
                    audit_data = json.loads(audit_data_raw)
                    for key in ("RequestURL", "TargetUrl", "Url", "ObjectId"):
                        url = audit_data.get(key, "")
                        if url:
                            signals = _classify_url(url)
                            for s in signals:
                                s.raw_context.update({"user_id": user_id, "operation": operation})
                                result.add(s)
                except Exception:
                    pass

        except Exception as e:
            result.errors.append(f"M365 audit parse error: {e}")


class ProxyLogParser:
    """
    Parses proxy/firewall access logs.
    Supports Squid, Zscaler, Palo Alto URL filtering CSVs, and generic access logs.
    Looks for AI domain hits.
    """
    # Common AI-related domain patterns (supplement taxonomy)
    AI_DOMAIN_PATTERNS = re.compile(
        r"(openai\.com|anthropic\.com|claude\.ai|gemini\.google\.com|"
        r"bard\.google\.com|perplexity\.ai|copilot\.microsoft\.com|"
        r"github\.com|huggingface\.co|replicate\.com|together\.ai|"
        r"mistral\.ai|cohere\.com|groq\.com|deepseek\.com|"
        r"api\.openai|api\.anthropic|generativelanguage\.googleapis)",
        re.IGNORECASE
    )

    def parse(self, content: str, result: ParserResult) -> None:
        result.log_type_detected = "Proxy/Firewall Access Log"
        lines = content.splitlines()

        # Try CSV first
        if "," in (lines[0] if lines else ""):
            self._parse_csv(content, result)
        else:
            self._parse_text(content, result)

    def _parse_csv(self, content: str, result: ParserResult) -> None:
        try:
            reader = csv.DictReader(io.StringIO(content))
            url_cols = ["url", "URL", "destination_url", "DestinationURL",
                        "request_url", "RequestURL", "host", "Host",
                        "domain", "Domain", "ServerIP"]
            for row in reader:
                result.rows_processed += 1
                url = ""
                for col in url_cols:
                    if col in row and row[col]:
                        url = row[col]
                        break
                if url and self.AI_DOMAIN_PATTERNS.search(url):
                    signals = _classify_url(url)
                    for s in signals:
                        s.raw_context.update(dict(row))
                        result.add(s)
        except Exception as e:
            result.errors.append(f"Proxy CSV parse error: {e}")

    def _parse_text(self, content: str, result: ParserResult) -> None:
        # Squid/plain log: extract URLs from each line
        url_re = re.compile(r'https?://[^\s"\'><]+', re.IGNORECASE)
        domain_re = re.compile(r'\b([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b')

        for line in content.splitlines():
            result.rows_processed += 1
            if not self.AI_DOMAIN_PATTERNS.search(line):
                continue
            urls = url_re.findall(line)
            for url in urls:
                signals = _classify_url(url)
                for s in signals:
                    s.raw_context["raw_line"] = line[:200]
                    result.add(s)
            # If no full URL found, try domain match
            if not urls:
                domains = domain_re.findall(line)
                for domain_match in domains:
                    domain = domain_match[0] if isinstance(domain_match, tuple) else domain_match
                    if self.AI_DOMAIN_PATTERNS.search(domain):
                        signals = _classify_url(domain)
                        for s in signals:
                            s.raw_context["raw_line"] = line[:200]
                            result.add(s)


class AzureActivityLogParser:
    """
    Parses Azure Monitor Activity Log JSON exports.
    Looks for AI-related resource operations.
    """
    AI_RESOURCE_TYPES = {
        "Microsoft.CognitiveServices", "Microsoft.MachineLearningServices",
        "Microsoft.BotService", "Microsoft.Search",
        "microsoft.cognitiveservices", "microsoft.machinelearningservices",
    }

    def parse(self, content: str, result: ParserResult) -> None:
        result.log_type_detected = "Azure Activity Log"
        try:
            data = json.loads(content)
            records = data if isinstance(data, list) else data.get("records", [data])
            for record in records:
                result.rows_processed += 1
                resource_id = record.get("resourceId", record.get("ResourceId", ""))
                resource_type_match = re.search(
                    r"providers/([^/]+/[^/]+)", resource_id, re.IGNORECASE
                )
                if not resource_type_match:
                    continue
                resource_type = resource_type_match.group(1)
                namespace = resource_type.split("/")[0]
                if namespace.lower() in {rt.lower() for rt in self.AI_RESOURCE_TYPES}:
                    from ..core.taxonomy import classify_by_azure_resource_type
                    entries = classify_by_azure_resource_type(resource_type)
                    if entries:
                        for e in entries:
                            result.add(RawSignal(
                                name=e.name, vendor=e.vendor,
                                category=e.category, subcategory=e.subcategory,
                                signal_type="azure_resource",
                                signal_value=resource_id,
                                confidence_score=0.95,
                                source_file="",
                                raw_context={"resource_id": resource_id, "record": record},
                            ))
                    else:
                        result.add(RawSignal(
                            name=resource_id.split("/")[-1],
                            vendor="Microsoft Azure",
                            category="Proprietary Models & Infrastructure",
                            subcategory="Azure AI Service",
                            signal_type="azure_resource",
                            signal_value=resource_id,
                            confidence_score=0.70,
                            source_file="",
                            raw_context={"resource_id": resource_id},
                        ))
        except json.JSONDecodeError as e:
            result.errors.append(f"JSON parse error: {e}")
        except Exception as e:
            result.errors.append(f"Azure activity log parse error: {e}")


class GenericCSVParser:
    """
    Fallback parser for generic CSVs.
    Scans all string columns for URLs, domains, and known AI tool names.
    """
    AI_TOOL_NAMES = {e.name.lower(): e for e in ALL_ENTRIES}
    AI_TOOL_PATTERN = re.compile(
        "|".join(re.escape(name) for name in AI_TOOL_NAMES.keys()),
        re.IGNORECASE
    )

    def parse(self, content: str, result: ParserResult) -> None:
        result.log_type_detected = "Generic CSV"
        try:
            reader = csv.DictReader(io.StringIO(content))
            url_re = re.compile(r'https?://[^\s"\'><,]+', re.IGNORECASE)
            for row in reader:
                result.rows_processed += 1
                row_text = " ".join(str(v) for v in row.values())

                # URL scanning
                urls = url_re.findall(row_text)
                for url in urls:
                    signals = _classify_url(url)
                    for s in signals:
                        s.raw_context.update({"row": dict(row)})
                        result.add(s)

                # Tool name scanning (only if no URL hit)
                if not urls and self.AI_TOOL_PATTERN.search(row_text):
                    matches = self.AI_TOOL_PATTERN.finditer(row_text)
                    for match in matches:
                        tool_name = match.group(0).lower()
                        if tool_name in self.AI_TOOL_NAMES:
                            e = self.AI_TOOL_NAMES[tool_name]
                            result.add(RawSignal(
                                name=e.name, vendor=e.vendor,
                                category=e.category, subcategory=e.subcategory,
                                signal_type="name_mention",
                                signal_value=match.group(0),
                                confidence_score=0.60,
                                source_file="",
                                raw_context={"row": dict(row)},
                            ))
        except Exception as e:
            result.errors.append(f"Generic CSV parse error: {e}")


# ─── Router / Dispatch ────────────────────────────────────────────────────────

def _detect_log_type(filename: str, content: str) -> str:
    """Heuristic to detect log type from filename + content."""
    fn = filename.lower()
    if "m365" in fn or "audit" in fn and "CreationTime" in content:
        return "m365_audit"
    if "activity" in fn and ("resourceId" in content or "ResourceId" in content):
        return "azure_activity"
    if fn.endswith(".json"):
        return "azure_activity"  # assume Azure Activity for JSON
    if any(x in fn for x in ["proxy", "squid", "zscaler", "firewall", "webfilter"]):
        return "proxy"
    if fn.endswith(".csv"):
        # Peek at headers
        first_line = content.split("\n")[0] if content else ""
        if "CreationTime" in first_line and "RecordType" in first_line:
            return "m365_audit"
        if "Workload" in first_line or "Operation" in first_line:
            return "m365_audit"
        return "generic_csv"
    if fn.endswith((".log", ".txt")):
        return "proxy"
    return "generic_csv"


async def parse_file(
    filename: str,
    content_bytes: bytes,
    use_llm_fallback: bool = True,
) -> ParserResult:
    """
    Main entry point. Parse a file and return extracted signals.

    Args:
        filename: Original filename (used for type detection)
        content_bytes: Raw file bytes
        use_llm_fallback: If True, send unmatched chunks to Claude for analysis
    """
    # Detect encoding
    try:
        import chardet
        detected = chardet.detect(content_bytes)
        encoding = detected.get("encoding") or "utf-8"
    except ImportError:
        encoding = "utf-8"

    try:
        content = content_bytes.decode(encoding, errors="replace")
    except Exception:
        content = content_bytes.decode("utf-8", errors="replace")

    result = ParserResult(filename)
    log_type = _detect_log_type(filename, content)

    if log_type == "m365_audit":
        M365AuditLogParser().parse(content, result)
    elif log_type == "azure_activity":
        AzureActivityLogParser().parse(content, result)
    elif log_type == "proxy":
        ProxyLogParser().parse(content, result)
    else:
        GenericCSVParser().parse(content, result)

    # LLM fallback for files with no/few matches
    if use_llm_fallback and len(result.signals) == 0 and len(content) > 100:
        from ..core.llm import analyze_log_chunk
        chunk = content[:4000]  # first 4k chars
        llm_signals = await analyze_log_chunk(log_type, chunk)
        for sig in llm_signals:
            result.add(RawSignal(
                name=sig.get("name", "Unknown AI Tool"),
                vendor=sig.get("vendor"),
                category=sig.get("category", "AI APIs & SDKs"),
                subcategory=None,
                signal_type=sig.get("signal_type", "llm_detected"),
                signal_value=sig.get("signal_value", ""),
                confidence_score=sig.get("confidence_score", 0.5),
                source_file="",
                raw_context={"llm_extracted": True},
            ))

    result.deduplicate()
    logger.info(
        f"Parsed {filename} ({log_type}): "
        f"{result.rows_processed} rows, {len(result.signals)} signals, "
        f"{len(result.errors)} errors"
    )
    return result
