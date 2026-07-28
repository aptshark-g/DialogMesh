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
        nodes = []
        if result and hasattr(result, 'nodes'):
            nodes = [{"id": nd.id, "type": getattr(nd, 'type', '?'),
                       "label": getattr(nd, 'label', str(nd))} for nd in result.nodes]
        print(json.dumps({"nodes": nodes}, indent=2, ensure_ascii=False, default=str))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


def register_cmds(subparsers):
    p = subparsers.add_parser("subgraph", help="Subgraph compiler")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    e = sp.add_parser("expand")
    e.add_argument("text", nargs="+")
