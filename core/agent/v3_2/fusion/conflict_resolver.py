from .models import TrackType, TrackResult, StageOutput

class ConflictResolver:
    PRIORITY_ORDER = [
        TrackType.CAUSAL, TrackType.TRACK_0,
        TrackType.TRACK_1, TrackType.STRATEGIC, TrackType.TRACK_P,
    ]

    def resolve(self, stage):
        conflicts = []
        dominant = None
        for priority in self.PRIORITY_ORDER:
            cands = [t for t in stage.tracks if t.track == priority and t.is_confident()]
            if not cands: continue
            dominant = cands[0]
            for other in stage.tracks:
                if other.track != priority and other.is_confident():
                    c = self._detect_conflict(dominant, other)
                    if c: conflicts.append(c)
            break
        return (dominant, conflicts)

    def _detect_conflict(self, dom, other):
        if dom.track == TrackType.TRACK_1 and other.track == TrackType.TRACK_P:
            di = dom.output.get("intent", {})
            oa = other.output.get("predicted_actions", [])
            if di and oa:
                return {"type": "INTENT_ACTION_MISMATCH", "dominant": dom.track.value, "other": other.track.value}
        if dom.confidence > 0.8 and other.confidence > 0.8:
            dd = str(dom.output.get("decision", ""))
            od = str(other.output.get("decision", ""))
            if dd and od and dd != od:
                return {"type": "CONFIDENCE_DIVERGENCE", "dominant": dom.track.value, "other": other.track.value}
        return None

    def apply(self, dominant, conflicts):
        if dominant is None:
            return {"fallback": True, "confidence_reduction": 0.5, "ask_clarification": True}
        out = dict(dominant.output)
        for c in conflicts:
            if c["type"] == "CONFIDENCE_DIVERGENCE": out["conservative_mode"] = True
            if c["type"] == "INTENT_ACTION_MISMATCH": out["confidence_reduction"] = 0.2
        return out
