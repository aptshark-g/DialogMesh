"""Subgraph + Format + Graph CLI commands."""
import json
from core.agent.cli.engine import get_engine, get_session


def cmd_subgraph_show(args):
    e = get_engine()
    sg = getattr(e, '_subgraph', None)
    if not sg:
        print(json.dumps({"error": "Subgraph compiler not loaded"}, ensure_ascii=False))
        return
    info = {"compiler": type(sg).__name__}
    last = getattr(e, '_last_subgraph', None)
    if last and hasattr(last, 'nodes'):
        info.update({"nodes": len(last.nodes), "edges": len(last.edges)})
    print(json.dumps(info, indent=2, ensure_ascii=False, default=str))


def cmd_subgraph_expand(args):
    e = get_engine()
    sg = getattr(e, '_subgraph', None)
    if not sg:
        print(json.dumps({"error": "Subgraph compiler not loaded"}, ensure_ascii=False))
        return
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    try:
        result = sg.expand_from_phrase(text) if hasattr(sg, 'expand_from_phrase') else (
            sg.expand(text) if hasattr(sg, 'expand') else None)
        if result:
                   "label": getattr(nd, 'label', str(nd))} for nd in (result.nodes if result else [])]
        print(json.dumps({"nodes": nodes}, indent=2, ensure_ascii=False, default=str))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


def register_cmds(subparsers):
    # Subgraph
    p = subparsers.add_parser("subgraph", help="Subgraph compiler operations")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show", help="Subgraph status")
    e = sp.add_parser("expand", help="Expand subgraph from phrase")
    e.add_argument("text", nargs="+")
