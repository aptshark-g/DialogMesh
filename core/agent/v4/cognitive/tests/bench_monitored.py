"""Monitored Chat Test — runs conversation + captures full ABC/Trace/Profile data per turn.

Output: data/monitor/chat_session_<ts>.jsonl — every turn's complete state.
After test, prints full analysis.
"""
import sys, os, json, time
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'

from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.events.event_ir import DialogAdapter

KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"

# MBTI-style prompts — analytical (T) vs emotional (F)
TURNS = [
    ("T", "I need a systematic analysis of the runtime architecture. What are the module dependencies?"),
    ("T", "Show me the exact design patterns used and their trade-offs. Be precise."),
    ("T", "What is the error handling hierarchy? I need try/except chain details."),
    ("T", "How would you test this end-to-end? Give specific coverage targets."),
    ("T", "What is the most critical module? Analyze its failure impact systematically."),
    ("F", "Help me understand the big picture — what feels most natural about this design?"),
    ("F", "I'm curious what excited you most when building this! What patterns surprised you?"),
    ("F", "How do you handle when things go wrong? I care about how the team copes emotionally."),
    ("F", "What's your favorite module? What makes working on it meaningful?"),
    ("F", "How do you make sure everything works together? What gives you confidence?"),
]


def run_monitored_test():
    ts = int(time.time())
    log_path = f"data/monitor/chat_session_{ts}.jsonl"
    os.makedirs("data/monitor", exist_ok=True)

    print("=" * 60)
    print("DialogMesh v6 — ABC Monitored Test")
    print(f"Log: {log_path}")
    print(f"Turns: {len(TURNS)} (5 T-type + 5 F-type)")
    print("=" * 60)

    prov = OpenAIProvider("deepseek", {
        "api_key": KEY, "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
    })
    eng = CognitiveRuntimeEngine(llm_provider=prov)
    eng.start()
    ad = DialogAdapter()

    all_events = []
    abc_hits = {"C": 0, "B": 0, "A": 0}

    for i, (style, text) in enumerate(TURNS):
        print(f"\n[{style}] Turn {i+1}/{len(TURNS)}: {text[:60]}...")

        response = eng.on_event(ad.adapt(text, style, i + 1))

        # ABC decision
        abc_decision = {}
        if hasattr(eng, '_abc') and eng._abc:
            abc_decision = eng._abc.decide(eng)
            layer = abc_decision.get("layer", "?")
            abc_hits[layer] = abc_hits.get(layer, 0) + 1

        # Trace
        m = eng._trace_v3.meta_analyze()
        rd = m.get("reason_distribution", {})

        # Profile
        tb = list(getattr(getattr(eng, '_cognitive_profile', None), 'track_b', {}).keys())

        # Record this turn
        event = {
            "turn": i + 1,
            "style": style,
            "text": text[:100],
            "response_len": len(response) if response else 0,
            "abc_layer": abc_decision.get("layer", "?"),
            "abc_rule": abc_decision.get("rule", ""),
            "abc_conf": abc_decision.get("confidence", 0),
            "trace_S": rd.get("strengthen", 0),
            "trace_W": rd.get("weaken", 0),
            "trace_R": rd.get("reject", 0),
            "trace_confidence": m.get("avg_confidence", 0),
            "trackB_tags": tb,
            "timestamp": time.time(),
        }
        all_events.append(event)

        # Live summary
        print(f"  ABC: L{event['abc_layer']} {event['abc_rule'] or 'default'} ({event['abc_conf']:.2f}) | "
              f"S={event['trace_S']} W={event['trace_W']} R={event['trace_R']} | "
              f"Tags={tb}")

    # Save
    with open(log_path, "w") as f:
        for event in all_events:
            f.write(json.dumps(event) + "\n")

    # Final analysis
    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)

    print(f"\nABC Layer Distribution: {abc_hits}")
    pct_c = abc_hits.get("C", 0) / len(all_events) * 100
    pct_b = abc_hits.get("B", 0) / len(all_events) * 100
    pct_a = abc_hits.get("A", 0) / len(all_events) * 100
    print(f"  C (symbolic): {pct_c:.0f}%  B (LLM): {pct_b:.0f}%  A (default): {pct_a:.0f}%")

    # Personality detection
    t_events = [e for e in all_events if e["style"] == "T"]
    f_events = [e for e in all_events if e["style"] == "F"]
    t_analytical = any("analytical" in e.get("trackB_tags", []) for e in t_events)
    f_emotional = any("emotional" in e.get("trackB_tags", []) for e in f_events)
    print(f"\nPersonality Detection:")
    print(f"  T-type → analytical: {'✅' if t_analytical else '❌'}")
    print(f"  F-type → emotional: {'✅' if f_emotional else '❌'}")

    # ABC stats
    if hasattr(eng, '_abc') and eng._abc:
        r = eng._abc.report()
        print(f"\nABC Engine: {json.dumps(r, indent=2)}")

    # Monitor events
    from core.agent.v4.cognitive.monitor_report import MonitorReport
    report = MonitorReport(f"chat_{ts}")
    report.collect(eng)
    report.finish()
    print(f"\nMonitorReport: {report.session_id}")

    print(f"\nFull log: {log_path}")
    return eng, all_events


if __name__ == "__main__":
    run_monitored_test()
