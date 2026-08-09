"""Deprecated — delegates to PCRRouterV2 (zero hardcoded keywords)."""
from core.agent.pcr_router_v2 import PCRRouterV2, PCRResult, StructuralFeatures


class RuleBasedPCR(PCRRouterV2):
    """Backward-compatible wrapper. All logic in PCRRouterV2."""
    name = "rule_based_v2"

    def evaluate(self, query):
        """Old API — maps to route().

        Compatible with both str (legacy) and PCRInput_v1 object (PCRGate
        contract). PCRGate.evaluate passes PCRInput_v1(query=text, ...);
        we must extract .query before route, otherwise route receives the
        object and StructuralFeatures crashes ('PCRInput_v1' has no strip).
        """
        text = query
        if not isinstance(query, str):
            text = getattr(query, "query", "") or ""
        result = self.route(text)
        return _PCRLegacyOutput(result)


class _PCRLegacyOutput:
    """Adapter: PCRResult → PCROutput_v1 shape."""
    def __init__(self, r: PCRResult):
        self._r = r
        self.expectation = r.zone
        self.noise_level = 0.0
        self.complexity_level = {"light": 0.3, "moderate": 0.6, "heavy": 0.9}.get(r.cognitive_level, 0.5)
        self.cognitive_profile = None
        self.execution_mode = r.execution_mode
        self.prompt_style = r.prompt_style
        self.parser_config_overrides = {}
        self.ambiguous_strategy = "BALANCED"
        self.suggested_next_actions = []  # Zero hardcoded — LLM generates at runtime
        self.latency_ms = 0.0
        self.trace_log = [f"[V2] zone={r.zone}"]
        self.implementation = "rule_based_v2"


def register_pcr(name, cls):
    pass  # no-op for backward compatibility


__all__ = ["RuleBasedPCR", "register_pcr"]

ExpectationIdentifier = str  # backward compat alias
