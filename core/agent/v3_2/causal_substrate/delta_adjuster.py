class DeltaAdjuster:
    INITIAL = 0.05; MAX = 0.15; MIN = 0.0
    def __init__(self):
        self.current = self.INITIAL
    def adjust(self, edge, cycle):
        if cycle % 50 != 0: return self.current
        if edge.structural_prior > 0.3 and edge.correction_count < 2:
            self.current = min(self.MAX, self.current + 0.02)
        elif edge.correction_count > 5:
            self.current = max(self.MIN, self.current - 0.02)
        return self.current