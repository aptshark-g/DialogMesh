"""Subgraph + Format + Graph CLI commands."""
import json
from core.agent.cli.engine import get_engine, get_session


def cmd_subgraph_show(args):
    e = get_engine()
    sg = getattr(e, '_subgraph', None)
    if not sg:
        print(json.dumps({"error": "Subgraph compiler not loaded"}, ensure_ascii=False))
        return
    # Real compile (v4 SubgraphCompiler): dialogue + meta perspectives
    try:
        d = sg.compile_dialogue(intent="show", intent_category="query")
        info = {
            "compiler": type(sg).__name__,
            "dialogue": {"perspective": d.perspective, "entries": len(d.entries),
                         "tokens": d.total_tokens, "domains": d.domains},
        }
        if hasattr(sg, "compile_meta"):
            m = sg.compile_meta("")
            info["meta"] = {"perspective": m.perspective, "entries": len(m.entries),
                            "tokens": m.total_tokens}
        print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


def cmd_subgraph_expand(args):
    e = get_engine()
    sg = getattr(e, '_subgraph', None)
    if not sg:
        print(json.dumps({"error": "Subgraph compiler not loaded"}, ensure_ascii=False))
        return
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    try:
        result = sg.compile_dialogue(intent=text, intent_category="query")
        entries = [{"domain": e.domain, "confidence": e.confidence,
                    "source": e.source, "content": e.content[:120]} for e in result.entries]
        print(json.dumps({"perspective": result.perspective, "entries": entries,
                          "total_tokens": result.total_tokens},
                         indent=2, ensure_ascii=False, default=str))
    except Exception as err:
        print(json.dumps({"error": str(err)}, ensure_ascii=False))


def register_cmds(subparsers):
    p = subparsers.add_parser("subgraph", help="Subgraph compiler")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    e = sp.add_parser("expand")
    e.add_argument("text", nargs="+")
