"""ControlledExperiment — literature-backed A/B testing framework.

Formulas from:
  - Reflexion (Shinn et al., 2023): Reflection Improvement Rate
  - ReflectionBench (ICML 2025): Error Detection Rate
  - Guo et al. (2017): Confidence Calibration Error
  - Standard stats: Cohen's d for effect size

4 experiments:
  1. Mind ON vs OFF → WEAKEN reduction
  2. REJECT detection → Error Detection Rate
  3. Personality discrimination → Cohen's d
  4. DiscourseTree fork → topic switch sensitivity
"""
import sys, os, math, json, time
import numpy as np
sys.path.insert(0, '.')

from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.v4.event_ir import DialogAdapter


def cohens_d(group_a: list, group_b: list) -> float:
    """Cohen's d: standardized mean difference."""
    if len(group_a) < 2 or len(group_b) < 2:
        return 0.0
    mean_a, mean_b = np.mean(group_a), np.mean(group_b)
    var_a, var_b = np.var(group_a, ddof=1), np.var(group_b, ddof=1)
    pooled = math.sqrt((var_a + var_b) / 2)
    return (mean_a - mean_b) / max(pooled, 1e-6)


def error_detection_rate(detected: int, total: int) -> float:
    """ReflectionBench: correctly detected / total induced errors."""
    return detected / max(1, total)


def reflection_improvement(pre_score: float, post_score: float) -> float:
    """Reflexion: (post - pre) / pre."""
    return (post_score - pre_score) / max(pre_score, 0.01)


# ═══════════════════════════════════════════════════
# Experiment 1: Mind ON vs OFF
# ═══════════════════════════════════════════════════

def exp_mind_on_off(provider_factory):
    """Mind should reduce WEAKEN by pre-activating stable relations."""
    print("\n[E1] Mind ON vs OFF")
    print("-" * 30)

    results = {"on": [], "off": []}
    turns = [
        ("How does the runtime architecture work?", "n1"),
        ("Explain the Observer component.", "n2"),
        ("Now switch to profile system design.", "s1"),
        ("Actually, back to architecture.", "s2"),
        ("Switch to extraction blueprint.", "s3"),
        ("Back to profile system.", "s4"),
    ]

    # Control: Mind disabled
    eng = CognitiveRuntimeEngine(llm_provider=provider_factory())
    # Disable Mind for control
    if hasattr(eng, '_mind'):
        eng._mind = None
    eng.start()
    ad = DialogAdapter()
    for i, (text, sid) in enumerate(turns):
        eng.on_event(ad.adapt(text, sid, i + 1))
    m = eng._trace_v3.meta_analyze()
    results["off"].append(m["reason_distribution"].get("weaken", 0))

    # Treatment: Mind enabled (default)
    eng2 = CognitiveRuntimeEngine(llm_provider=provider_factory())
    eng2.start()
    for i, (text, sid) in enumerate(turns):
        eng2.on_event(ad.adapt(text, sid, i + 1))
    m2 = eng2._trace_v3.meta_analyze()
    results["on"].append(m2["reason_distribution"].get("weaken", 0))

    d = cohens_d(results["off"], results["on"])
    print(f"  WEAKEN: ON={results['on']} OFF={results['off']}")
    print(f"  Cohen's d={d:.2f} ({'large' if abs(d)>=0.8 else 'medium' if abs(d)>=0.5 else 'small'} effect)")
    return {"cohens_d": d, "interpretation": "Mind reduces WEAKEN" if d < -0.3 else "no significant effect"}


# ═══════════════════════════════════════════════════
# Experiment 2: REJECT Detection
# ═══════════════════════════════════════════════════

def exp_reject_detection(provider_factory):
    """Injected rejections should trigger MetaConsumer warnings."""
    print("\n[E2] REJECT Detection Rate")
    print("-" * 30)

    eng = CognitiveRuntimeEngine(llm_provider=provider_factory())
    eng.start()
    ad = DialogAdapter()

    reject_turns = [
        ("No, you are wrong about that.", "r1"),
        ("Still incorrect. Try again.", "r2"),
        ("Rethink and give a different answer.", "r3"),
        ("You're still wrong — one more try.", "r4"),
    ]

    injected = 0
    detected = 0
    for i, (text, sid) in enumerate(reject_turns):
        eng.on_event(ad.adapt(text, sid, i + 1))
        injected += 1
        # Check if REJECT transition was recorded
        m = eng._trace_v3.meta_analyze()
        if m["reason_distribution"].get("reject", 0) > 0:
            detected += 1

    edr = error_detection_rate(detected, injected)
    mc = eng._meta_consumer
    mc_warnings = 0
    if mc:
        advice = mc.consume(eng._trace_v3, len(reject_turns))
        mc_warnings = len(advice.get("warnings", []))

    print(f"  Injected: {injected}  Detected: {detected}  EDR={edr:.0%}")
    print(f"  MetaConsumer warnings: {mc_warnings}")
    return {"EDR": edr, "meta_warnings": mc_warnings, "passed": edr > 0.5}


