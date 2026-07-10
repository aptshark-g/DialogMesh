from .models import RewardSignal, ABLReflection
from .reward_rules import RewardRuleTable
from .time_decay import TimeDecay
from .noise_adaptation import NoiseAdaptation
from .abl_reflection import ABLReflectionGenerator
from .correction_detector import CorrectionDetector


class BehaviorRewarder:
    def __init__(self, graph, rules=None, decay=None, noise=None, abl=None):
        self.graph = graph
        self.rules = rules or RewardRuleTable()
        self.decay = decay or TimeDecay()
        self.noise = noise or NoiseAdaptation()
        self.abl = abl or ABLReflectionGenerator()
        self.correction_counts = {}

    def on_prediction_result(self, prediction, actual, is_correction=False,
                              delta_t=0.0, context="", turn=0, has_alternative=False):
        key = self._find_key(actual)
        if not key:
            return (RewardSignal("", 0), None)
        if is_correction:
            self.correction_counts[key] = self.correction_counts.get(key, 0) + 1
        raw = self.rules.evaluate(prediction, actual, is_correction, has_alternative=has_alternative)
        dec = self.decay.compute_decay(delta_t)
        edge = self.graph.edges.get(key) if hasattr(self.graph, "edges") else None
        fr = self.graph.nodes.get(edge.from_step_id) if edge else None
        is_exp = fr and fr.action_type == "EXPLORATION"
        sig = RewardSignal(key, raw, dec, self.noise.noise_level,
                           is_exploration=is_exp,
                           correction_count=self.correction_counts.get(key, 0))
        # Use noise.get_effective_reward instead of raw sig.compute_effective
        sig.effective_reward = self.noise.get_effective_reward(sig)
        if self.correction_counts.get(key, 0) >= 3 and edge:
            self._mark_persistent_error(key)
        ref = None
        if is_correction or raw < 0:
            top1 = prediction.top3[0].action_summary if prediction and prediction.top3 else ""
            ref = self.abl.generate(key, top1, actual, context, turn)
        return (sig, ref)

    def on_session_end(self):
        self._apply_to_graph(None, 0.0)
        self.correction_counts.clear()

    def _mark_persistent_error(self, edge_key):
        """Mark an edge as having persistent errors."""
        edge = self.graph.edges.get(edge_key) if hasattr(self.graph, "edges") else None
        if edge:
            edge.correction_mode = True
            edge.weight *= 0.3

    def _apply_to_graph(self, edge_key, effective_reward):
        """Apply decay to all edges and optionally update a specific edge."""
        if hasattr(self.graph, "edges"):
            for e in self.graph.edges.values():
                e.weight *= 0.95
        if edge_key and hasattr(self.graph, "edges"):
            edge = self.graph.edges.get(edge_key)
            if edge:
                edge.weight = max(0.0, min(1.0, edge.weight + effective_reward * 0.1))

    def _find_key(self, actual):
        if not hasattr(self.graph, "edges"):
            return None
        for k, e in self.graph.edges.items():
            ts = self.graph.nodes.get(e.to_step_id) if hasattr(self.graph, "nodes") else None
            if ts and ts.action_summary == actual:
                return k
        return None
