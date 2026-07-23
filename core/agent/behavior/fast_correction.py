"""快速纠正通道"""


class FastCorrectionDetector:
    CORRECTION_THRESHOLD = 2
    CORRECTION_WINDOW = 10

    def __init__(self, graph):
        self.graph = graph
        self._correction_log: dict[str, list[bool]] = {}

    def record_observation(self, edge_key: str, is_correction: bool):
        if edge_key not in self._correction_log:
            self._correction_log[edge_key] = []
        log = self._correction_log[edge_key]
        log.append(is_correction)
        if len(log) > self.CORRECTION_WINDOW:
            log.pop(0)

    def is_fast_correction_needed(self, edge_key: str) -> bool:
        log = self._correction_log.get(edge_key, [])
        if len(log) < self.CORRECTION_THRESHOLD:
            return False
        return all(log[-self.CORRECTION_THRESHOLD:])

    def apply_fast_correction(self, edge_key: str):
        edge = self.graph.edges.get(edge_key)
        if not edge:
            return
        edge.correction_mode = True

    def release_correction(self, edge_key: str):
        edge = self.graph.edges.get(edge_key)
        if edge:
            edge.correction_mode = False
        if edge_key in self._correction_log:
            self._correction_log[edge_key] = []
