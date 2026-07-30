"""Knowledge Graph CLI — DESIGN_CLI §17."""
import json
from core.agent.cli.engine import get_engine


def cmd_knowledge_query(args):
    e = get_engine()
    rb = getattr(e, '_rag_bridge', None)
    fl = getattr(e, '_frame_library', None)
    result = {"rag": None, "frames": None}
    if rb and hasattr(rb, 'query'):
        try:
            import asyncio
            r = asyncio.run(rb.query(args.keyword, limit=5))
            result["rag"] = str(r)[:200]
        except: pass
    if fl and hasattr(fl, 'query'):
        try:
            result["frames"] = str(fl.query(args.keyword))[:200]
        except: pass
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_knowledge_sources(args):
    e = get_engine()
    srcs = getattr(e, '_learning_sources', [])
    names = [type(s).__name__ for s in (srcs or [])]
    print(json.dumps({"sources": names}, ensure_ascii=False))


def cmd_knowledge_import(args):
    e = get_engine()
    rb = getattr(e, '_rag_bridge', None)
    if rb and hasattr(rb, 'load_from_file'):
        try:
            rb.load_from_file(args.file)
            print(json.dumps({"imported": True, "file": args.file}, ensure_ascii=False))
        except Exception as ex:
            print(json.dumps({"error": str(ex)}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "RAGBridge not available"}, ensure_ascii=False))


def register_cmds(subparsers):
    p = subparsers.add_parser("knowledge", help="Knowledge Graph operations")
    sp = p.add_subparsers(dest="subcommand")
    q = sp.add_parser("query"); q.add_argument("keyword")
    sp.add_parser("sources")
    i = sp.add_parser("import"); i.add_argument("file")
