"""Implicit Personality Extraction — measure "暗提取" not LLM capability.

Same architecture questions, asked in TWO different styles:
  T-style: analytical, systematic, demanding details
  F-style: people-oriented, big-picture, emotional

System should detect personality from HOW questions are asked,
not from explicit self-descriptions.

Metric: TrackB tags after 5 turns → does it tag personality_analytical
for T-style and personality_emotional for F-style?
"""
import sys, os, json
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'
import numpy as np
from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.events.event_ir import DialogAdapter

KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"

# Same questions, two styles
QUESTIONS = [
    "How is the runtime architecture organized?",
    "What design patterns are used and why?",
    "How should we handle error cases in the pipeline?",
    "What is the most important module and why?",
    "How would you test the whole system end-to-end?",
]

T_STYLE = [
    "I need to understand the runtime architecture — specifically the module dependencies and data flow. Be systematic.",
    "What design patterns are used? I want specific names and how they interact. Explain the rationale precisely.",
    "How should we handle error cases? I need the exact try/except hierarchy and fallback chains. Be detailed.",
    "What is the most critical module? Give me dependency analysis and failure impact. Be analytical.",
    "How would you test this end-to-end? I need specific test coverage targets and integration test strategies.",
]

F_STYLE = [
    "Help me get the big picture of how the runtime works — what feels most natural about the design?",
    "I'm curious about what design patterns you used! What's the most interesting connection you've discovered?",
    "How do you handle when things go wrong? I want to understand how the team deals with challenges.",
    "What's your favorite module? What makes working on it meaningful and exciting for you?",
    "How do you make sure everything works together well? I want to know what brings you confidence in the system.",
]


def run_implicit_test(provider_factory):
    """5 turns per style, compare TrackB tags after each session."""
    print("Implicit Personality Extraction Test")
    print("=" * 50)

    results = {}

    for style_name, prompts in [("T-style", T_STYLE), ("F-style", F_STYLE)]:
        eng = CognitiveRuntimeEngine(llm_provider=provider_factory())
        eng.start()
        ad = DialogAdapter()

        for i, prompt in enumerate(prompts):
            eng.on_event(ad.adapt(prompt, style_name, i + 1))

        # Collect TrackB tags — explicitly call infer_from_trace
        from core.agent.v4.cognitive.tag_layer import TagAcquisitionEngine
        TagAcquisitionEngine().infer_from_trace(eng._trace_v3, eng._cognitive_profile)
        profile = eng._cognitive_profile
        track_b = getattr(profile, 'track_b', {}) if profile else {}
        tags = list(track_b.keys())

        # Trace signals
        m = eng._trace_v3.meta_analyze()
        rd = m.get("reason_distribution", {})

        results[style_name] = {
            "tags": tags,
            "strengthen": rd.get("strengthen", 0),
            "weaken": rd.get("weaken", 0),
            "reject": rd.get("reject", 0),
        }

        print(f"\n  {style_name}:")
        print(f"    Trace: S={rd.get('strengthen',0)} W={rd.get('weaken',0)} R={rd.get('reject',0)}")
        print(f"    TrackB tags: {tags}")

    # Detection quality
    t_tags = results["T-style"]["tags"]
    f_tags = results["F-style"]["tags"]
    t_has_analytical = any("analytical" in t for t in t_tags)
    f_has_emotional = any("emotional" in t for t in f_tags)

    print(f"\n  Detection:")
    print(f"    T-style → analytical: {'✅' if t_has_analytical else '❌'}")
    print(f"    F-style → emotional: {'✅' if f_has_emotional else '❌'}")
    print(f"    Differentiation: {'✅' if t_has_analytical != f_has_emotional else '❌'}")

    os.makedirs("data/monitor", exist_ok=True)
    with open("data/monitor/implicit_personality.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    def make_prov():
        return OpenAIProvider("deepseek", {
            "api_key": KEY, "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
        })

    run_implicit_test(make_prov)