# ═══════════════════════════════════════════════════
# Experiment 3: Personality Discrimination
# ═══════════════════════════════════════════════════

PERSONA_INTJ = [
    "I prefer working alone on complex problems. Systematic analysis.",
    "Data and logic should guide decisions. Emotions cloud judgment.",
    "Can you explain the architecture systematically?",
    "What design patterns are used and why?",
    "How does the runtime handle edge cases?",
]

PERSONA_ENFP = [
    "I love collaborating with the team! Brainstorming is energizing!",
    "What feels right is more important than what's purely logical.",
    "Can you give me a big-picture overview?",
    "How do the pieces work together? I want to understand the vision.",
    "What's the most exciting part of this architecture?",
]


def exp_personality_discrimination(provider_factory):
    """ENFP should produce more WEAKEN than INTJ (emotional vs analytical)."""
    print("\n[E3] Personality Discrimination")
    print("-" * 30)

    def measure_persona(turns, label):
        eng = CognitiveRuntimeEngine(llm_provider=provider_factory())
        eng.start()
        ad = DialogAdapter()
        weaken_events = []
        for i, text in enumerate(turns):
            eng.on_event(ad.adapt(text, label, i + 1))
            m = eng._trace_v3.meta_analyze()
            weaken_events.append(m["reason_distribution"].get("weaken", 0))
        total_weaken = sum(weaken_events)
        print(f"  {label}: WEAKEN={total_weaken} ({weaken_events})")
        return total_weaken

    intj_w = measure_persona(PERSONA_INTJ, "intj")
    enfp_w = measure_persona(PERSONA_ENFP, "enfp")
    d = cohens_d([intj_w], [enfp_w]) if intj_w != enfp_w else 0
    print(f"  Cohen's d={d:.2f}")
    print(f"  {'✅ discrimination' if abs(d) >= 0.5 else '⚠️ weak discrimination' if abs(d) >= 0.2 else '❌ no discrimination'}")
    return {"intj_weaken": intj_w, "enfp_weaken": enfp_w, "cohens_d": d}


# ═══════════════════════════════════════════════════
# Experiment 4: DiscourseTree Fork
# ═══════════════════════════════════════════════════

def exp_topic_fork(provider_factory):
    """Topic switching should produce more DiscourseTree forks."""
    print("\n[E4] DiscourseTree Fork Detection")
    print("-" * 30)

    eng = CognitiveRuntimeEngine(llm_provider=provider_factory())
    eng.start()
    ad = DialogAdapter()

    same_topic = [
        ("How does runtime work?", "st1"),
        ("What about the Observer?", "st2"),
        ("And the ContextCompiler?", "st3"),
    ]
    switch_topic = [
        ("Now switch to profile system.", "sw1"),
        ("Actually, back to architecture.", "sw2"),
        ("Switch to extraction blueprint.", "sw3"),
    ]

    def count_forks(turns):
        initial_blocks = len(eng._discourse_tree._trees)
        for text, sid in turns:
            eng.on_event(ad.adapt(text, sid, len(turns)))
        # Count new trees/forks created
        final_blocks = sum(len(getattr(t, 'blocks', {})) for t in eng._discourse_tree._trees.values())
        return final_blocks - initial_blocks

    same_forks = count_forks(same_topic)
    switch_forks = count_forks(switch_topic)
    print(f"  Same topic forks: {same_forks}")
    print(f"  Switch topic forks: {switch_forks}")
    ratio = switch_forks / max(1, same_forks)
    print(f"  Ratio: {ratio:.1f}x ({'✅ sensitive' if ratio >= 1.5 else '⚠️ insensitive'})")
    return {"same_forks": same_forks, "switch_forks": switch_forks, "ratio": ratio}


def run_all_experiments(provider_factory):
    """Run all 4 controlled experiments."""
    print("CONTROLLED EXPERIMENTS — Literature-Backed")
    print("=" * 50)

    results = {}
    results["e1_mind"] = exp_mind_on_off(provider_factory)
    results["e2_reject"] = exp_reject_detection(provider_factory)
    results["e3_personality"] = exp_personality_discrimination(provider_factory)
    results["e4_fork"] = exp_topic_fork(provider_factory)

    os.makedirs("data/monitor", exist_ok=True)
    with open("data/monitor/experiments.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{'=' * 50}")
    count = sum(1 for r in results.values() if r.get("passed", r.get("cohens_d", 0) > 0.3))
    print(f"  Experiments with significant effect: {count}/4")
    print(f"  Saved: data/monitor/experiments.json")


if __name__ == "__main__":
    from core.agent.llm_providers.openai_provider import OpenAIProvider

    def make_provider():
        return OpenAIProvider("lmstudio", {
            "api_key": "lm-studio",
            "base_url": "http://127.0.0.1:1234/v1",
            "model": "nvidia/nemotron-3-nano-4b",
        })

    run_all_experiments(make_provider)
