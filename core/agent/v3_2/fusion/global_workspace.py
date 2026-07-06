from .models import TrackType, TrackResult

class GlobalWorkspace:
    BASE_PRIORITY = [TrackType.CAUSAL, TrackType.TRACK_0, TrackType.TRACK_1, TrackType.STRATEGIC, TrackType.TRACK_P]
    SUPPRESSION_LIMIT = 3

    def __init__(self):
        self.repression_count = {t: 0 for t in TrackType}
        self.last_dominant = None

    def select_dominant(self, tracks):
        cands = [t for t in tracks if t.is_confident()]
        if not cands: return None
        scored = []
        for t in cands:
            idx = self.BASE_PRIORITY.index(t.track) if t.track in self.BASE_PRIORITY else 99
            boost = self.repression_count.get(t.track, 0) // self.SUPPRESSION_LIMIT
            scored.append(((10 - idx) + boost, t.confidence, t))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        dom = scored[0][2]
        for t in self.repression_count:
            self.repression_count[t] = 0 if t == dom.track else self.repression_count.get(t, 0) + 1
        self.last_dominant = dom.track
        return dom

    def get_status(self):
        return {k.value: v for k, v in self.repression_count.items()}