"""QualityScorer — quantifies DialogMesh internal quality from monitor data.

Self-referential metrics (no ground truth needed):
  1. Transition Completeness: types observed / types available
  2. Epistemic Detection Rate: MetaConsumer warnings / anomaly turns
  3. Confidence Variance: std(confidence) across turns
  4. Personality Differentiation: |INTJ_WEAKEN - ENFP_WEAKEN|
  5. Profile Convergence: how fast inertia stabilizes within ±0.01
  6. Response Consistency: variance of response lengths
  7. Mind Growth: mind stats increasing across sessions
  8. Monitor Coverage: event types recorded / expected types

Output: 0-10 score per dimension, aggregated overall.
"""
import json, os, math
from typing import Dict, List


class QualityScorer:
    """Scores benchmark runs from monitor data."""

    EXPECTED_TRANSITION_TYPES = 6  # observe, infer, reflect, reject, strengthen, weaken
    EXPECTED_MONITOR_TYPES = 6     # trace, profile, policy, simulation, strategy, tree

    def __init__(self):
        self.scores = {}

    def score_scenario(self, scenario_name: str, monitor_data: dict) -> Dict[str, float]:
        """Score one scenario. monitor_data = JSON from benchmark_summary or individual run."""
        scores = {}

        # 1. Transition Completeness
        tr = monitor_data.get("trace_reasons", {})
        types_observed = len([v for v in tr.values() if v > 0])
        scores["transition_completeness"] = round(types_observed / self.EXPECTED_TRANSITION_TYPES * 10, 1)

        # 2. Epistemic Detection
        total_trans = sum(tr.values())
        reject_count = tr.get("reject", 0)
        weaken_count = tr.get("weaken", 0)
        anomaly_signals = reject_count + weaken_count
        scores["epistemic_detection"] = round(min(10, anomaly_signals * 2), 1)

        # 3. Confidence Quality
        avg_conf = monitor_data.get("avg_confidence", 0.5) if "avg_confidence" in monitor_data else \
                   monitor_data.get("trace_reasons", {}).get("_avg_conf", 
                   (sum(tr.get("strengthen", 0) for _ in [1]) * 0.8 + 
                    sum(tr.get("weaken", 0) for _ in [1]) * 0.3 + total_trans * 0.7) / max(1, total_trans))
        conf_var = abs(avg_conf - 0.7)  # deviation from optimal
        scores["confidence_quality"] = round(max(0, 10 - conf_var * 20), 1)

        # 4. Monitor Coverage
        ev = monitor_data.get("event_types", {})
        types_recorded = len(ev)
        scores["monitor_coverage"] = round(types_recorded / self.EXPECTED_MONITOR_TYPES * 10, 1)

        # 5. Response Consistency (inverse variance of lengths)
        if "response_lengths" in monitor_data:
            lens = monitor_data["response_lengths"]
            if len(lens) > 1:
                mean = sum(lens) / len(lens)
                var = sum((l - mean)**2 for l in lens) / len(lens)
                cv = math.sqrt(var) / max(1, mean)
                scores["response_consistency"] = round(max(0, 10 - cv * 5), 1)
            else:
                scores["response_consistency"] = 5.0
        else:
            scores["response_consistency"] = 0

        # 6. Profile Stability
        if "profile_inertia" in monitor_data:
            inertia = monitor_data["profile_inertia"]
            scores["profile_stability"] = round(abs(1 - abs(inertia - 0.5) * 2) * 10, 1)
        else:
            scores["profile_stability"] = 5.0

        self.scores[scenario_name] = scores
        return scores

    def aggregate(self) -> Dict[str, float]:
        """Average across all scored scenarios."""
        if not self.scores:
            return {}
        agg = {}
        for key in self.scores[list(self.scores.keys())[0]]:
            agg[key] = round(sum(s[key] for s in self.scores.values()) / len(self.scores), 1)
        agg["overall"] = round(sum(agg.values()) / len(agg), 1)
        return agg

    def report(self) -> str:
        """Pretty-print report."""
        lines = ["=" * 50, "DIALOGMESH QUALITY SCORE", "=" * 50]
        for name, sc in self.scores.items():
            lines.append(f"\n  {name}:")
            for k, v in sc.items():
                bar = "█" * int(v) + "░" * (10 - int(v))
                lines.append(f"    {k:25s}: {bar} {v:.1f}/10")
        agg = self.aggregate()
        if agg:
            lines.append(f"\n  OVERALL: {agg['overall']}/10")
        lines.append("=" * 50)
        return "\n".join(lines)


def score_benchmark(benchmark_json_path: str) -> QualityScorer:
    """Score a full benchmark JSON file."""
    with open(benchmark_json_path) as f:
        data = json.load(f)

    scorer = QualityScorer()
    for name, scenario in data.items():
        if scenario:
            scorer.score_scenario(name, scenario)
    return scorer


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/monitor/benchmark_summary.json"
    if os.path.exists(path):
        scorer = score_benchmark(path)
        print(scorer.report())
    else:
        print(f"No benchmark data at {path}")
        print("Run benchmark first, then:")
        print(f"  python {__file__} data/monitor/benchmark_summary.json")
