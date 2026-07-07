# Topic Marker Dictionary + Layered Detector
# Layer 1: Dictionary matching (77 markers, 4 categories)
# Layer 2: Cross-domain entity detection
# Layer 3: LLM fallback (placeholder)

import os, json
from typing import List, Tuple, Optional

EXPLICIT = {
    "\u5bf9\u4e86": 0.95, "\u53e6\u5916": 0.90, "\u987a\u4fbf": 0.85,
    "\u8fd8\u6709": 0.80, "\u8bdd\u8bf4\u56de\u6765": 0.90,
    "\u6362\u4e2a\u8bdd\u9898": 1.0, "\u8bf4\u56de": 0.90,
    "\u56de\u5230": 0.85, "\u5173\u4e8e": 0.80, "\u8bf4\u5230": 0.85,
    "\u63d0\u5230": 0.85, "\u8bf4\u8d77\u6765": 0.80,
    "\u5bf9\u4e86\u8bf4\u5230": 0.95, "\u7a81\u7136\u60f3\u5230": 0.90,
    "\u6211\u60f3\u8d77\u6765": 0.85, "\u4e0d\u8bf4\u8fd9\u4e2a\u4e86": 1.0,
    "\u54e6\u5bf9\u4e86": 0.95, "\u5bf9\u4e86\u8fd8\u6709": 0.90,
    "\u987a\u4fbf\u95ee\u4e00\u4e0b": 0.90, "\u63d2\u4e00\u53e5": 0.85,
    "\u9898\u5916\u8bdd": 0.90, "\u8bdd\u8bf4": 0.85,
    "\u987a\u4fbf\u63d0\u4e00\u4e0b": 0.85, "\u8865\u5145\u4e00\u4e0b": 0.80,
    "\u518d\u8bf4": 0.75, "\u53e6\u5916\u518d\u8bf4": 0.85,
    "\u8fd8\u6709\u4e00\u4ef6\u4e8b": 0.90, "\u4e0d\u8c08\u8fd9\u4e2a\u4e86": 1.0,
    "\u804a\u70b9\u522b\u7684": 1.0, "\u6362\u4e2a\u4e8b\u8bf4": 0.95,
    "\u8a00\u5f52\u6b63\u4f20": 0.95, "\u56de\u5230\u6b63\u9898": 0.95,
    "\u8bf4\u6b63\u4e8b": 0.90, "\u5bf9\u4e86\u8bf4\u8d77": 0.90,
}

LOGIC = {
    "\u4f46\u662f": 0.80, "\u4e0d\u8fc7": 0.75, "\u7136\u800c": 0.80,
    "\u53ef\u662f": 0.75, "\u867d\u7136": 0.60, "\u5c3d\u7ba1": 0.60,
    "\u867d\u8bf4": 0.65, "\u4f46\u4e0d\u8fc7": 0.80, "\u53ea\u662f": 0.60,
    "\u4e0d\u8fc7\u8bdd\u8bf4\u56de\u6765": 0.90,
    "\u4f46\u8bdd\u8bf4\u56de\u6765": 0.90,
}

SEQUENCE = {
    "\u7136\u540e": 0.60, "\u63a5\u7740": 0.65, "\u4e4b\u540e": 0.55,
    "\u4e0b\u4e00\u6b65": 0.70, "\u63a5\u4e0b\u6765": 0.70,
    "\u968f\u540e": 0.65, "\u518d\u7136\u540e": 0.65, "\u4e0b\u9762": 0.60,
}

REFERENCE = {
    "\u521a\u624d\u90a3\u4e2a": 0.90, "\u4e4b\u524d\u8bf4\u7684": 0.90,
    "\u4e0a\u6b21\u8bf4\u7684": 0.90, "\u4e0a\u56de\u63d0\u5230\u7684": 0.90,
    "\u4f60\u521a\u624d\u8bf4": 0.85, "\u4e0a\u9762\u7684": 0.65,
    "\u56de\u770b": 0.70, "\u521a\u624d": 0.70, "\u90a3\u4e2a": 0.60,
}

ALL_MARKERS = {}
for d in [EXPLICIT, LOGIC, SEQUENCE, REFERENCE]:
    ALL_MARKERS.update(d)

SORTED_MARKERS = sorted(ALL_MARKERS.keys(), key=len, reverse=True)

class TopicMarkerDetector:
    """Layered topic switch detector: dict -> entity -> LLM"""
    def __init__(self, marker_file=""):
        self.markers = dict(ALL_MARKERS)
        self._sorted = list(SORTED_MARKERS)
        if marker_file and os.path.exists(marker_file):
            self._load(marker_file)

    def _load(self, path):
        try:
            extra = json.load(open(path, "r", encoding="utf-8"))
            self.markers.update(extra)
            self._sorted = sorted(self.markers.keys(), key=len, reverse=True)
        except Exception as e:
            print(f"[TopicMarker] Load failed: {e}")

    def detect_layer1(self, text):
        """Dictionary match, longest-first"""
        for marker in self._sorted:
            if marker in text:
                return [(marker, self.markers[marker])]
        return []

    def detect_layer2(self, curr_ents, prev_ents):
        """Entity domain mismatch signal"""
        if not curr_ents or not prev_ents:
            return 0.5
        s1, s2 = set(curr_ents), set(prev_ents)
        j = len(s1 & s2) / max(len(s1 | s2), 1)
        return 0.7 if j < 0.2 else 0.5 if j < 0.4 else 0.3

    def detect(self, text, curr_ents=None, prev_ents=None, llm=None):
        """(is_switch, confidence, source)"""
        l1 = self.detect_layer1(text)
        if l1:
            m, c = l1[0]
            if c >= 0.85:
                return True, c, f"dict:{m}"
        l2 = self.detect_layer2(curr_ents or [], prev_ents or [])
        if l2 >= 0.7:
            return True, l2, "entity"
        return False, max(0.0, l2), "none"

    CROSS_REF_PATTERNS = {
        "analogy": ["跟.*一样", "类似于", "和.*类似", "就像", "同样的道理", "同理", "跟.*一样的地方"],
        "continuation": ["接着说", "继续刚才", "回到"],
        "correction": ["不对", "错了", "不是这样", "更正一下"],
    }

    def detect_cross_ref(self, text: str) -> list:
        """Detect cross-topic references. Returns list of (ref_type, confidence)."""
        import re
        results = []
        for ref_type, patterns in self.CROSS_REF_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, text):
                    conf = 0.8 if ref_type in ("analogy", "correction") else 0.7
                    results.append((ref_type, conf))
                    break
        return results

DETECTOR = TopicMarkerDetector()
__all__ = ["DETECTOR", "TopicMarkerDetector"]
