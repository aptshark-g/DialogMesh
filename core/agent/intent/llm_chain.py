"""LLM-driven chain base — agent-native verification.

Each chain: algorithm pre-filter (zero-cost) → LLM verify (high-quality).
LLM is the coordinator, not a tool call.
"""

from __future__ import annotations
from typing import Optional, Any
from .models import ChainVote, FilterResult, SubIntent, VerifyContext


class LLMDrivenChain:
    """LLM-dominant chain verifier. Algorithm filters, LLM decides."""

    def __init__(self, llm=None, data_source: Any = None, name: str = ""):
        self.llm = llm
        self.data = data_source
        self.name = name

    def is_ready(self) -> bool:
        """Can this chain participate? Engineering chain overrides to False."""
        return True

    def verify(self, candidate: SubIntent, context: VerifyContext) -> ChainVote:
        """Two-step: algorithm filter → LLM verify."""
        # Step 1: algorithm pre-filter (zero cost)
        pre = self._algorithm_filter(candidate, context)
        if pre.outcome == "reject":
            return ChainVote(chain=self.name, confidence=0.1, decision="reject", reason=pre.reason)
        if pre.outcome == "accept":
            return ChainVote(chain=self.name, confidence=0.9, decision="accept", reason=pre.reason)
        if pre.outcome == "skip":
            return ChainVote(chain=self.name, confidence=0.5, decision="pass", reason=pre.reason)

        # Step 2: LLM verify (agent coordination)
        if not self.llm:
            return ChainVote(chain=self.name, confidence=0.5, decision="pass",
                           reason=f"{self.name}: LLM unavailable")

        prompt = self._build_llm_prompt(candidate, context, pre.hints)
        try:
            response = self.llm.generate(prompt, max_tokens=150, temperature=0.1)
            return self._parse_llm_response(response)
        except Exception as e:
            return ChainVote(chain=self.name, confidence=0.4, decision="pass",
                           reason=f"{self.name}: LLM error: {e}")

    def _algorithm_filter(self, candidate: SubIntent, context: VerifyContext) -> FilterResult:
        """Subclass: zero-cost pre-filter. Return accept/reject/pass."""
        return FilterResult(outcome="pass")

    def _build_llm_prompt(self, candidate: SubIntent, context: VerifyContext, hints: dict) -> str:
        """Subclass: build LLM verification prompt."""
        return ""

    def _parse_llm_response(self, response: str) -> ChainVote:
        """Parse LLM response. Default: accept if contains 'yes'/'accept', reject if 'no'."""
        import json, re

        # Try JSON first
        try:
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(response))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            data = json.loads(cleaned)
            return ChainVote(
                chain=self.name,
                confidence=float(data.get("confidence", 0.5)),
                decision=data.get("decision", "pass"),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # Fallback: keyword detection
        lower = str(response).lower()
        if "yes" in lower or "accept" in lower or "支持" in lower:
            nums = [float(t) for t in re.findall(r'[\d.]+', str(response))]
            conf = nums[0] if nums else 0.7
            return ChainVote(chain=self.name, confidence=conf, decision="accept",
                           reason=str(response)[:100])

        if "no" in lower or "reject" in lower or "不支持" in lower:
            return ChainVote(chain=self.name, confidence=0.2, decision="reject",
                           reason=str(response)[:100])

        return ChainVote(chain=self.name, confidence=0.5, decision="pass",
                       reason=str(response)[:100])
