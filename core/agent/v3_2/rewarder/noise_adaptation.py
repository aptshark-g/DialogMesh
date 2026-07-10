import time


class NoiseAdaptation:
    INITIAL_NOISE = 0.5
    MIN_SAMPLES = 500
    WINDOW = 3

    def __init__(self):
        self.noise_level = self.INITIAL_NOISE
        self.history = {}
        self.total = 0
        self.window = 3
        self._effectiveness = {}
        self._signal_strength = {}

    def record_correction(self, key, text=""):
        if key not in self.history:
            self.history[key] = []
        self.history[key].append({"text": text, "t": time.time()})
        self.total += 1

    def analyze(self):
        if self.total < self.MIN_SAMPLES:
            return
        contra = sum(
            1
            for ev in self.history.values()
            for i in range(1, len(ev))
            if ev[i]["t"] - ev[i - 1]["t"] < 180
        )
        if contra / max(self.total, 1) > 0.3:
            self.noise_level = min(1.0, self.noise_level + 0.1)
            self.window = 7
        # Analyze effectiveness and signal strength for all keys
        for key in list(self.history.keys()):
            self._analyze_effectiveness(key)
            self._analyze_signal_strength(key)

    def _analyze_effectiveness(self, key):
        """Compute success rate trend for a key over time."""
        events = self.history.get(key, [])
        if not events:
            self._effectiveness[key] = 0.5
            return
        # Treat recent corrections as failures, non-corrections as successes
        # Simplified: count events as failures (corrections), assume baseline success
        total_events = len(events)
        recent_window = events[-self.window :] if total_events >= self.window else events
        failure_rate = len(recent_window) / max(total_events, 1)
        self._effectiveness[key] = max(0.0, min(1.0, 1.0 - failure_rate))

    def _analyze_signal_strength(self, key):
        """Compute signal-to-noise ratio for corrections."""
        events = self.history.get(key, [])
        if not events:
            self._signal_strength[key] = 0.0
            return
        # Signal = unique meaningful corrections; Noise = rapid repeated corrections
        unique_texts = len(set(ev.get("text", "") for ev in events))
        total = len(events)
        # Compute time-spread: wider spread = stronger signal
        if total >= 2:
            time_span = events[-1]["t"] - events[0]["t"]
            density = total / max(time_span, 1.0)
        else:
            density = 1.0
        snr = unique_texts / max(density * total, 1.0)
        self._signal_strength[key] = max(0.0, min(1.0, snr))

    def get_effective_reward(self, signal):
        """Adjust raw reward based on noise level and signal strength."""
        raw = getattr(signal, "raw_reward", getattr(signal, "reward", 0.0))
        key = getattr(signal, "edge_key", "")
        effectiveness = self._effectiveness.get(key, 0.5)
        signal_strength = self._signal_strength.get(key, 0.5)
        # Higher noise reduces reward; higher effectiveness and signal strength boost it
        adjusted = raw * (1 - self.noise_level) * (0.5 + 0.5 * effectiveness) * (0.5 + 0.5 * signal_strength)
        return max(-1.0, min(1.0, adjusted))
