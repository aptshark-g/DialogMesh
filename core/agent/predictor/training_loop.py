from .models import TrainingSignal, Candidate, PredictionResult
from ..behavior_graph.models import BehaviorStep, BehaviorEdge
from ..behavior_graph.weight_updater import WeightUpdater
from ..behavior_graph.statistics import GraphStatisticsCollector
import time


class TrainingFeedbackLoop:
    """Full training feedback loop connecting predictions to graph weight updates."""

    def __init__(self, graph, weight_updater=None):
        self.graph = graph
        self.weight_updater = weight_updater or WeightUpdater()
        self._recent_updates = []
        self._correction_counts = {}

    def on_user_action(self, prediction, actual, actual_type, is_correction=False, delta_t=0.0):
        """Process a user action, update graph weights, and return training signal.

        Keeps backward compatibility with the old signature:
            on_user_action(self, prediction, actual, actual_type, is_correction=False)
        """
        # 1. Compute TrainingSignal reward
        signal = TrainingSignal(
            predicted=getattr(prediction, "candidates", []) if prediction else [],
            actual_action=actual,
            is_correction=is_correction,
        )
        signal.compute_reward()
        if is_correction:
            signal.reward = -0.20

        # 2. Find matching edge in graph by action_summary
        matched_edge_key = None
        matched_edge = None
        if self.graph and hasattr(self.graph, "edges"):
            for ek, edge in self.graph.edges.items():
                to_step = self.graph.nodes.get(edge.to_step_id)
                if to_step and to_step.action_summary == actual:
                    matched_edge_key = ek
                    matched_edge = edge
                    break

        # 3. If found: update edge weight using WeightUpdater
        if matched_edge:
            matched_edge.record_observation(success=(not is_correction), correction=is_correction)
            self.weight_updater.update_freq_ratio(matched_edge)
            matched_edge.weight = self.weight_updater.update(matched_edge)
            matched_edge.last_activated = time.time()
            matched_edge.activation_count += 1

        # 4. If correction: apply fast correction (downweight old path, create new edge)
        if is_correction:
            if matched_edge:
                matched_edge.weight = max(0.0, matched_edge.weight * 0.3)
                matched_edge.correction_mode = True
                self._correction_counts[matched_edge_key] = self._correction_counts.get(matched_edge_key, 0) + 1
            # Create new BehaviorStep + BehaviorEdge for corrected path
            new_step_id = f"step_{actual}_{int(time.time() * 1000)}"
            new_step = BehaviorStep(
                step_id=new_step_id,
                action_summary=actual,
                action_type=actual_type,
                timestamp=time.time(),
            )
            self.graph.add_step(new_step)
            # Link from the top predicted candidate if available
            top_candidates = getattr(prediction, "top3", []) if prediction else []
            if top_candidates:
                from_summary = top_candidates[0].action_summary
                from_step = None
                for s in self.graph.nodes.values():
                    if s.action_summary == from_summary:
                        from_step = s
                        break
                if from_step:
                    new_edge_key = self.graph.record_edge(from_step, new_step, success=True, correction=False)
                    matched_edge_key = new_edge_key
                    matched_edge = self.graph.edges.get(new_edge_key)

        # 5. If not found: create new BehaviorStep + BehaviorEdge
        if not matched_edge:
            new_step_id = f"step_{actual}_{int(time.time() * 1000)}"
            new_step = BehaviorStep(
                step_id=new_step_id,
                action_summary=actual,
                action_type=actual_type,
                timestamp=time.time(),
            )
            self.graph.add_step(new_step)
            # Try to link from a recent step if graph has nodes
            if self.graph.nodes:
                recent_step = max(
                    self.graph.nodes.values(),
                    key=lambda s: getattr(s, "timestamp", 0),
                )
                new_edge_key = self.graph.record_edge(recent_step, new_step, success=(not is_correction), correction=is_correction)
                matched_edge_key = new_edge_key
                matched_edge = self.graph.edges.get(new_edge_key)

        # 6. Update graph statistics
        if self.graph and hasattr(self.graph, "stats"):
            collector = GraphStatisticsCollector(self.graph)
            collector.update()

        # Log recent update
        self._recent_updates.append({
            "edge_key": matched_edge_key,
            "reward": signal.reward,
            "is_correction": is_correction,
            "timestamp": time.time(),
        })
        if len(self._recent_updates) > 100:
            self._recent_updates.pop(0)

        # 7. Return signal + updated edge key
        return (signal, matched_edge_key)

    def on_session_end(self):
        """Decay all edge weights by 0.95 and clear correction counts."""
        if self.graph and hasattr(self.graph, "edges"):
            for edge in self.graph.edges.values():
                edge.weight *= 0.95
                edge.correction_mode = False
        self._correction_counts.clear()
        # Update statistics after decay
        if self.graph and hasattr(self.graph, "stats"):
            collector = GraphStatisticsCollector(self.graph)
            collector.update()

    def get_training_report(self):
        """Return summary of recent updates."""
        if not self._recent_updates:
            return {"total_updates": 0, "corrections": 0, "avg_reward": 0.0, "latest": []}
        total = len(self._recent_updates)
        corrections = sum(1 for u in self._recent_updates if u["is_correction"])
        avg_reward = sum(u["reward"] for u in self._recent_updates) / total
        return {
            "total_updates": total,
            "corrections": corrections,
            "avg_reward": round(avg_reward, 4),
            "latest": self._recent_updates[-10:],
        }
