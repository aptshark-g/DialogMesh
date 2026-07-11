from dataclasses import dataclass

@dataclass
class CorrectionSignal:
    is_correction: bool = False
    correction_type: str = ""
    correct_path: str = ""
    confidence: float = 0.0
    edge_key: str = ""

class CorrectionDetector:
    NEGATIONS = ["不对", "不是", "不要", "换", "错了", "重来"]

    def __init__(self):
        self.fail_counts = {}

    def reset(self):
        self.fail_counts = {}

    def success(self, edge_key: str):
        self.fail_counts.pop(edge_key, None)

    def detect(self, text, prev_actions, current, edge_hist=None):
        for kw in self.NEGATIONS:
            if kw in text:
                idx = text.find(kw) + len(kw)
                alt = text[idx:].strip().split("。")[0] if idx < len(text) else ""
                return CorrectionSignal(True, "explicit", alt, 0.9 if alt else 0.6)
        if len(prev_actions) >= 2 and prev_actions[-1] == current:
            return CorrectionSignal(True, "rollback", "", 0.7)
        if edge_hist is not None and current.endswith("failure"):
            key = (prev_actions[-1] if prev_actions else "?") + "->" + current
            self.fail_counts[key] = self.fail_counts.get(key, 0) + 1
            if self.fail_counts[key] >= 3:
                return CorrectionSignal(True, "consecutive_failure", "", 0.6, key)
        else:
            # Non-failure turn: reset counts for this edge to avoid false positives
            if edge_hist is not None and prev_actions:
                key = prev_actions[-1] + "->" + current
                self.success(key)
        return CorrectionSignal()