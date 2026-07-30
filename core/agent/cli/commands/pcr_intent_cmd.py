"""PCR and Intent CLI commands."""
import json
from core.agent.cli.engine import get_engine, get_provider


def cmd_pcr(args):
    """PCR routing, config, history."""
    sub = getattr(args, 'subcommand', 'route')
    e = get_engine()
    pcr = getattr(e, '_pcr_router', None)

    if sub == 'config':
        if pcr and hasattr(pcr, 'get_config'):
            cfg = pcr.get_config()
            print(json.dumps(cfg, indent=2, ensure_ascii=False, default=str))
        else:
            print(json.dumps({"error": "No PCR config available"}, ensure_ascii=False))
        return

    if sub == 'history':
        if pcr and hasattr(pcr, 'history'):
            hist = pcr.history()
            print(json.dumps(hist if isinstance(hist, dict) else {"history": hist}, indent=2, ensure_ascii=False, default=str))
        else:
            print(json.dumps({"history": []}, ensure_ascii=False))
        return

    if sub == 'set-config':
        key = getattr(args, 'key', None)
        val = getattr(args, 'value', None)
        if pcr and hasattr(pcr, 'set_config') and key:
            pcr.set_config(key, val)
            print(json.dumps({"status": "ok", "key": key, "value": val}, ensure_ascii=False))
        else:
            print(json.dumps({"error": "set_config not available"}, ensure_ascii=False))
        return

    if sub == 'reset-config':
        if pcr and hasattr(pcr, 'reset_config'):
            pcr.reset_config()
            print(json.dumps({"status": "ok", "msg": "PCR config reset"}, ensure_ascii=False))
        else:
            print(json.dumps({"error": "reset_config not available"}, ensure_ascii=False))
        return

    # Default: route
    import asyncio
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    if pcr:
        try:
            if hasattr(pcr, 'process'):
                result = asyncio.run(pcr.process(text))
                out = getattr(result, '__dict__', str(result)) if result else {}
                print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
                return
        except Exception as err:
            print(json.dumps({"error": str(err)}, ensure_ascii=False))
            return
    last_pcr = getattr(e, '_last_pcr', None)
    if last_pcr:
        print(json.dumps({"zone": getattr(last_pcr, 'expectation', '?'),
                          "complexity": getattr(last_pcr, 'complexity_level', 0),
                          "mode": getattr(last_pcr, 'execution_mode', '?'),
                          "style": getattr(last_pcr, 'prompt_style', '?')}, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"error": "No PCR router available"}, ensure_ascii=False))


def cmd_intent(args):
    """Parse intent from text."""
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    e = get_engine()
    
    parser = getattr(e, '_intent_parser', None)
    if parser and hasattr(parser, 'parse'):
        try:
            result = parser.parse(text)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return
        except Exception as err:
            pass
    
    # Try MultiLayerLLM
    ml = getattr(e, '_multilayer_llm', None)
    if ml:
        result = ml.intent(text)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"error": "No intent parser available"}, ensure_ascii=False))


def cmd_context(args):
    """Show compiled context from last event."""
    e = get_engine()
    ctx = getattr(e, '_last_context', None)
    if ctx and ctx.entries:
        entries = [{"type": getattr(ent, "type", "?"), "domain": getattr(ent, "domain", "?"),
                     "content": getattr(ent, "content", "")[:100]} for ent in ctx.entries]
        print(json.dumps({"entries": len(entries), "items": entries}, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"entries": 0, "items": [], "msg": "No context compiled yet. Use 'dm event send' first."}, ensure_ascii=False))


def register_cmds(subparsers):
    # PCR
    p = subparsers.add_parser("pcr", help="PCR routing")
    sp = p.add_subparsers(dest="subcommand")
    pr = sp.add_parser("route", help="Route text through PCR")
    pr.add_argument("text", nargs="+")
    sp.add_parser("config")
    sp.add_parser("history")
    sc = sp.add_parser("set-config")
    sc.add_argument("key")
    sc.add_argument("value")
    sp.add_parser("reset-config")

    # Intent
    p = subparsers.add_parser("intent", help="Intent parsing")
    sp = p.add_subparsers(dest="subcommand")
    ip = sp.add_parser("parse", help="Parse intent from text")
    ip.add_argument("text", nargs="+")

    # Context
    p = subparsers.add_parser("context", help="Context compilation")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show", help="Show compiled context")
    sp.add_parser("compile", help="Compile context from session")
    sp.add_parser("section"); sp.add_parser("ir-export"); sp.add_parser("ir-format")
