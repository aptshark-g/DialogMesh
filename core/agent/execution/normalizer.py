"""External Tool Normalizer — normalize OpenCode/Codex/MCP results to unified format.

ENGINEERING_FUSION: multi-tool coordination → normalized ExecutionResult → LLM dedup.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class NormalizedResult:
    """Unified format for any external tool output."""
    source: str                     # "opencode" / "codex" / "mcp" / "claude_code" / "pi"
    status: str                     # "success" / "failed" / "partial"
    summary: str                    # One-line summary
    artifacts: List[str] = field(default_factory=list)
    findings: List[Dict] = field(default_factory=list)
    raw: Optional[Any] = None       # Original tool output
    confidence: float = 0.5
    tokens_used: int = 0
    duration_ms: float = 0.0


class ExternalToolNormalizer:
    """Normalize heterogeneous external tool outputs → unified format."""

    def normalize(self, source: str, raw_output: Any) -> NormalizedResult:
        """Route to the correct normalizer based on source."""
        normalizers = {
            "opencode": self._from_opencode,
            "codex": self._from_codex,
            "mcp": self._from_mcp,
            "claude_code": self._from_claude_code,
            "pi": self._from_pi,
        }
        fn = normalizers.get(source, self._from_generic)
        return fn(raw_output)

    def _from_opencode(self, raw: Any) -> NormalizedResult:
        """OpenCode CLI output → normalized."""
        if isinstance(raw, dict):
            return NormalizedResult(
                source="opencode",
                status=raw.get("status", "unknown"),
                summary=str(raw.get("output", raw.get("result", "")))[:200],
                artifacts=raw.get("artifacts", raw.get("files_modified", [])),
                findings=self._extract_findings(raw),
                raw=raw,
                confidence=raw.get("confidence", 0.7),
            )
        return NormalizedResult(source="opencode", status="success",
                                summary=str(raw)[:200], raw=raw)

    def _from_codex(self, raw: Any) -> NormalizedResult:
        """OpenAI Codex CLI output → normalized."""
        if isinstance(raw, dict):
            return NormalizedResult(
                source="codex",
                status="success" if raw.get("completion") else "failed",
                summary=str(raw.get("completion", ""))[:200],
                artifacts=[raw.get("file", "")] if raw.get("file") else [],
                findings=self._extract_findings(raw),
                raw=raw,
                tokens_used=raw.get("tokens_used", 0),
            )
        return NormalizedResult(source="codex", status="success",
                                summary=str(raw)[:200], raw=raw)

    def _from_mcp(self, raw: Any) -> NormalizedResult:
        """MCP Tool output → normalized."""
        if isinstance(raw, dict):
            result = raw.get("result", raw)
            return NormalizedResult(
                source="mcp",
                status="success" if not raw.get("error") else "failed",
                summary=str(result)[:200],
                findings=self._extract_findings(raw),
                raw=raw,
            )
        return NormalizedResult(source="mcp", status="success",
                                summary=str(raw)[:200], raw=raw)

    def _from_claude_code(self, raw: Any) -> NormalizedResult:
        """Claude Code CLI output → normalized."""
        if isinstance(raw, dict):
            return NormalizedResult(
                source="claude_code",
                status=raw.get("status", "unknown"),
                summary=str(raw.get("output", raw.get("response", "")))[:200],
                artifacts=raw.get("files_written", raw.get("artifacts", [])),
                findings=self._extract_findings(raw),
                raw=raw,
            )
        return NormalizedResult(source="claude_code", status="success",
                                summary=str(raw)[:200], raw=raw)

    def _from_pi(self, raw: Any) -> NormalizedResult:
        """Pi agent output → normalized."""
        if isinstance(raw, dict):
            return NormalizedResult(
                source="pi",
                status=raw.get("status", "unknown"),
                summary=str(raw.get("output", raw.get("response", "")))[:200],
                artifacts=raw.get("files_modified", raw.get("artifacts", [])),
                findings=self._extract_findings(raw),
                raw=raw,
            )
        return NormalizedResult(source="pi", status="success",
                                summary=str(raw)[:200], raw=raw)

    def _from_generic(self, raw: Any) -> NormalizedResult:
        """Generic fallback normalizer."""
        return NormalizedResult(
            source="generic", status="success",
            summary=str(raw)[:200], raw=raw)

    def _extract_findings(self, data: dict) -> List[Dict]:
        """Extract security/quality findings from tool output."""
        findings = data.get("findings", data.get("vulnerabilities", []))
        if not findings and isinstance(data.get("output"), str):
            # Parse findings from text
            import re
            text = str(data.get("output", ""))
            for pattern, severity in [
                (r'sql.?injection', 'high'), (r'xss', 'high'),
                (r'race.condition', 'medium'), (r'memory.leak', 'medium'),
                (r'path.traversal', 'high'), (r'injection', 'medium'),
            ]:
                if re.search(pattern, text, re.IGNORECASE):
                    findings.append({"type": pattern.replace('.?', '_'),
                                    "severity": severity, "source": "text_parse"})
        return findings[:10]


class MultiToolFusion:
    """Fuse normalized results from multiple external tools."""

    def __init__(self, llm=None, param_registry=None):
        self._llm = llm
        self._params = param_registry

    def fuse(self, results: List[NormalizedResult]) -> NormalizedResult:
        """Merge multiple normalized results → one unified output.

        Dedup by finding type: same finding from multiple tools → keep highest confidence.
        """
        if not results:
            return NormalizedResult(source="fusion", status="failed",
                                    summary="No results")

        if len(results) == 1:
            return results[0]

        # Merge artifacts (dedup by filename)
        all_artifacts = []
        seen = set()
        for r in results:
            for a in r.artifacts:
                if a not in seen:
                    all_artifacts.append(a)
                    seen.add(a)

        # Merge findings (dedup by type, keep highest confidence)
        merged_findings = {}
        for r in results:
            for f in r.findings:
                ftype = f.get("type", str(f))
                if ftype not in merged_findings:
                    merged_findings[ftype] = f
                    merged_findings[ftype]["_sources"] = [r.source]
                else:
                    merged_findings[ftype]["_sources"].append(r.source)
                    old_conf = merged_findings[ftype].get("confidence", 0.5)
                    new_conf = f.get("confidence", 0.5)
                    if new_conf > old_conf:
                        merged_findings[ftype] = f
                        merged_findings[ftype]["_sources"] = [r.source]

        findings = list(merged_findings.values())

        # Summary
        sources = list(set(r.source for r in results))
        summary = f"[{'+'.join(sources)}] {len(findings)} findings, {len(all_artifacts)} artifacts"

        # LLM fusion for high-value cases
        if self._llm and len(findings) > 0 and any(
            f.get("severity") == "high" for f in findings):
            try:
                prompt = f"Fuse these findings from multiple tools into one sentence:\n{summary}"
                llm_summary = self._llm.generate(prompt, max_tokens=80, temperature=0.1)
                summary = llm_summary.strip() or summary
            except Exception:
                pass

        return NormalizedResult(
            source="fusion", status="success",
            summary=summary, artifacts=all_artifacts,
            findings=findings,
            confidence=max(r.confidence for r in results),
        )
