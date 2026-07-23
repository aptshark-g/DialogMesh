from .models import ABLReflection
import time
import json


class ABLReflectionGenerator:
    ERROR_TYPES = ["over_generalization", "missing_step", "wrong_entity", "domain_mismatch"]

    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    def generate(self, edge_key, predicted, actual, ctx="", turn=0):
        # Try LLM path first if available
        if self.llm_provider:
            try:
                raw = self._llm_generate(edge_key, predicted, actual, ctx)
                parsed = self._parse_llm_output(raw)
                if parsed:
                    return parsed
            except Exception:
                pass  # Fallback to rule-based
        # Rule-based fallback
        et = "wrong_entity"
        if predicted and actual and predicted[:2] == actual[:2]:
            et = "missing_step"
        return ABLReflection(edge_key, et, actual, "", "", turn, time.time())

    def _llm_generate(self, edge_key, predicted, actual, context):
        """Build prompt asking LLM to analyze why prediction was wrong."""
        prompt = (
            f"Analyze why the predicted action '{predicted}' was wrong "
            f"compared to the actual action '{actual}'.\n"
            f"Context: {context}\n"
            f"Return a JSON object with keys: error_type (one of {self.ERROR_TYPES}), "
            f"correct_path, why_wrong, suggested_correction."
        )
        if hasattr(self.llm_provider, "generate"):
            return self.llm_provider.generate(prompt)
        elif callable(self.llm_provider):
            return self.llm_provider(prompt)
        return "{}"

    def _parse_llm_output(self, raw):
        """Parse JSON string into ABLReflection fields."""
        if not raw or not isinstance(raw, str):
            return None
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            error_type = data.get("error_type", "wrong_entity")
            if error_type not in self.ERROR_TYPES:
                error_type = "wrong_entity"
            return ABLReflection(
                edge_key=data.get("edge_key", ""),
                error_type=error_type,
                correct_path=data.get("correct_path", ""),
                why_wrong=data.get("why_wrong", ""),
                suggested_correction=data.get("suggested_correction", ""),
                turn_count=data.get("turn_count", 0),
                timestamp=time.time(),
            )
        except json.JSONDecodeError:
            return None
