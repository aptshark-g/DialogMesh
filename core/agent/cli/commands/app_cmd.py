"""App-layer CLI commands: chat, test, ab, monitor, export, data management."""
import json, os, sys
from core.agent.cli.engine import get_engine, get_session, get_provider, PROJECT_ROOT


def cmd_chat(args):
    """Interactive chat loop (simple)."""
    e = get_engine()
    p = get_provider()
    sid = get_session()
    print(f"DialogMesh v6 CLI Chat (session: {sid})")
    print("Type /quit to exit, /task to see task graph.\n")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text or text == "/quit":
            break
        if text == "/task":
            tg_path = os.path.join(PROJECT_ROOT, "data", "task_graphs", f"{sid}.json")
            if os.path.exists(tg_path):
                with open(tg_path, encoding="utf-8") as f:
                    print(json.dumps(json.load(f), indent=2, ensure_ascii=False))
            else:
                print("(no task graph)")
            continue
        # Process through engine + LLM
        from core.agent.events.event_ir import DialogAdapter
        adapter = DialogAdapter()
        event = adapter.adapt(text, session_id=sid, turn_number=1)
        e.on_event(event)
        from core.agent.llm_providers.base import GenerateRequest
        req = GenerateRequest(prompt="", messages=[{"role": "system", "content": "你是DialogMesh助手"}, {"role": "user", "content": text}], system_prompt="你是DialogMesh助手", max_tokens=800, temperature=0.3)
        result = p.generate(req)
        reply = result.text if hasattr(result, 'text') else str(result)
        print(f"\n{reply}\n")


def cmd_test(args):
    """Run a simple benchmark."""
    print(json.dumps({"msg": "test — run 'dm engine status' for subsystem health check"}, ensure_ascii=False))


def cmd_ab(args):
    """A/B comparison placeholder."""
    sid = get_session()
    print(json.dumps({"msg": "ab — use 'dm event send <msg>' to collect data for comparison", "session": sid}, ensure_ascii=False))


def cmd_monitor(args):
    """Show monitoring logs."""
    e = get_engine()
    el = getattr(e, '_event_log', None)
    if el and hasattr(el, 'tail'):
        entries = el.tail(10)
        print(json.dumps({"log": entries}, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps({"msg": "EventLog not available"}, ensure_ascii=False))


def cmd_export(args):
    """Export session data."""
    sid = get_session()
    export = {"session_id": sid}
    # Messages
    sess_path = os.path.join(PROJECT_ROOT, "data", "v3_sessions.json")
    if os.path.exists(sess_path):
        with open(sess_path, encoding="utf-8") as f:
            sessions = json.load(f)
        if sid in sessions:
            export["messages"] = sessions[sid].get("messages", [])
    # Task graph
    tg_path = os.path.join(PROJECT_ROOT, "data", "task_graphs", f"{sid}.json")
    if os.path.exists(tg_path):
        with open(tg_path, encoding="utf-8") as f:
            export["task_graph"] = json.load(f)
    print(json.dumps(export, indent=2, ensure_ascii=False))


def cmd_data_show(args):
    """Show data directory sizes."""
    import os as _os
    data_dir = os.path.join(PROJECT_ROOT, "data")
    info = {}
    if _os.path.exists(data_dir):
        for item in os.listdir(data_dir):
            p = os.path.join(data_dir, item)
            if _os.path.isfile(p):
                info[item] = _os.path.getsize(p)
            elif _os.path.isdir(p):
                count = len(os.listdir(p))
                size = sum(_os.path.getsize(os.path.join(p, f)) for f in os.listdir(p) if _os.path.isfile(os.path.join(p, f)))
                info[f"{item}/"] = f"{count} files, {size}b"
    print(json.dumps(info, indent=2, ensure_ascii=False))


def cmd_data_clean(args):
    """Clean data directory."""
    import shutil
    data_dir = os.path.join(PROJECT_ROOT, "data")
    if args.module == "all":
        for item in ["v3_sessions.json", "task_graphs", "session_events"]:
            p = os.path.join(data_dir, item)
            if os.path.isfile(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p)
        print(json.dumps({"status": "cleaned all"}, ensure_ascii=False))
    elif args.module == "task-graphs":
        tg = os.path.join(data_dir, "task_graphs")
        if os.path.isdir(tg):
            shutil.rmtree(tg)
            os.makedirs(tg)
        print(json.dumps({"status": "cleaned task_graphs"}, ensure_ascii=False))


def register_cmds(subparsers):
    p = subparsers.add_parser("chat", help="Interactive chat (Ctrl+D to quit)")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("start")

    p = subparsers.add_parser("test", help="Run benchmarks")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("run")

    p = subparsers.add_parser("ab", help="A/B comparison")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("run")

    p = subparsers.add_parser("monitor", help="Monitoring view")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")

    p = subparsers.add_parser("export", help="Export session data")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("all")

    p = subparsers.add_parser("data", help="Data management")
    sp = p.add_subparsers(dest="subcommand")
    sp.add_parser("show")
    c = sp.add_parser("clean")
    c.add_argument("module", help="all | task-graphs")
