"""Benchmark runner — tests DialogMesh with real LLM against benchmark scenarios.

Scenarios:
  - persona_chat: personality tracking (INTJ vs ENFP)
  - multi_hop: multi-step reasoning (architecture → component → dependency)
  - topic_switch: discourse tree fork detection
  - continuous: long-form discussion quality

Each scenario generates monitor data for analysis.
"""
import sys, os, time, json
sys.path.insert(0, '.')
from core.agent.v4.cognitive.monitor_report import MonitorReport

from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.v4.event_ir import DialogAdapter
from core.agent.v4.cognitive.internal_monitor import InternalStateMonitor


DEEPSEEK_KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"


def create_engine():
    import os
    os.environ["DIALOGMESH_MONITOR"] = "1"  # force ON
    prov = OpenAIProvider("deepseek", {
        "api_key": DEEPSEEK_KEY,
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    })
    return CognitiveRuntimeEngine(llm_provider=prov)


def run_scenario(name: str, turns: list, label: str = ""):
    """Run a benchmark scenario and return monitor summary."""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    eng = create_engine()
    eng.start()
    ad = DialogAdapter()
    monitor = eng._monitor

    for i, (speaker, text) in enumerate(turns):
        if speaker == "USER":
            t0 = time.time()
            response = eng.on_event(ad.adapt(text, session_id=name, turn_number=i+1))
            elapsed = (time.time() - t0) * 1000
            print(f"  [{i+1:2d}] USER: {text[:60]}")
            print(f"       ASSISTANT: {(response or '')[:100]}... ({elapsed:.0f}ms)")
        # Save monitor every 3 turns
        if i % 3 == 0 and monitor:
            monitor.save()

    if monitor:
        monitor.save()  # don't flush — save keeps events
        summary = monitor.summary()
        # Also capture from trace
        trace = eng._trace_v3
        if trace:
            m = trace.meta_analyze()
            summary["trace_transitions"] = m["total_transitions"]
            summary["trace_reasons"] = m["reason_distribution"]
        print(f"\n  Monitor: {summary}")
        return summary
    return {}


# ═══════════════════════ Scenarios ═══════════════════════

PERSONA_INTJ = [
    ("USER", "I prefer working alone on complex problems. Systematic analysis is my approach."),
    ("USER", "Data and logic should guide decisions. Emotions cloud judgment."),
    ("USER", "Can you explain the architecture of this system?"),
    ("USER", "What design patterns are used and why were they chosen?"),
    ("USER", "How does the runtime handle edge cases? I need specific details."),
]

PERSONA_ENFP = [
    ("USER", "I love collaborating with the team! Brainstorming gives me so much energy!"),
    ("USER", "What feels right to me is more important than what's purely logical."),
    ("USER", "Can you give me a big-picture overview of this system?"),
    ("USER", "How do the different pieces work together? I want to understand the vision."),
    ("USER", "What's the most exciting part of this architecture?"),
]

MULTI_HOP = [
    ("USER", "How does the DialogMesh runtime work?"),
    ("USER", "What role does the Observer play in the pipeline?"),
    ("USER", "How does the Observer connect to the Workspace?"),
    ("USER", "What hypotheses are generated during workspace reasoning?"),
    ("USER", "How does the system resolve conflicts between hypotheses?"),
    ("USER", "What knowledge gets committed after reflection?"),
]

TOPIC_SWITCH = [
    ("USER", "Explain the architecture of DialogMesh."),
    ("USER", "Now let's talk about the profile system design."),
    ("USER", "Actually, switch back to architecture — how does CausalPlanner work?"),
    ("USER", "Let's discuss the extraction blueprint instead."),
    ("USER", "How does jieba parsing compare to Stanza for Chinese text?"),
    ("USER", "Going back to architecture — how does the ContextCompiler fit in?"),
]

if __name__ == "__main__":
    report = MonitorReport("bench_live")
    results = {}

    print("DialogMesh v6 Benchmark Suite")

    results["persona_intj"] = run_scenario("Persona: INTJ", PERSONA_INTJ)
    results["persona_enfp"] = run_scenario("Persona: ENFP", PERSONA_ENFP)
    results["multi_hop"] = run_scenario("Multi-Hop Reasoning", MULTI_HOP)
    results["topic_switch"] = run_scenario("Topic Switch Detection", TOPIC_SWITCH)

    # Save aggregate results
    os.makedirs("data/monitor", exist_ok=True)
    report.finish()
    with open("data/monitor/benchmark_summary.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{'='*60}")
    report = MonitorReport("bench_live")
    print("  Benchmark Complete")
    print(f"  Results: data/monitor/benchmark_summary.json")
    print(f"  Logs:    data/monitor/monitor_*.jsonl")
    print(f"{'='*60}")
