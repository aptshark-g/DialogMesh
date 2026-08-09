"""Behavior chain white-box (A19) — `dm behavior` + `dm commitment` series.

Exposes the behavior-chain brain: scheduler decision, prediction result,
behavior graph, A18 parameter registry, principle distillation, and the
explicit-commitment lifecycle (user-declared + distilled).
"""

import asyncio
import json
import time

from core.agent.cli.engine import get_engine


def _brain(e, init=True):
    brain = getattr(e, "_behavior_brain", None)
    if brain is None and init and hasattr(e, "_init_behavior_brain"):
        e._init_behavior_brain()
        brain = getattr(e, "_behavior_brain", None)
    return brain


def _dump(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_behavior(args):
    """Behavior chain white-box: show/predict/graph/config/distill."""
    sub = getattr(args, "subcommand", "show")
    e = get_engine()
    brain = _brain(e)

    if sub == "show":
        if brain is None:
            _dump({"error": "behavior brain not available"})
            return
        stats = brain.stats()
        stats["ready"] = True
        stats["adapter"] = (
            getattr(e, "_behavior_graph_adapter", None).stats()
            if getattr(e, "_behavior_graph_adapter", None) else None
        )
        _dump(stats)
        return

    if sub == "predict":
        if brain is None:
            _dump({"error": "behavior brain not available"})
            return
        try:
            result = asyncio.run(brain.predict_next())
            _dump({
                "mode": result.query_mode,
                "predicted_top1": result.predicted_top1,
                "ask_clarification": result.ask_clarification,
                "latency_ms": result.latency_ms,
                "candidates": [
                    {
                        "action": c.action_summary,
                        "expected_value": round(c.expected_value, 4),
                        "llm_probability": round(c.llm_probability, 4),
                        "success_rate": round(c.success_rate, 4),
                        "cognitive_load": round(c.cognitive_load, 4),
                        "profile_match": round(c.profile_match, 4),
                    }
                    for c in result.candidates[:5]
                ],
                "scheduler": (
                    brain._last_decision.to_dict()
                    if brain._last_decision else None
                ),
            })
        except Exception as err:
            _dump({"error": str(err)})
        return

    if sub == "graph":
        if brain is None:
            _dump({"error": "behavior brain not available"})
            return
        g = brain.graph
        recent = sorted(g.nodes.values(), key=lambda s: s.timestamp)[-10:]
        _dump({
            "nodes": len(g.nodes),
            "edges": len(g.edges),
            "recent_chain": [
                {
                    "step_id": s.step_id,
                    "action": s.action_summary,
                    "action_type": s.action_type,
                }
                for s in recent
            ],
            "edges_sample": [
                {
                    "edge_id": ed.edge_id,
                    "weight": round(ed.weight, 4),
                    "success_rate": round(ed.success_rate, 4),
                    "sample_count": ed.sample_count,
                    "is_stable": ed.is_stable,
                }
                for ed in list(g.edges.values())[:10]
            ],
        })
        return

    if sub == "config":
        try:
            from core.agent.compiler.parameter_registry import get_registry
            reg = get_registry()
            key = getattr(args, "key", None)
            value = getattr(args, "value", None)
            params = reg.namespace("behavior")
            if key:
                if value is not None:
                    try:
                        typed = float(value) if "." in str(value) else int(value)
                    except ValueError:
                        typed = value
                    ok = reg.set(key, typed)
                    _dump({"set": key, "value": typed, "ok": ok})
                else:
                    _dump({"key": key, "value": reg.get(key)})
            else:
                _dump(params)
        except Exception as err:
            _dump({"error": str(err)})
        return

    if sub == "distill":
        if brain is None:
            _dump({"error": "behavior brain not available"})
            return
        created = brain.commitments.distill_from_graph(
            brain.graph,
            min_sample=int(getattr(args, "min_sample", 5) or 5),
            min_success=float(getattr(args, "min_success", 0.7) or 0.7),
        )
        _dump({
            "distilled": [c.to_dict() for c in created],
            "total_commitments": len(brain.commitments.list()),
        })
        return

    _dump({"error": f"Unknown subcommand {sub}"})


def cmd_commitment(args):
    """Explicit commitment lifecycle: list/add/arm/fire/complete/cancel/match."""
    sub = getattr(args, "subcommand", "list")
    e = get_engine()
    brain = _brain(e)
    if brain is None:
        _dump({"error": "behavior brain not available"})
        return
    reg = brain.commitments

    if sub == "list":
        status = getattr(args, "status", None)
        _dump({
            "stats": reg.stats(),
            "commitments": [c.to_dict() for c in reg.list(status=status)],
        })
        return

    if sub == "add":
        when = getattr(args, "when", None)
        should = getattr(args, "should", None)
        if not when or not should:
            _dump({"error": "usage: dm commitment add <when> <should> [--rather-than X] [--because Y]"})
            return
        c = reg.add(
            when=when,
            should=should,
            rather_than=getattr(args, "rather_than", "") or "",
            because=getattr(args, "because", "") or "",
            source="user",
        )
        _dump({"status": "ok", "added": c.to_dict()})
        return

    if sub in ("arm", "fire", "complete", "cancel", "expire"):
        cid = getattr(args, "id", None)
        if not cid:
            _dump({"error": f"usage: dm commitment {sub} <id>"})
            return
        method = getattr(reg, sub)
        c = method(cid)
        if c is None:
            _dump({"error": f"commitment {cid} not found or transition invalid"})
            return
        _dump({"status": "ok", "transition": sub, "commitment": c.to_dict()})
        return

    if sub == "match":
        text = getattr(args, "text", None)
        if not text:
            _dump({"error": "usage: dm commitment match <text>"})
            return
        _dump({
            "blocks": reg.context_blocks(text, max_blocks=3),
            "matched": [c.to_dict() for c in reg.match(text)],
        })
        return

    _dump({"error": f"Unknown subcommand {sub}"})


def register_cmds(subparsers):
    p = subparsers.add_parser("behavior", help="Behavior chain white-box (A19)")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("predict")
    sp.add_parser("graph")
    cfg = sp.add_parser("config")
    cfg.add_argument("key", nargs="?", default=None)
    cfg.add_argument("value", nargs="?", default=None)
    di = sp.add_parser("distill")
    di.add_argument("--min-sample", default=5)
    di.add_argument("--min-success", default=0.7)

    cp = subparsers.add_parser("commitment", help="Explicit commitment lifecycle")
    csp = cp.add_subparsers(dest="subcommand")
    lst = csp.add_parser("list")
    lst.add_argument("--status", default=None)
    a = csp.add_parser("add")
    a.add_argument("when")
    a.add_argument("should")
    a.add_argument("--rather-than", default="")
    a.add_argument("--because", default="")
    for name in ("arm", "fire", "complete", "cancel", "expire"):
        t = csp.add_parser(name)
        t.add_argument("id")
    m = csp.add_parser("match")
    m.add_argument("text")
