#!/usr/bin/env python3
"""DialogMesh CLI — dm command entry point.

Usage:
  dm engine start [--provider=deepseek] [--key=SK-...] [--model=deepseek-chat]
  dm engine stop
  dm engine status
  dm session new
  dm session list
  dm session use <id>
  dm session info
  dm session history
  dm event send <text> [--sid=<id>]
  dm reply generate [--ctx=<json>]
  dm reply show
  dm reply raw <prompt>
  dm reply model
  dm reply model set <name>
  dm task show [--sid=<id>]
  dm task save <--input=file|stdin>
  dm task confirm [--sid=<id>]
  dm task node add <name> [--deps=<id,id>]
  dm task node edit <id> <key=val>...
  dm task node remove <id>
  dm task edge add <from> <to>
  dm task edge remove <from> <to>
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from core.agent.cli.engine import (
    start_engine, stop_engine, engine_status,
    get_session, set_session,
    get_engine, get_provider, get_chain_status,
    STATE_FILE,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ══════════════════════════════════════════════════════════════════════════════
# Engine commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_engine_start(args):
    result = start_engine(
        provider_type=args.provider,
        api_key=args.key,
        base_url=args.base_url,
        model=args.model,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_engine_stop(args):
    result = stop_engine()
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_engine_status(args):
    result = engine_status()
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_engine_chains(args):
    result = get_chain_status()
    print(json.dumps(result, indent=2, ensure_ascii=False))


# ══════════════════════════════════════════════════════════════════════════════
# Session commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_session_new(args):
    import uuid
    sid = str(uuid.uuid4())[:12]
    set_session(sid)
    print(json.dumps({"session_id": sid}, ensure_ascii=False))


def cmd_session_list(args):
    # Read sessions from the state file and v3_sessions.json
    sessions = []
    state_file = os.path.join(PROJECT_ROOT, "data", "v3_sessions.json")
    if os.path.exists(state_file):
        import json as _json
        with open(state_file, encoding="utf-8") as f:
            data = _json.load(f)
        for sid, s in data.items():
            msgs = s.get("messages", [])
            sessions.append({
                "id": sid[:12],
                "turns": len(msgs),
                "last": msgs[-1].get("content", "")[:60] if msgs else "",
            })
    print(json.dumps(sessions, indent=2, ensure_ascii=False))


def cmd_session_use(args):
    result = set_session(args.id)
    print(json.dumps(result, ensure_ascii=False))


def cmd_session_info(args):
    sid = get_session(args.id if hasattr(args, 'id') and args.id else None)
    state_file = os.path.join(PROJECT_ROOT, "data", "v3_sessions.json")
    info = {"session_id": sid, "turns": 0}
    if os.path.exists(state_file):
        import json as _json
        with open(state_file, encoding="utf-8") as f:
            data = _json.load(f)
        if sid in data:
            s = data[sid]
            info["turns"] = len(s.get("messages", []))
            info["created"] = s.get("created_at", "?")
    print(json.dumps(info, indent=2, ensure_ascii=False))


def cmd_session_history(args):
    sid = get_session(args.id if hasattr(args, 'id') and args.id else None)
    state_file = os.path.join(PROJECT_ROOT, "data", "v3_sessions.json")
    if os.path.exists(state_file):
        import json as _json
        with open(state_file, encoding="utf-8") as f:
            data = _json.load(f)
        if sid in data:
            msgs = data[sid].get("messages", [])
            history = [{"role": m["role"], "content": m["content"]} for m in msgs]
            print(json.dumps(history, indent=2, ensure_ascii=False))
            return
    print(json.dumps([], ensure_ascii=False))


# ══════════════════════════════════════════════════════════════════════════════
# Event send (full pipeline)
# ══════════════════════════════════════════════════════════════════════════════

def cmd_event_send(args):
    engine = get_engine()
    provider = get_provider()
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    sid = get_session(args.sid if hasattr(args, 'sid') else None)

    # Build EventIR and process through engine
    from core.agent.events.event_ir import DialogAdapter
    adapter = DialogAdapter()
    event = adapter.adapt(text, session_id=sid, turn_number=1)

    t0 = __import__("time").time()
    r = None
    try:
        r = engine.on_event(event)
    except Exception as e:
        r = str(e)

    # Extract PCR result
    pcr = getattr(engine, '_last_pcr', None)

    # Call LLM for reply
    try:
        system_prompt = "你是 DialogMesh v6 认知助手。用中文回复，简洁专业。"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        req = type("req", (), {
            "prompt": "",
            "messages": messages,
            "system_prompt": system_prompt,
            "max_tokens": 800,
            "temperature": 0.3,
        })
        from core.agent.llm_providers.base import GenerateRequest
        req2 = GenerateRequest(prompt="", messages=messages, system_prompt=system_prompt, max_tokens=800, temperature=0.3)
        llm_reply = provider.generate(req2)
        reply_text = llm_reply.text if hasattr(llm_reply, 'text') else str(llm_reply)
    except Exception as e:
        reply_text = f"[LLM error: {e}]"
    import json as _json
    import os as _os
    elapsed = (__import__("time").time() - t0) * 1000

    result = {
        "session_id": sid,
        "reply": reply_text,
        "text": text,
        "latency_ms": round(elapsed, 1),
    }
    if pcr:
        result["pcr"] = {
            "zone": getattr(pcr, 'expectation', '?'),
            "complexity": round(getattr(pcr, 'complexity_level', 0), 2),
        }

    # Persist messages to v3_sessions.json
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "data")
        _os.makedirs(data_dir, exist_ok=True)
        sess_path = os.path.join(data_dir, "v3_sessions.json")
        if os.path.exists(sess_path):
            with open(sess_path, encoding="utf-8") as f:
                sessions = _json.load(f)
        else:
            sessions = {}
        if sid not in sessions:
            sessions[sid] = {"created_at": __import__("time").time(), "messages": []}
        sessions[sid]["messages"].append({"role": "user", "content": text})
        sessions[sid]["messages"].append({"role": "assistant", "content": reply_text})
        with open(sess_path, "w", encoding="utf-8") as f:
            _json.dump(sessions, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    print(json.dumps(result, indent=2, ensure_ascii=False))


# ══════════════════════════════════════════════════════════════════════════════
# Reply commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_reply_model(args):
    from core.agent.cli.engine import _state
    model = _state.get("model", "deepseek-chat")
    provider = _state.get("provider", "deepseek")
    print(json.dumps({"model": model, "provider": provider}, ensure_ascii=False))


def cmd_reply_model_set(args):
    from core.agent.cli.engine import _state, _save_state
    _state["model"] = args.name
    _save_state()
    print(json.dumps({"model": args.name, "status": "set"}, ensure_ascii=False))


def cmd_reply_raw(args):
    provider = get_provider()
    prompt = " ".join(args.prompt) if isinstance(args.prompt, list) else args.prompt
    try:
        result = provider.generate(prompt, max_tokens=500, temperature=0.3)
        print(json.dumps({"reply": result}, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))


# ══════════════════════════════════════════════════════════════════════════════
# Task graph commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_task_show(args):
    from core.agent.cli.engine import _state
    import json as _json
    sid = get_session(args.sid if hasattr(args, 'sid') else None)
    tg_path = os.path.join(PROJECT_ROOT, "data", "task_graphs", f"{sid}.json")
    if os.path.exists(tg_path):
        with open(tg_path, encoding="utf-8") as f:
            data = _json.load(f)
    else:
        data = {"nodes": [], "edges": []}
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_task_save(args):
    sid = get_session(args.sid if hasattr(args, 'sid') else None)
    import json as _json
    if args.input == "stdin":
        data = _json.load(sys.stdin)
    else:
        with open(args.input, encoding="utf-8") as f:
            data = _json.load(f)

    tg_dir = os.path.join(PROJECT_ROOT, "data", "task_graphs")
    os.makedirs(tg_dir, exist_ok=True)
    with open(os.path.join(tg_dir, f"{sid}.json"), "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)

    print(json.dumps({"status": "ok", "nodes": len(data.get("nodes", [])),
                       "edges": len(data.get("edges", []))}, ensure_ascii=False))


def cmd_task_confirm(args):
    sid = get_session(args.sid if hasattr(args, 'sid') else None)
    # Mark confirmed so next event sees it
    from core.agent.cli.engine import _state, _save_state
    confirmed = _state.setdefault("confirmed_tasks", [])
    if sid not in confirmed:
        confirmed.append(sid)
    _save_state()
    print(json.dumps({"status": "confirmed", "session_id": sid}, ensure_ascii=False))


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def _dispatch_p3(args):
    """Dispatch P3 commands: behavior, meta, assoc, obs."""
    about = getattr(args, "subcommand", "")
    cmd = args.command
    from core.agent.cli.commands.p3_cmd import (
        cmd_behavior_show, cmd_behavior_predict,
        cmd_meta_show, cmd_meta_review,
        cmd_assoc_show, cmd_assoc_trace,
        cmd_obs_show, cmd_obs_query,
    )
    map = {
        ("behavior","show"): cmd_behavior_show, ("behavior","predict"): cmd_behavior_predict,
        ("meta","show"): cmd_meta_show, ("meta","review"): cmd_meta_review,
        ("assoc","show"): cmd_assoc_show, ("assoc","trace"): cmd_assoc_trace,
        ("obs","show"): cmd_obs_show, ("obs","query"): cmd_obs_query,
    }
    map.get((cmd, about), lambda a: print(f"dm {cmd} <show|...>"))(args)


def _dispatch_p4(args):
    """Dispatch P4 commands: profile, engineering, concepts, mind."""
    about = getattr(args, "subcommand", "")
    cmd = args.command
    from core.agent.cli.commands.p4_cmd import (
        cmd_profile_show, cmd_profile_edit,
        cmd_engineering_show, cmd_concepts_show, cmd_mind_show,
    )
    m = {
        ("profile","show"): cmd_profile_show, ("profile","edit"): cmd_profile_edit,
        ("engineering","show"): cmd_engineering_show,
        ("concepts","show"): cmd_concepts_show,
        ("mind","show"): cmd_mind_show,
    }
    m.get((cmd, about), lambda a: print(f"dm {cmd} <show|...>"))(args)


def _dispatch_p5(args):
    """Dispatch P5 commands: rules, abc, annotations, corrections, feedback, inertia, versions, metrics."""
    about = getattr(args, "subcommand", "")
    cmd = args.command
    from core.agent.cli.commands.p5_cmd import (
        cmd_rules_show, cmd_rules_add, cmd_abc_show,
        cmd_annotations_show, cmd_corrections_show, cmd_feedback_show,
        cmd_inertia_show, cmd_versions_show, cmd_metrics_show,
    )
    m = {
        ("rules","show"): cmd_rules_show, ("rules","add"): cmd_rules_add,
        ("abc","show"): cmd_abc_show,
        ("annotations","show"): cmd_annotations_show,
        ("corrections","show"): cmd_corrections_show,
        ("feedback","show"): cmd_feedback_show,
        ("inertia","show"): cmd_inertia_show,
        ("versions","show"): cmd_versions_show,
        ("metrics","show"): cmd_metrics_show,
    }
    m.get((cmd, about), lambda a: print(f"dm {cmd} <show|...>"))(args)


def _dispatch_app(args):
    """Dispatch app commands: chat, test, ab, monitor, export, data."""
    about = getattr(args, "subcommand", "")
    cmd = args.command
    from core.agent.cli.commands.app_cmd import (
        cmd_chat, cmd_test, cmd_ab, cmd_monitor, cmd_export, cmd_data_show, cmd_data_clean,
    )
    m = {
        ("chat","start"): cmd_chat,
        ("test","run"): cmd_test,
        ("ab","run"): cmd_ab,
        ("monitor","show"): cmd_monitor,
        ("export","all"): cmd_export,
        ("data","show"): cmd_data_show,
        ("data","clean"): cmd_data_clean,
    }
    m.get((cmd, about), lambda a: print(f"dm {cmd} <...>"))(args)


def _dispatch_task_ops(args):
    """Dispatch task node/edge operations."""
    from core.agent.cli.commands.p7_cmd import (
        cmd_task_node_add, cmd_task_node_edit, cmd_task_node_remove,
        cmd_task_edge_add, cmd_task_edge_remove,
    )
    node_op = getattr(args, "node_op", getattr(args, "edge_op", ""))
    cmd = getattr(args, "subcommand", "")
    m = {
        ("node", "add"): cmd_task_node_add, ("node", "edit"): cmd_task_node_edit,
        ("node", "remove"): cmd_task_node_remove,
        ("edge", "add"): cmd_task_edge_add, ("edge", "remove"): cmd_task_edge_remove,
    }
    m.get((cmd, node_op), lambda a: print("dm task node <add|edit|remove> | dm task edge <add|remove>"))(args)


def main():
    parser = argparse.ArgumentParser(description="DialogMesh CLI", prog="dm")
    sub = parser.add_subparsers(dest="command")

    # Engine
    p = sub.add_parser("engine", help="Engine lifecycle")
    p2 = p.add_subparsers(dest="subcommand")
    p_es = p2.add_parser("start", help="Start engine")
    p_es.add_argument("--provider", default="deepseek")
    p_es.add_argument("--key", default="")
    p_es.add_argument("--base-url", default="")
    p_es.add_argument("--model", default="deepseek-chat")
    p2.add_parser("stop", help="Stop engine")
    p2.add_parser("status", help="Engine status")
    p2.add_parser("chains", help="Chain status")

    # Session
    p = sub.add_parser("session", help="Session management")
    p2 = p.add_subparsers(dest="subcommand")
    p2.add_parser("new", help="Create session")
    p2.add_parser("list", help="List sessions")
    p_use = p2.add_parser("use", help="Set current session")
    p_use.add_argument("id")
    p2.add_parser("info", help="Session info")
    p2.add_parser("history", help="Message history")

    # Event
    p = sub.add_parser("event", help="Event operations")
    p2 = p.add_subparsers(dest="subcommand")
    p_ev = p2.add_parser("send", help="Send message through full pipeline")
    p_ev.add_argument("text", nargs="+", help="Message text")
    p_ev.add_argument("--sid", help="Session ID")

    # Reply
    p = sub.add_parser("reply", help="LLM reply operations")
    p2 = p.add_subparsers(dest="subcommand")
    p2.add_parser("model", help="Show current model")
    p_ms = p2.add_parser("set", help="Set model")
    p_ms.add_argument("name")
    p_raw = p2.add_parser("raw", help="Raw LLM call")
    p_raw.add_argument("prompt", nargs="+")

    # ── P2: Discourse, PCR, Intent, Context, Subgraph, Format, Graph ──
    from core.agent.cli.commands import register_all
    register_all(sub)

    # Task
    p = sub.add_parser("task", help="Task graph operations")
    p2 = p.add_subparsers(dest="subcommand")
    p2.add_parser("show", help="Show task graph")
    p_save = p2.add_parser("save", help="Save task graph")
    p_save.add_argument("--input", required=True, help="JSON file or 'stdin'")
    p_save.add_argument("--sid", help="Session ID")
    p2.add_parser("confirm", help="Confirm task graph")
    # Task node/edge subcommands
    tn = p2.add_parser("node", help="Task node operations")
    tn2 = tn.add_subparsers(dest="node_op")
    ta = tn2.add_parser("add"); ta.add_argument("name"); ta.add_argument("--deps", default="")
    te = tn2.add_parser("edit"); te.add_argument("id"); te.add_argument("keyval", nargs="+")
    tr = tn2.add_parser("remove"); tr.add_argument("id")
    te2 = p2.add_parser("edge", help="Task edge operations")
    te2s = te2.add_subparsers(dest="edge_op")
    tae = te2s.add_parser("add"); tae.add_argument("from_"); tae.add_argument("to_")
    tre = te2s.add_parser("remove"); tre.add_argument("from_"); tre.add_argument("to_")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmd_map = {
        ("engine", "start"): cmd_engine_start,
        ("engine", "stop"): cmd_engine_stop,
        ("engine", "status"): cmd_engine_status,
        ("engine", "chains"): cmd_engine_chains,
        ("session", "new"): cmd_session_new,
        ("session", "list"): cmd_session_list,
        ("session", "use"): cmd_session_use,
        ("session", "info"): cmd_session_info,
        ("session", "history"): cmd_session_history,
        ("event", "send"): cmd_event_send,
        ("reply", "model"): cmd_reply_model,
        ("reply", "set"): cmd_reply_model_set,
        ("reply", "raw"): cmd_reply_raw,
        ("task", "show"): cmd_task_show,
        ("task", "save"): cmd_task_save,
        ("task", "confirm"): cmd_task_confirm,
    }
    fn = cmd_map.get((args.command, getattr(args, "subcommand", None)))
    if fn:
        fn(args)
    elif args.command == "discourse":
        about = getattr(args, "subcommand", "")
        from core.agent.cli.commands.discourse_cmd import cmd_show as d1, cmd_tree as d2, cmd_block as d3, cmd_feed as d4, cmd_search as d5
        {"show": d1, "tree": d2, "block": d3, "feed": d4, "search": d5}.get(about, lambda a: print("Usage: dm discourse <show|tree|block|feed|search>"))(args)
    elif args.command == "pcr":
        from core.agent.cli.commands.pcr_intent_cmd import cmd_pcr
        cmd_pcr(args)
    elif args.command == "intent":
        from core.agent.cli.commands.pcr_intent_cmd import cmd_intent
        cmd_intent(args)
    elif args.command == "context":
        from core.agent.cli.commands.pcr_intent_cmd import cmd_context
        cmd_context(args)
    elif args.command == "blueprint":
        about = getattr(args, "subcommand", "")
        from core.agent.cli.commands.blueprint_cmd import cmd_blueprint_show as bs, cmd_blueprint_build as bb
        {"show": bs, "build": bb}.get(about, lambda a: print("dm blueprint <show|build>"))(args)
    elif args.command == "decider":
        about = getattr(args, "subcommand", "")
        from core.agent.cli.commands.blueprint_cmd import cmd_decider_show as ds, cmd_decider_chains as dc, cmd_decider_execute as dx
        {"show": ds, "chains": dc, "execute": dx}.get(about, lambda a: print("dm decider <show|chains|execute>"))(args)
    elif args.command == "subgraph":
        about = getattr(args, "subcommand", "")
        from core.agent.cli.commands.subgraph_cmd import cmd_subgraph_show as sg1, cmd_subgraph_expand as sg2
        {"show": sg1, "expand": sg2}.get(about, lambda a: print("dm subgraph <show|expand>"))(args)
    elif args.command in ("behavior", "meta", "assoc", "obs"):
        _dispatch_p3(args)
    elif args.command in ("profile", "engineering", "concepts", "mind"):
        _dispatch_p4(args)
    elif args.command in ("rules", "abc", "annotations", "corrections", "feedback", "inertia", "versions", "metrics"):
        _dispatch_p5(args)
    elif args.command in ("chat", "test", "ab", "monitor", "export", "data"):
        _dispatch_app(args)
    elif args.command == "task" and getattr(args, "subcommand", "") in ("node", "edge"):
        _dispatch_task_ops(args)
    else:
        if args.command == "reply" and args.subcommand is None:
            cmd_reply_model(args)
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
