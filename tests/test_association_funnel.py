"""Association Funnel V2 Test — rule-based + LLM mock."""

import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.agent.v4.association_funnel import AssociationFunnel


class MockLLM:
    """Mock LLM provider for test."""
    def __init__(self, responses: dict = None):
        self.responses = responses or {}
        self.calls = []

    def generate(self, prompt: str, max_tokens: int = 100) -> str:
        self.calls.append(prompt[:50])
        for key, val in self.responses.items():
            if key in prompt:
                return val
        return json.dumps([])


def test_funnel_rule():
    """Test without LLM — uses fallback rules."""
    funnel = AssociationFunnel()
    rounds = [
        {"text": "scan 0x401000", "expectation": "TOOL",
         "category": "memory_scan", "entities": ["0x401000", "scan"]},
        {"text": "patch the binary", "expectation": "TOOL",
         "category": "code_patch", "entities": ["NOP", "patch"]},
        {"text": "analyze encryption", "expectation": "TOOL",
         "category": "crypto_analysis", "entities": ["encryption", "AES"]},
        {"text": "hook frida", "expectation": "ADVISOR",
         "category": "function_hook", "entities": ["frida", "hook"]},
    ]

    for r in rounds:
        funnel.ingest_event({"kind": "pcr_computed", "payload": {"expectation": r["expectation"]}})
        funnel.ingest_event({"kind": "intent_parsed",
                            "payload": {"category": r["category"], "entities": r["entities"], "text": r["text"]}})

    result = funnel.run()
    print("=== V2 Rule-based (no LLM) ===")
    print(f"L1 relations: {len(result['layer1_relations'])}")
    print(f"L1.5 implicit: {result['layer1.5_implicit']}")
    print(f"L3 consensus: {result['layer3_consensus']}")
    print(f"L4 chains: {result['layer4_chains']}")
    print(f"L5 causal: {result['layer5_causal']}")
    print(f"Stats: {result['stats']}")
    assert len(result["layer3_consensus"]) > 0, "Should have consensus"
    assert result["stats"]["total_entities"] > 0
    assert result["stats"]["llm_calls"] == 0
    return result


def test_funnel_llm():
    """Test with Mock LLM — LLM generates hypotheses."""
    llm = MockLLM({
        "behavior labels": json.dumps(["memory_scan", "code_patch"]),
        "causal relationships": json.dumps({"memory_scan": "code_patch"}),
        "type category": json.dumps({"0x401000": "hex_address", "scan": "tool_name", "frida": "tool_name", "hook": "tool_name"}),
    })
    funnel = AssociationFunnel(llm_provider=llm)

    funnel.ingest_event({"kind": "intent_parsed",
                        "payload": {"category": "memory_scan",
                                   "entities": ["0x401000", "scan", "frida", "hook"],
                                   "text": "scan 0x401000 with frida hook"}})

    result = funnel.run()
    print("\n=== V2 LLM (mock) ===")
    print(f"LLM calls: {result['stats']['llm_calls']}")
    print(f"L3 consensus: {result['layer3_consensus']}")
    print(f"L3 beliefs: {json.dumps(result['layer3_all_beliefs'], indent=2)}")
    print(f"L5 causal: {result['layer5_causal']}")
    assert result["stats"]["llm_calls"] > 0, "Should use LLM"
    return result


if __name__ == "__main__":
    r = test_funnel_rule()
    r2 = test_funnel_llm()

    with open("tests/test_performance/funnel_v2_report.json", "w") as f:
        json.dump({"rule": r["stats"], "llm": r2["stats"]}, f, indent=2)

    print("\n✅ Association Funnel V2: rule + LLM both functional")
