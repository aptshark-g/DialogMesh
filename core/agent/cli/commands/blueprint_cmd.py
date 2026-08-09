"""Blueprint + Decider CLI — DESIGN_CLI §8."""
import json
from core.agent.cli.engine import get_engine


def _build_dag(text, strategy):
    from core.agent.blueprint.engine import BlueprintEngine
    be = BlueprintEngine()
    dag = be.build(text, intent=text, strategy=strategy)
    return dag

def cmd_blueprint_show(args):
    dag = _build_dag("show", "TEMPLATE")
    nodes = [n.node_id for n in getattr(dag, 'nodes', [])]
    edges = [f"{e.from_node}->{e.to_node}" for e in getattr(dag, 'edges', [])]
    print(json.dumps({"nodes": nodes, "edges": edges, "strategy": getattr(dag, 'strategy', '?')},
                     indent=2, ensure_ascii=False))

def cmd_blueprint_build(args):
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    dag = _build_dag(text, "TEMPLATE")
    print(json.dumps({"nodes": getattr(dag, 'node_count', 0), "strategy": "TEMPLATE"}, ensure_ascii=False))

def cmd_blueprint_validate(args):
    dag = _build_dag("validate", "TEMPLATE")
    valid = dag is not None and getattr(dag, 'node_count', 0) > 0
    print(json.dumps({"valid": valid, "nodes": getattr(dag, 'node_count', 0),
                      "edges": len(getattr(dag, 'edges', []))}, ensure_ascii=False))

def cmd_blueprint_export(args):
    dag = _build_dag("export", "TEMPLATE")
    data = {"nodes": [n.node_id for n in getattr(dag, 'nodes', [])],
            "edges": [f"{e.from_node}->{e.to_node}" for e in getattr(dag, 'edges', [])],
            "strategy": getattr(dag, 'strategy', 'TEMPLATE')}
    print(json.dumps(data, indent=2, ensure_ascii=False))

def cmd_blueprint_build_hybrid(args):
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    dag = _build_dag(text, "HYBRID")
    print(json.dumps({"nodes": getattr(dag, 'node_count', 0), "strategy": "HYBRID", "mode": "template+LLM override"},
                     ensure_ascii=False))

def cmd_blueprint_build_llm(args):
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    dag = _build_dag(text, "LLM_DRIVEN")
    print(json.dumps({"nodes": getattr(dag, 'node_count', 0), "strategy": "LLM_DRIVEN", "mode": "full LLM DAG"},
                     ensure_ascii=False))

def cmd_blueprint_history(args):
    e = get_engine()
    be = getattr(e, '_blueprint_engine', None)
    if be and hasattr(be, 'history'):
        h = be.history()
        print(json.dumps({"history": str(h)[:200]}, ensure_ascii=False))
    else:
        from core.agent.blueprint.engine import BlueprintEngine
        dag1 = _build_dag("test1", "TEMPLATE")
        dag2 = _build_dag("test2", "HYBRID")
        print(json.dumps({"history": [{"template": dag1.node_count, "hybrid": dag2.node_count}]},
                         ensure_ascii=False))

def cmd_decider_show(args):
    e = get_engine()
    gd = getattr(e, '_decider', None)
    if gd:
        stats = gd.stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))
        return
    print(json.dumps({"error": "No decider"}, ensure_ascii=False))

def cmd_decider_chains(args):
    e = get_engine()
    gd = getattr(e, '_decider', None)
    if gd and hasattr(gd, 'stats'):
        s = gd.stats()
        print(json.dumps({"tick": s.get("tick", 0), "state": s.get("state", "idle")}, ensure_ascii=False))
        return
    print(json.dumps({"chains": []}, ensure_ascii=False))

def cmd_decider_execute(args):
    from core.agent.kernel import kernel_decider_execute
    text = " ".join(args.text) if hasattr(args, 'text') and args.text else "execute"
    print(json.dumps(kernel_decider_execute(text), indent=2, ensure_ascii=False))

def register_cmds(subparsers):
    p = subparsers.add_parser("blueprint", help="Blueprint DAG operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    b = sp.add_parser("build"); b.add_argument("text", nargs="+")
    sp.add_parser("validate")
    sp.add_parser("export")
    bh = sp.add_parser("build-hybrid"); bh.add_argument("text", nargs="+")
    bl = sp.add_parser("build-llm"); bl.add_argument("text", nargs="+")
    sp.add_parser("history")
    sp.add_parser("analyze")
    sp.add_parser("template-list")
    sp.add_parser("clear")
    sp.add_parser("diff")
    sp.add_parser("optimize")

    p = subparsers.add_parser("decider", help="Decider operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    sp.add_parser("chains")
    sp.add_parser("execute")
