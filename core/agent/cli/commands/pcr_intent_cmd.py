"""PCR and Intent CLI commands."""
import json
from core.agent.cli.engine import get_engine, get_provider


def cmd_pcr(args):
    """Route text through Pre-Cognitive Router."""
    import asyncio
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    e = get_engine()
    
    pcr_inst = getattr(e, '_pcr_router', None)
    if pcr_inst:
        try:
            if hasattr(pcr_inst, 'process'):
                result = asyncio.run(pcr_inst.process(text))
                out = getattr(result, '__dict__', str(result)) if result else {}
                print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
                return
        except Exception as err:
            print(json.dumps({"error": str(err)}, ensure_ascii=False))
            return
    
    # Fallback: rule-based PCR from engine
    last_pcr = getattr(e, '_last_pcr', None)
    if last_pcr:
        info = {
            "zone": getattr(last_pcr, 'expectation', '?'),
            "complexity": getattr(last_pcr, 'complexity_level', 0),
            "mode": getattr(last_pcr, 'execution_mode', '?'),
            "style": getattr(last_pcr, 'prompt_style', '?'),
        }
        print(json.dumps(info, indent=2, ensure_ascii=False))
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

    # Intent
    p = subparsers.add_parser("intent", help="Intent parsing")
    sp = p.add_subparsers(dest="subcommand")
    ip = sp.add_parser("parse", help="Parse intent from text")
    ip.add_argument("text", nargs="+")

    # Context
    p = subparsers.add_parser("context", help="Context compilation")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show", help="Show compiled context")
