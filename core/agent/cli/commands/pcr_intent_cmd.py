"""PCR + Intent CLI commands — DESIGN_CLI §§5-6."""
import json
from core.agent.cli.engine import get_engine, get_session


# ═══ PCR ═══

def cmd_pcr(args):
    """PCR routing, config, history."""
    sub = getattr(args, 'subcommand', 'route')
    e = get_engine()
    pcr = getattr(e, '_pcr_router', None)

    if sub == 'config':
        # White-box config (A19): dimension weights / zone thresholds from YAML
        from core.agent.pcr_dimensions import load_config
        cfg = load_config()
        if cfg:
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

    # Default: route — PCRRouterV2.route(text) → PCRResult (zone + labels)
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    if pcr:
        try:
            if hasattr(pcr, 'route'):
                result = pcr.route(text)
                print(json.dumps({
                    "zone": getattr(result, 'zone', 'MIXED'),
                    "x_axis": getattr(result, 'x_axis', 0.5),
                    "y_axis": getattr(result, 'y_axis', 0.5),
                    "z_axis": getattr(result, 'z_axis', 0.0),
                    "labels": getattr(result, 'labels', {}),
                    "cognitive_level": getattr(result, 'cognitive_level', 'moderate'),
                    "execution_mode": getattr(result, 'execution_mode', 'auto'),
                    "prompt_style": getattr(result, 'prompt_style', 'default'),
                }, indent=2, ensure_ascii=False, default=str))
                return
        except Exception as err:
            print(json.dumps({"error": str(err)}, ensure_ascii=False))
            return
    last_pcr = getattr(e, '_last_pcr', None)
    if last_pcr:
        print(json.dumps({
            "zone": getattr(last_pcr, 'zone', getattr(last_pcr, 'expectation', '?')),
            "x_axis": getattr(last_pcr, 'x_axis', None),
            "y_axis": getattr(last_pcr, 'y_axis', None),
            "z_axis": getattr(last_pcr, 'z_axis', None),
            "labels": getattr(last_pcr, 'labels', {}),
            "complexity": getattr(last_pcr, 'complexity_level', 0),
            "mode": getattr(last_pcr, 'execution_mode', '?'),
            "style": getattr(last_pcr, 'prompt_style', '?'),
        }, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"error": "No PCR router available"}, ensure_ascii=False))


# ═══ Intent ═══

def cmd_intent(args):
    """Intent parse/show/history/confidence."""
    sub = getattr(args, 'subcommand', 'parse')
    e = get_engine()

    if sub == 'show':
        last = getattr(e, '_last_intent', None)
        if last:
            info = getattr(last, '__dict__', str(last))
            print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
        else:
            print(json.dumps({"error": "No intent parsed yet", "intent": "unknown"}, ensure_ascii=False))
        return

    if sub == 'history':
        pcr = getattr(e, '_pcr_router', None)
        hist = []
        if pcr and hasattr(pcr, 'history'):
            raw = pcr.history()
            if isinstance(raw, list):
                hist = raw[-10:]
            elif isinstance(raw, dict):
                hist = raw.get('history', [])[-10:]
        print(json.dumps({"history": hist}, indent=2, ensure_ascii=False, default=str))
        return

    if sub == 'confidence':
        last = getattr(e, '_last_intent', None)
        pcr = getattr(e, '_last_pcr', None)
        print(json.dumps({
            "intent_confidence": getattr(last, 'confidence', 0) if last else 0,
            "pcr_zone": getattr(pcr, 'expectation', '?') if pcr else '?',
            "pcr_complexity": getattr(pcr, 'complexity_level', 0) if pcr else 0,
        }, indent=2, ensure_ascii=False))
        return

    # Default: parse
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    import asyncio
    pcr = getattr(e, '_pcr_router', None)
    if pcr and hasattr(pcr, 'process'):
        try:
            result = asyncio.run(pcr.process(text))
            out = getattr(result, '__dict__', str(result)) if result else {}
            print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
            return
        except: pass
    print(json.dumps({"intent": "unknown", "confidence": 0.5, "msg": "Mock mode"}, ensure_ascii=False))


# ═══ Context ═══

def cmd_context(args):
    """Show compiled context from last event."""
    e = get_engine()
    ctx = getattr(e, '_last_context', None)
    if ctx and hasattr(ctx, 'entries') and ctx.entries:
        entries = [{"type": getattr(ent, "type", "?"), "domain": getattr(ent, "domain", "?"),
                     "content": getattr(ent, "content", "")[:100]} for ent in ctx.entries]
        print(json.dumps({"entries": len(entries), "items": entries}, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"entries": 0, "items": [], "msg": "No context compiled yet."}, ensure_ascii=False))


# ═══ Registration ═══

def register_cmds(subparsers):
    # PCR
    p = subparsers.add_parser("pcr", help="PCR routing")
    sp = p.add_subparsers(dest="subcommand")
    pr = sp.add_parser("route", help="Route text through PCR")
    pr.add_argument("text", nargs="+")
    sp.add_parser("config")
    sp.add_parser("history")
    sc = sp.add_parser("set-config"); sc.add_argument("key"); sc.add_argument("value")
    sp.add_parser("reset-config")

    # Intent
    p = subparsers.add_parser("intent", help="Intent parsing")
    sp = p.add_subparsers(dest="subcommand")
    ip = sp.add_parser("parse", help="Parse intent from text")
    ip.add_argument("text", nargs="+")
    sp.add_parser("show")
    sp.add_parser("history")
    sp.add_parser("confidence")

    # Context
    p = subparsers.add_parser("context", help="Context IR")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
