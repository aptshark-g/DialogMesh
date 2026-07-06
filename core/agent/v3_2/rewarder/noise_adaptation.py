class NoiseAdaptation:
    INITIAL_NOISE = 0.5; MIN_SAMPLES = 500; WINDOW = 3

    def __init__(self):
        self.noise_level = self.INITIAL_NOISE
        self.history = {}; self.total = 0; self.window = 3

    def record_correction(self, key, text=""):
        if key not in self.history: self.history[key] = []
        import time; self.history[key].append({"text": text, "t": time.time()})
        self.total += 1

    def analyze(self):
        if self.total < self.MIN_SAMPLES: return
        contra = sum(1 for ev in self.history.values() for i in range(1,len(ev)) if ev[i]["t"]-ev[i-1]["t"]<180)
        if contra / max(self.total, 1) > 0.3:
            self.noise_level = min(1.0, self.noise_level + 0.1)
            self.window = 7