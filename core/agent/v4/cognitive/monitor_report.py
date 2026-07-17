"""MonitorReport — unified benchmark monitoring with replay capability.

Records ALL internal events per benchmark scenario for complete traceability.
Call it at benchmark start/end to guarantee data capture.
"""
from __future__ import annotations
import json, os, time, sys
from typing import Any, Dict, List, Optional


class MonitorReport:
    """Benchmark-level monitoring with guaranteed data capture.

    Unlike InternalStateMonitor (attached to engine, may be None),
    MonitorReport is self-contained and guarantees data is written.

    Usage:
        report = MonitorReport("reflection_bench")
        report.record("start", {"scenario": "math_error"})
        # ... run benchmark ...
        report.collect(engine)  # pull all engine internals
        report.finish()  # flush to JSONL + write summary
    """

    def __init__(self, benchmark_name: str, log_dir: str = "data/monitor"):
        self.benchmark = benchmark_name
        self.log_dir = log_dir
        self.session_id = f"{benchmark}_{int(time.time())}"
        self.events: List[dict] = []
        self.scenarios: Dict[str, dict] = {}
        self._start_time = time.time()
        os.makedirs(log_dir, exist_ok=True)

    def record(self, event_type: str, data: dict, scenario: str = ""):
        """Record one event."""
        self.events.append({
            "ts": time.time(),
            "type": event_type,
            "scenario": scenario,
            "data": data,
        })

    def collect(self, engine) -> dict:
        """Pull all engine internals into this report.

        Guaranteed to work even if engine._monitor is None.
        """
        info = {"time": time.time() - self._start_time}

        # Trace
        if hasattr(engine, '_trace_v3') and engine._trace_v3:
            m = engine._trace_v3.meta_analyze()
            info["transitions"] = m["total_transitions"]
            info["transition_types"] = sorted(m["reason_distribution"].keys())
            info["rejects"] = m["reason_distribution"].get("reject", 0)
            info["strengthen"] = m["reason_distribution"].get("strengthen", 0)
            self.record("trace", m)

        # Profile
        if hasattr(engine, '_cognitive_profile') and engine._cognitive_profile:
            ta = engine._cognitive_profile.track_a
            info["inertia"] = getattr(ta, 'cognitive_inertia', 0)
            info["trust"] = getattr(ta, 'trust_score', 0)
            info["observations"] = getattr(ta, 'observation_count', 0)
            self.record("profile", {
                "inertia": info["inertia"],
                "trust": info["trust"],
                "obs": info["observations"],
            })

        # Policy
        if hasattr(engine, '_active_policy') and engine._active_policy:
            p = engine._active_policy
            info["policy_perspective"] = getattr(p, 'perspective', '')
            info["policy_mode"] = getattr(p, 'explanation_mode', '')
            self.record("policy", {
                "perspective": info["policy_perspective"],
                "mode": info["policy_mode"],
            })

        # Mind
        if hasattr(engine, '_mind') and engine._mind:
            info["mind_relations"] = engine._mind.stats().get("active_relations", 0)
        if hasattr(engine, '_mind_attention') and engine._mind_attention:
            info["mind_anchors"] = engine._mind_attention.stats().get("total_updates", 0)
        if hasattr(engine, '_mind_mistakes') and engine._mind_mistakes:
            info["mind_rules"] = engine._mind_mistakes.stats().get("rules", 0)
        self.record("mind", {
            "relations": info.get("mind_relations", 0),
            "anchors": info.get("mind_anchors", 0),
            "rules": info.get("mind_rules", 0),
        })

        # DiscourseTree
        if hasattr(engine, '_discourse_tree'):
            for sid, tree in engine._discourse_tree._trees.items():
                blocks = getattr(tree, 'blocks', {})
                info["tree_blocks"] = len(blocks)
                info["tree_active"] = len(getattr(tree, 'active_blocks', lambda: [])())
                break
            if info.get("tree_blocks"):
                self.record("tree", {"blocks": info["tree_blocks"], "active": info.get("tree_active", 0)})

        return info

    def finish_scenario(self, name: str, result: dict):
        """Mark one scenario complete with results."""
        self.scenarios[name] = {
            "result": result,
            "events": len(self.events),
            "elapsed": time.time() - self._start_time,
        }

    def finish(self) -> str:
        """Write JSONL log + summary JSON. Returns log path."""
        log_path = os.path.join(self.log_dir, f"{self.session_id}.jsonl")
        with open(log_path, 'w', encoding='utf-8') as f:
            for e in self.events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

        summary = {
            "benchmark": self.benchmark,
            "session_id": self.session_id,
            "total_events": len(self.events),
            "duration_s": time.time() - self._start_time,
            "scenarios": len(self.scenarios),
            "event_types": {},
        }
        for e in self.events:
            t = e["type"]
            summary["event_types"][t] = summary["event_types"].get(t, 0) + 1

        for name, sc in self.scenarios.items():
            summary.setdefault("scenario_results", {})[name] = sc["result"]

        summary_path = os.path.join(self.log_dir, f"{self.session_id}_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print(f"  Monitor: {len(self.events)} events → {os.path.basename(log_path)}")
        return log_path

    @staticmethod
    def replay(log_path: str) -> List[dict]:
        """Read back a monitor log for analysis."""
        if not os.path.exists(log_path):
            return []
        events = []
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                events.append(json.loads(line))
        return events

    @staticmethod
    def replay_summary(log_dir: str = "data/monitor"):
        """Summarize all benchmark runs."""
        files = [f for f in os.listdir(log_dir) if f.endswith('_summary.json')]
        results = []
        for f in files:
            with open(os.path.join(log_dir, f)) as fp:
                results.append(json.load(fp))
        return results
