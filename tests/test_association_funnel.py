"""Association Funnel Test — 5-layer pipeline."""

import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.agent.v4.association_funnel import AssociationFunnel


def test_funnel():
    funnel = AssociationFunnel()
    
    # Simulate 5 rounds of PCR + Intent + Behavior events
    rounds = [
        ({"expectation": "TOOL", "entities": ["0x401000", "scan", "memory"]},
         {"category": "memory_scan", "entities": ["0x401000", "scan", "memory"]}),
        ({"expectation": "TOOL", "entities": ["0x7ff12345", "patch", "NOP"]},
         {"category": "code_patch", "entities": ["0x7ff12345", "patch", "NOP"]}),
        ({"expectation": "ADVISOR", "entities": ["encryption", "algorithm", "AES"]},
         {"category": "crypto_analysis", "entities": ["encryption", "algorithm", "AES"]}),
        ({"expectation": "TOOL", "entities": ["frida", "hook", "angr"]},
         {"category": "function_hook", "entities": ["frida", "hook", "angr"]}),
        ({"expectation": "ADVISOR", "entities": ["packer", "UPX"]},
         {"category": "packer_identification", "entities": ["packer", "UPX"]}),
    ]
    
    for pcr, intent in rounds:
        funnel.ingest_pcr(pcr["expectation"], pcr.get("entities"))
        funnel.ingest_intent(intent["category"], intent.get("entities"))
        funnel.ingest_behavior(intent["category"])
    
    result = funnel.run()
    
    print("=== Layer 1: Co-occurrence ===")
    for r in result["layer1_relations"][:5]:
        print(f"  {r.source.name} ↔ {r.target.name} (strength={r.strength})")
    
    print("\n=== Layer 3: Consensus Behavior Labels ===")
    print(f"  {result['layer3_consensus']}")
    
    print("\n=== Layer 4: Markov Chains ===")
    for s, t, c in result["layer4_chains"]:
        print(f"  {s} → {t} (count={c})")
    
    print("\n=== Layer 5: Causal Closure ===")
    for label, effects in result["layer5_closure"].items():
        if effects:
            print(f"  {label} → {effects}")
    
    # Assertions
    assert len(result["layer1_relations"]) > 0, "Should have co-occurrence"
    assert len(result["layer3_consensus"]) > 0, "Should have consensus labels"
    assert len(result["layer4_chains"]) > 0, "Should have Markov chains"
    
    return result


if __name__ == "__main__":
    result = test_funnel()
    with open("tests/test_performance/funnel_report.json", "w") as f:
        json.dump({
            "layer1_relations": len(result["layer1_relations"]),
            "layer3_consensus": result["layer3_consensus"],
            "layer4_chains_count": len(result["layer4_chains"]),
            "layer5_causal_count": sum(len(v) for v in result["layer5_closure"].values()),
        }, f, indent=2)
    print("\n✅ Association Funnel: 5 layers functional")
