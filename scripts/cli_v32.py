#!/usr/bin/env python3
"""DialogMesh v3.2 CLI - local mode, no backend needed"""
import sys, os, json, asyncio, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.agent.v3_2.testing_utils import MockLLM, DEFAULT_COMPILER_RESPONSE
from core.agent.v3_2.integration import V32Pipeline

def main():
    ap = argparse.ArgumentParser(description="DialogMesh v3.2 CLI")
    ap.add_argument("query", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--graph", action="store_true")
    args = ap.parse_args()

    pipe = V32Pipeline(MockLLM(DEFAULT_COMPILER_RESPONSE))

    qs = [args.query] if args.query else [l.strip() for l in sys.stdin if l.strip()]
    for q in qs:
        if q.lower() in ("exit", "quit"):
            break
        r = asyncio.run(pipe.process(q))
        p = r["parse"]
        f = r["fusion"]

        if args.json:
            out = {"turn": r["turn"], "stability": p.stability, "slots": p.to_dict().get("slots", {})}
            print(json.dumps(out, ensure_ascii=False))
            continue

        print()
        print("[Turn {}] Stability: {:.3f}".format(r["turn"], p.stability))
        for name, slot in p.slots.items():
            print("  {}: {} (conf={:.2f}, src={})".format(name, slot.value, slot.confidence, slot.source))

        if args.debug:
            print("  Utterance: {} | Degraded: {}".format(p.utterance_type, p.degraded))
            qm = getattr(f, "query_mode", "?")
            print("  Fusion: {:.3f} (mode: {})".format(f.confidence, qm))

        if args.graph:
            st = pipe.graph.get_statistics()
            print("  Graph: {} nodes, {} edges, {} samples".format(st.node_count, st.edge_count, st.total_samples))
        print()

if __name__ == "__main__":
    main()
