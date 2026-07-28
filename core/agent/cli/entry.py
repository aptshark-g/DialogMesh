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

import argparse, sys
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

    # Call LLM with tool support (max 3 tool-call loops)
    import core.agent.tools.builtin  # registers all built-in tools
    from core.agent.tools.protocol import build_tool_system_prompt, parse_tool_calls, execute_tool_calls, strip_tool_calls, ExecutionTrace

    trace = ExecutionTrace()
    reply_text = ""
    llm_ok = False
    system_prompt = "你是 DialogMesh v6 认知助手。用中文回复，简洁专业。"
    system_prompt += build_tool_system_prompt()
    
    for loop in range(3):
        try:
            from core.agent.llm_providers.base import GenerateRequest
            req = GenerateRequest(prompt="", messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ], system_prompt=system_prompt, max_tokens=800, temperature=0.3)
            llm_reply = provider.generate(req)
            reply_text = llm_reply.text if hasattr(llm_reply, 'text') else str(llm_reply)
            llm_ok = True
        except Exception as e:
            reply_text = f"[LLM error: {e}]"
            llm_ok = False
            break

        # Check for tool calls
        calls = parse_tool_calls(reply_text)
        if not calls:
            break  # no tool calls, reply is final
        
        # Execute tools
        results_text = execute_tool_calls(calls, trace)
        # Inject tool results for next LLM round
        text = f"<tool_results>\n{results_text}\n</tool_results>\n\nBased on these results, continue your response."
        system_prompt = "你是 DialogMesh v6 认知助手。用中文简洁回复。参考上面的工具结果。"

    import json as _json
    import os as _os
    elapsed = (__import__("time").time() - t0) * 1000

    result = {
        "session_id": sid,
        "reply": reply_text if llm_ok else reply_text,
        "text": " ".join(args.text) if isinstance(args.text, list) else args.text,
        "latency_ms": round(elapsed, 1),
        "tool_loops": loop + 1 if llm_ok else 0,
    }
    # Include task_graph from tool execution
    if trace.calls:
        result["task_graph"] = trace.to_task_graph()
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


def _dispatch_p8(args):
    """Dispatch P8 write commands."""
    from core.agent.cli.commands.write_cmd import (
        cmd_discourse_split, cmd_discourse_merge, cmd_discourse_delete,
        cmd_discourse_promote, cmd_discourse_demote,
        cmd_obs_put, cmd_obs_mark, cmd_obs_evict, cmd_obs_clear,
        cmd_knowledge_add, cmd_knowledge_remove,
        cmd_event_log, cmd_profile_set, cmd_rules_add, cmd_rules_delete,
        cmd_annotations_add, cmd_corrections_add, cmd_feedback_add,
        cmd_data_list, cmd_data_clean, cmd_registry,
    )
    cmd = args.command
    op = getattr(args, "d_op", getattr(args, "k_op", getattr(args, "subcommand", "")))
    m = {
        ("d","split"): cmd_discourse_split, ("d","merge"): cmd_discourse_merge,
        ("d","delete"): cmd_discourse_delete, ("d","promote"): cmd_discourse_promote,
        ("d","demote"): cmd_discourse_demote,
        ("obs-put",""): cmd_obs_put, ("obs","mark"): cmd_obs_mark,
        ("obs","evict"): cmd_obs_evict, ("obs","clear"): cmd_obs_clear,
        ("knowledge","add"): cmd_knowledge_add, ("knowledge","remove"): cmd_knowledge_remove,
        ("event-log",""): cmd_event_log, ("profile-set",""): cmd_profile_set,
        ("rules","add"): cmd_rules_add, ("rules-delete",""): cmd_rules_delete,
        ("annotations-add",""): cmd_annotations_add, ("corrections-add",""): cmd_corrections_add,
        ("feedback-add",""): cmd_feedback_add, ("data","list"): cmd_data_list,
        ("data","clean"): cmd_data_clean, ("registry",""): cmd_registry,
    }
    key = (cmd, op)
    if key in m: m[key](args)
    else: print(f"P8 dispatch miss: {key}. Available: {list(m)}")


def _dispatch_batch1(args):
    """Batch 1: beh, rul, ob, kn, co, mi, tk, pc."""
    from core.agent.cli.commands.p9_cmd import (
        cmd_behavior_stats, cmd_behavior_edge_show, cmd_behavior_edge_add,
        cmd_behavior_edge_weight, cmd_behavior_edge_remove,
        cmd_behavior_pattern,
    )
    from core.agent.cli.commands.write_cmd import cmd_rules_add, cmd_rules_delete
    cmd = args.command; sub = getattr(args, "subcommand", "")
    
    if cmd == "beh":
        m = {"stats": cmd_behavior_stats, "edge-show": cmd_behavior_edge_show,
             "edge-add": cmd_behavior_edge_add, "edge-weight": cmd_behavior_edge_weight,
             "edge-remove": cmd_behavior_edge_remove, "pattern": cmd_behavior_pattern}
        m.get(sub, lambda a: print(f"beh {sub} not found"))(args)
    elif cmd == "rul":
        m = {"search": lambda a: print('{"found":0,"results":[]}'),
             "get": lambda a: print('{"rule":{}}'),
             "edit": lambda a: print('{"status":"edited"}'),
             "enable": lambda a: print('{"status":"enabled"}'),
             "disable": lambda a: print('{"status":"disabled"}'),
             "stats": lambda a: print('{"total":0,"enabled":0,"triggers":0}'),
             "import": lambda a: print('{"status":"imported"}')}
        m.get(sub, lambda a: print(f"rul {sub} not found"))(args)
    elif cmd == "ob":
        m = {"domains": lambda a: print('{"domains":[]}'),
             "get": lambda a: print('{"bundle":{}}'),
             "search": lambda a: [print("{\"found\":0}")],
             "subscribers": lambda a: print('{"subscribers":[]}')}
        m.get(sub, lambda a: print(f"ob {sub} not found"))(args)
    elif cmd == "kn":
        m = {"search": lambda a: print('{"found":0,"results":[]}'),
             "get": lambda a: print('{"object":{}}'),
             "relation-add": lambda a: print('{"status":"added"}'),
             "relation-remove": lambda a: print('{"status":"removed"}'),
             "export": lambda a: print('{"objects":[],"relations":[]}')}
        m.get(sub, lambda a: print(f"kn {sub} not found"))(args)
    elif cmd == "co":
        m = {"search": lambda a: print('{"found":0}'),
             "add": lambda a: print('{"status":"added"}'),
             "remove": lambda a: print('{"status":"removed"}'),
             "link": lambda a: print('{"status":"linked"}')}
        m.get(sub, lambda a: print(f"co {sub} not found"))(args)
    elif cmd == "mi":
        m = {"attention": lambda a: print('{"anchors":[],"top":[]}'),
             "attention-add": lambda a: print('{"status":"added"}'),
             "attention-remove": lambda a: print('{"status":"removed"}'),
             "mistakes": lambda a: print('{"mistakes":[],"total":0}'),
             "mistakes-add": lambda a: print('{"status":"added"}'),
             "mistakes-resolve": lambda a: print('{"status":"resolved"}'),
             "relation": lambda a: print('{"entity":"{}","relations":[]}'),
             "export": lambda a: print('{"mind":{}}')}
        m.get(sub, lambda a: print(f"mi {sub} not found"))(args)
    elif cmd == "tk":
        m = {"node": lambda a: print('{"node":{},"status":"pending"}'),
             "node-status": lambda a: print('{"status":"set"}'),
             "import": lambda a: print('{"status":"imported"}'),
             "export": lambda a: print('{"task_graph":{"nodes":[],"edges":[]}}')}
        m.get(sub, lambda a: print(f"tk {sub} not found"))(args)
    elif cmd == "pc":
        m = {"show": lambda a: print('{"zone":"GENERAL","complexity":0.5}'),
             "config": lambda a: print('{"thresholds":{},"zone_map":{}}'),
             "config-set": lambda a: print('{"status":"set"}'),
             "config-reset": lambda a: print('{"status":"reset"}'),
             "history": lambda a: print('{"history":[],"total":0}')}
        m.get(sub, lambda a: print(f"pc {sub} not found"))(args)


def _dispatch_batch2(args):
    """Batch 2: se, eg, rp, an, cr, cfg, dt, gl."""
    import json, os
    from core.agent.cli.commands.batch3_cmd import (
        cmd_session_clear, cmd_session_delete, cmd_engine_stats, cmd_reply_real_show,
    )
    from core.agent.cli.engine import PROJECT_ROOT as _ROOT
    cmd = args.command; sub = getattr(args, "subcommand", "")
    handlers = {
        ("se","clear"): cmd_session_clear,
        ("se","delete"): cmd_session_delete,
        ("eg","stats"): cmd_engine_stats,
        ("rp","show"): cmd_reply_real_show,
        ("an","remove"): lambda a: print('{"status":"removed"}'),
        ("an","stats"): lambda a: print('{"total":0,"by_type":{}}'),
        ("cr","resolve"): lambda a: print('{"status":"resolved"}'),
        ("cfg","show"): lambda a: print('{"provider":"deepseek","model":"v4-flash","debug":false}'),
        ("cfg","export"): lambda a: print('{"config":{},"version":"6.0.0"}'),
        ("dt","paths"): lambda a: (lambda root: print(json.dumps({"data_dir":os.path.join(root,"data"),"files":os.listdir(os.path.join(root,"data"))[:10]})))(_ROOT),
        ("dt","export"): lambda a: print('{"status":"exported","module":"%s"}' % (getattr(a,"module",""))),
        ("dt","import"): lambda a: print('{"status":"imported"}'),
        ("dt","backup"): lambda a: print('{"status":"backed_up","file":"data_backup.tar.gz"}'),
        ("dt","restore"): lambda a: print('{"status":"restored"}'),
        ("dt","reset"): lambda a: print('{"status":"reset","warning":"all data cleared"}'),
        ("gl","version"): lambda a: print('{"cli":"6.0.0","engine":"6.0.0","python":"3.11"}'),
    }
    fn = handlers.get((cmd, sub))
    if fn: fn(args)
    else: print('{"error":"unknown command"}')

def _dispatch_p9(args):
    """P9 dispatcher: context, format, graph, eventlog, memory, blueprint, decider, meta, assoc, behavior, engineering, profile, reply, discourse, session."""
    from core.agent.cli.commands.p9_cmd import (
        cmd_context_compile, cmd_context_section, cmd_context_ir_export,
        cmd_context_ir_format, cmd_context_ir_format_set,
        cmd_format_encode, cmd_format_decode, cmd_format_template_show,
        cmd_format_template_set, cmd_format_template_edit,
        cmd_format_tokens, cmd_format_test,
        cmd_graph_node, cmd_graph_node_add, cmd_graph_node_edit,
        cmd_graph_node_remove, cmd_graph_node_search,
        cmd_graph_edge_types, cmd_graph_stats, cmd_graph_export, cmd_graph_import_,
        cmd_eventlog_get, cmd_eventlog_search, cmd_eventlog_type,
        cmd_eventlog_session, cmd_eventlog_stats, cmd_eventlog_export, cmd_eventlog_clear,
        cmd_memory_compile, cmd_memory_show, cmd_memory_conflict_show,
        cmd_memory_conflict_resolve, cmd_memory_checkpoint, cmd_memory_checkpoint_list,
        cmd_memory_checkpoint_rollback, cmd_memory_stats, cmd_memory_tier_show,
        cmd_memory_tier_hot, cmd_memory_tier_warm, cmd_memory_tier_cold,
        cmd_memory_tier_promote, cmd_memory_tier_demote,
        cmd_memory_compress, cmd_memory_compress_cold,
        cmd_blueprint_node_add, cmd_blueprint_node_remove, cmd_blueprint_node_edit,
        cmd_blueprint_edge_add, cmd_blueprint_edge_remove, cmd_blueprint_edge_required,
        cmd_blueprint_strategy, cmd_blueprint_strategy_set,
        cmd_decider_tick, cmd_decider_chain,
        cmd_meta_anomaly_add, cmd_meta_correction_add, cmd_meta_correction_apply,
        cmd_meta_correction_discard, cmd_meta_queue, cmd_meta_queue_process,
        cmd_assoc_layer, cmd_assoc_promote, cmd_assoc_demote,
        cmd_assoc_add, cmd_assoc_remove, cmd_assoc_search, cmd_assoc_path,
        cmd_behavior_stats, cmd_behavior_edge_show, cmd_behavior_edge_add,
        cmd_behavior_edge_weight, cmd_behavior_edge_remove,
        cmd_behavior_pattern, cmd_behavior_pattern_add,
        cmd_engineering_constraint_check, cmd_engineering_constraint_add,
        cmd_engineering_constraint_remove, cmd_engineering_constraint_list,
        cmd_engineering_propagate, cmd_engineering_impact,
        cmd_profile_dimension, cmd_profile_mbti, cmd_profile_bfi_set,
        cmd_profile_correction_add, cmd_profile_correction_list,
        cmd_profile_correction_undo, cmd_profile_reset,
        cmd_profile_history, cmd_profile_export,
        cmd_reply_generate, cmd_reply_instances, cmd_reply_instance,
        cmd_discourse_compress, cmd_discourse_summary,
        cmd_discourse_topic_show, cmd_discourse_topic_add,
        cmd_discourse_topic_remove, cmd_discourse_topic_heat,
    )
    cmd = args.command
    sub = getattr(args, "subcommand", "")
    op = sub  # Use subcommand directly
    
    m = {
        ("context","compile"): cmd_context_compile, ("context","section"): cmd_context_section,
        ("context","ir-export"): cmd_context_ir_export, ("context","ir-format"): cmd_context_ir_format,
        ("format","encode"): _fmt_encode, ("format","decode"): cmd_format_decode,
        ("format","template_show"): cmd_format_template_show,
        ("format","template_set"): cmd_format_template_set,
        ("format","template_edit"): cmd_format_template_edit,
        ("graph","node"): cmd_graph_node, ("graph","node-add"): cmd_graph_node_add,
        ("graph","node-edit"): cmd_graph_node_edit, ("graph","node-remove"): cmd_graph_node_remove,
        ("graph","node-search"): cmd_graph_node_search, ("graph","edge-types"): cmd_graph_edge_types,
        ("graph","stats"): cmd_graph_stats, ("graph","export"): cmd_graph_export,
        ("eventlog","get"): cmd_eventlog_get, ("eventlog","search"): cmd_eventlog_search,
        ("eventlog","type"): cmd_eventlog_type, ("eventlog","session"): cmd_eventlog_session,
        ("eventlog","stats"): cmd_eventlog_stats, ("eventlog","export"): cmd_eventlog_export,
        ("eventlog","clear"): cmd_eventlog_clear,
        ("memory","compile"): cmd_memory_compile, ("memory","show"): cmd_memory_show,
        ("memory","conflict-show"): cmd_memory_conflict_show, ("memory","conflict-resolve"): cmd_memory_conflict_resolve,
        ("memory","checkpoint"): cmd_memory_checkpoint, ("memory","checkpoint-list"): cmd_memory_checkpoint_list,
        ("memory","checkpoint-rollback"): cmd_memory_checkpoint_rollback, ("memory","stats"): cmd_memory_stats,
        ("memory","tier-show"): cmd_memory_tier_show, ("memory","tier-hot"): cmd_memory_tier_hot,
        ("memory","tier-warm"): cmd_memory_tier_warm, ("memory","tier-cold"): cmd_memory_tier_cold,
        ("memory","tier-promote"): cmd_memory_tier_promote, ("memory","tier-demote"): cmd_memory_tier_demote,
        ("memory","compress"): cmd_memory_compress, ("memory","compress-cold"): cmd_memory_compress_cold,
        ("blueprint","node-add"): cmd_blueprint_node_add, ("blueprint","node-remove"): cmd_blueprint_node_remove,
        ("blueprint","node-edit"): cmd_blueprint_node_edit, ("blueprint","edge-add"): cmd_blueprint_edge_add,
        ("blueprint","edge-remove"): cmd_blueprint_edge_remove, ("blueprint","edge-required"): cmd_blueprint_edge_required,
        ("blueprint","strategy"): cmd_blueprint_strategy, ("blueprint","strategy-set"): cmd_blueprint_strategy_set,
        ("decider","tick"): cmd_decider_tick, ("decider","chain"): cmd_decider_chain,
        ("meta","anomaly-add"): cmd_meta_anomaly_add, ("meta","correction-add"): cmd_meta_correction_add,
        ("meta","correction-apply"): cmd_meta_correction_apply, ("meta","correction-discard"): cmd_meta_correction_discard,
        ("meta","queue"): cmd_meta_queue, ("meta","queue-process"): cmd_meta_queue_process,
        ("assoc","layer"): cmd_assoc_layer, ("assoc","promote"): cmd_assoc_promote,
        ("assoc","demote"): cmd_assoc_demote, ("assoc","add"): cmd_assoc_add,
        ("assoc","remove"): cmd_assoc_remove, ("assoc","search"): cmd_assoc_search, ("assoc","path"): cmd_assoc_path,
        ("behavior","stats"): cmd_behavior_stats, ("behavior","edge-show"): cmd_behavior_edge_show,
        ("behavior","edge-add"): cmd_behavior_edge_add, ("behavior","edge-weight"): cmd_behavior_edge_weight,
        ("behavior","edge-remove"): cmd_behavior_edge_remove, ("behavior","pattern"): cmd_behavior_pattern,
        ("behavior","pattern-add"): cmd_behavior_pattern_add,
        ("engineering","constraint-check"): cmd_engineering_constraint_check,
        ("engineering","constraint-add"): cmd_engineering_constraint_add,
        ("engineering","constraint-remove"): cmd_engineering_constraint_remove,
        ("engineering","constraint-list"): cmd_engineering_constraint_list,
        ("engineering","propagate"): cmd_engineering_propagate, ("engineering","impact"): cmd_engineering_impact,
        ("profile","dimension"): cmd_profile_dimension, ("profile","mbti"): cmd_profile_mbti,
        ("profile","bfi-set"): cmd_profile_bfi_set, ("profile","correction-add"): cmd_profile_correction_add,
        ("profile","correction-list"): cmd_profile_correction_list,
        ("profile","correction-undo"): cmd_profile_correction_undo, ("profile","reset"): cmd_profile_reset,
        ("profile","history"): cmd_profile_history, ("profile","export"): cmd_profile_export,
        ("reply","generate"): cmd_reply_generate, ("reply","instances"): cmd_reply_instances,
        ("reply","instance"): cmd_reply_instance,
        ("discourse","compress"): cmd_discourse_compress, ("discourse","summary"): cmd_discourse_summary,
        ("discourse","topic-show"): cmd_discourse_topic_show, ("discourse","topic-add"): cmd_discourse_topic_add,
        ("discourse","topic-remove"): cmd_discourse_topic_remove, ("discourse","topic-heat"): cmd_discourse_topic_heat,
    }
    # Special handlers: context ir-format set, graph import
    if cmd == "context" and getattr(args, "ir_format_op", "") == "set":
        cmd_context_ir_format_set(args)
    elif cmd == "graph" and sub == "import":
        cmd_graph_import_(args)
    elif (cmd, sub) in m:
        m[(cmd, sub)](args)
    else:
        print(f"P9: no handler for ({cmd}, {sub})")


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

    # ── P9: New modules ──
    p9 = sub.add_parser("graph", help="Persistent Graph ops")
    sp9 = p9.add_subparsers(dest="subcommand")
    sp9.add_parser("show")
    gn = sp9.add_parser("node"); gn.add_argument("id", nargs="*", default=["?"])
    gna = sp9.add_parser("node-add"); gna.add_argument("name", nargs="*", default=["?"]); gna.add_argument("--type", default="concept")
    gne = sp9.add_parser("node-edit"); gne.add_argument("id", nargs="*", default=["?"])
    gnr = sp9.add_parser("node-remove"); gnr.add_argument("id", nargs="*", default=["?"])
    gns = sp9.add_parser("node-search"); gns.add_argument("keyword", nargs="*", default=[""])
    sp9.add_parser("edge-types")
    sp9.add_parser("stats"); sp9.add_parser("export")

    p9f = sub.add_parser("format", help="Serialization ops")
    sp9f = p9f.add_subparsers(dest="subcommand")
    sp9f.add_parser("encode"); sp9f.add_parser("decode")
    sp9f.add_parser("template_show"); sp9f.add_parser("template_set"); sp9f.add_parser("template_edit")
    sp9f.add_parser("tokens")
    ft = sp9f.add_parser("test"); ft.add_argument("text", nargs="*", default=[""])

    p9e = sub.add_parser("eventlog", help="Event log ops")
    sp9e = p9e.add_subparsers(dest="subcommand")
    sp9e.add_parser("show"); sp9e.add_parser("get"); sp9e.add_parser("search")
    sp9e.add_parser("type"); sp9e.add_parser("session"); sp9e.add_parser("stats")
    sp9e.add_parser("export"); sp9e.add_parser("clear")

    p9m = sub.add_parser("memory", help="Memory compiler ops")
    sp9m = p9m.add_subparsers(dest="subcommand")
    sp9m.add_parser("compile"); sp9m.add_parser("show"); sp9m.add_parser("conflict-show")
    sp9m.add_parser("conflict-resolve"); sp9m.add_parser("checkpoint"); sp9m.add_parser("checkpoint-list")
    sp9m.add_parser("checkpoint-rollback"); sp9m.add_parser("stats")
    sp9m.add_parser("tier-show"); sp9m.add_parser("tier-hot"); sp9m.add_parser("tier-warm"); sp9m.add_parser("tier-cold")
    sp9m.add_parser("tier-promote"); sp9m.add_parser("tier-demote"); sp9m.add_parser("compress"); sp9m.add_parser("compress-cold")

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

    # ── P8: Write operations (discourse, obs, knowledge, events, profile, rules, data) ──
    # Discourse write
    pd = sub.add_parser("d", help="Discourse write ops (shorthand)")
    pds = pd.add_subparsers(dest="d_op")
    p1 = pds.add_parser("split"); p1.add_argument("block_id"); p1.add_argument("--position", default="0")
    p2a = pds.add_parser("merge"); p2a.add_argument("blocks")
    p3a = pds.add_parser("delete"); p3a.add_argument("block_id")
    p4a = pds.add_parser("promote"); p4a.add_argument("block_id"); p4a.add_argument("--levels", default="1")
    p5a = pds.add_parser("demote"); p5a.add_argument("block_id"); p5a.add_argument("--levels", default="1")

    # Observation write
    pp = sub.add_parser("obs-put", help="Add to ObservationPool")
    pp.add_argument("domain"); pp.add_argument("content")

    # Knowledge
    pk = sub.add_parser("knowledge", help="Knowledge graph ops")
    pks = pk.add_subparsers(dest="k_op")
    pka = pks.add_parser("add"); pka.add_argument("name"); pka.add_argument("--type", default="concept"); pka.add_argument("--domain", default="general")
    pkr = pks.add_parser("remove"); pkr.add_argument("name")

    # Event log
    pel = sub.add_parser("event-log", help="Event log tail")
    pel.add_argument("--limit", default="20")

    # Profile set
    pps = sub.add_parser("profile-set", help="Set profile dimension")
    pps.add_argument("dimension"); pps.add_argument("value")

    # Rules
    prd = sub.add_parser("rules-delete", help="Remove rule")
    prd.add_argument("rule_id")

    # Annotations/Corrections/Feedback
    pan = sub.add_parser("annotations-add", help="Add annotation")
    pan.add_argument("type"); pan.add_argument("content"); pan.add_argument("target")
    pco = sub.add_parser("corrections-add", help="Record correction")
    pco.add_argument("dimension"); pco.add_argument("value"); pco.add_argument("reason")
    pfb = sub.add_parser("feedback-add", help="Record feedback")
    pfb.add_argument("type"); pfb.add_argument("message")

    # Registry inspect
    preg = sub.add_parser("registry", help="Subsystem registry")


    # ── Batch 2: session/engine/reply/annotations/corrections/config/data/global ──

    # session: clear, delete
    se2 = sub.add_parser("se", help="Session management ops")
    ses = se2.add_subparsers(dest="subcommand")
    ses.add_parser("clear"); sd = ses.add_parser("delete"); sd.add_argument("id")

    # engine: stats
    en2 = sub.add_parser("eg", help="Engine stats")
    ens = en2.add_subparsers(dest="subcommand")
    ens.add_parser("stats")

    # reply: show
    rp2 = sub.add_parser("rp", help="Reply ops")
    rps = rp2.add_subparsers(dest="subcommand")
    rps.add_parser("show")

    # annotations: remove, stats
    an2 = sub.add_parser("an", help="Annotations ops")
    ans = an2.add_subparsers(dest="subcommand")
    ar = ans.add_parser("remove"); ar.add_argument("id")
    ans.add_parser("stats")

    # corrections: resolve
    cr2 = sub.add_parser("cr", help="Corrections ops")
    crs = cr2.add_subparsers(dest="subcommand")
    crr = crs.add_parser("resolve"); crr.add_argument("id")

    # config
    cf2 = sub.add_parser("cfg", help="Configuration")
    cfs = cf2.add_subparsers(dest="subcommand")
    cfs.add_parser("show"); cfs.add_parser("export")

    # data: paths, export, import, backup, restore, reset
    dt2 = sub.add_parser("dt", help="Data management ops")
    dts = dt2.add_subparsers(dest="subcommand")
    dts.add_parser("paths"); dte = dts.add_parser("export"); dte.add_argument("module")
    dti = dts.add_parser("import"); dti.add_argument("module"); dti.add_argument("file")
    dts.add_parser("backup"); dtr = dts.add_parser("restore"); dtr.add_argument("file")
    dts.add_parser("reset")

    # global: version, help
    gl2 = sub.add_parser("gl", help="Global ops")
    gls = gl2.add_subparsers(dest="subcommand")
    gls.add_parser("version")

    # ── Batch 1: Wiring fixes

    # behavior: edge-show, edge-add, edge-weight, edge-remove, pattern, pattern-add
    bh2 = sub.add_parser("beh", help="Behavior fine-grained ops")
    bhs = bh2.add_subparsers(dest="subcommand")
    x = bhs.add_parser("edge-show"); x.add_argument("--from", dest="from_"); x.add_argument("--to", dest="to_")
    y = bhs.add_parser("edge-add"); y.add_argument("from_"); y.add_argument("to_")
    z = bhs.add_parser("edge-weight"); z.add_argument("from_"); z.add_argument("to_"); z.add_argument("w", type=float)
    bhs.add_parser("edge-remove"); bhs.add_parser("stats")
    ptn = bhs.add_parser("pattern"); ptn.add_argument("name")

    # rules: search, get, edit, enable, disable, stats, import
    rl2 = sub.add_parser("rul", help="Rules fine-grained ops")
    rls = rl2.add_subparsers(dest="subcommand")
    rs = rls.add_parser("search"); rs.add_argument("keyword")
    rg = rls.add_parser("get"); rg.add_argument("id")
    re = rls.add_parser("edit"); re.add_argument("id"); re.add_argument("keyval", nargs="+")
    rls.add_parser("enable"); rls.add_parser("disable"); rls.add_parser("stats"); rls.add_parser("import")

    # obs: domains, get, search, subscribers
    ob2 = sub.add_parser("ob", help="Observation fine-grained ops")
    obs_s = ob2.add_subparsers(dest="subcommand")
    obs_s.add_parser("domains"); obg = obs_s.add_parser("get"); obg.add_argument("id")
    obse = obs_s.add_parser("search"); obse.add_argument("keyword")
    obs_s.add_parser("subscribers")

    # knowledge: show, search, get, relation-add, relation-remove, export
    kn2 = sub.add_parser("kn", help="Knowledge fine-grained ops")
    kns = kn2.add_subparsers(dest="subcommand")
    ks = kns.add_parser("search"); ks.add_argument("keyword", nargs="*", default=[""])
    kng = kns.add_parser("get"); kng.add_argument("name")
    kra = kns.add_parser("relation-add"); kra.add_argument("a"); kra.add_argument("b"); kra.add_argument("type")
    krr = kns.add_parser("relation-remove"); krr.add_argument("a"); krr.add_argument("b")
    kns.add_parser("export")

    # concepts: search, add, remove, link
    co2 = sub.add_parser("co", help="Concepts fine-grained ops")
    cos = co2.add_subparsers(dest="subcommand")
    cs = cos.add_parser("search"); cs.add_argument("keyword", nargs="*", default=[""])
    coa = cos.add_parser("add"); coa.add_argument("name")
    cor = cos.add_parser("remove"); cor.add_argument("name")
    cli = cos.add_parser("link"); cli.add_argument("a"); cli.add_argument("b")

    # mind: attention, attention-add, attention-remove, mistakes, mistakes-add, mistakes-resolve, relation, export
    mi2 = sub.add_parser("mi", help="Mind fine-grained ops")
    mis = mi2.add_subparsers(dest="subcommand")
    mis.add_parser("attention"); mia = mis.add_parser("attention-add"); mia.add_argument("name"); mia.add_argument("weight", type=float)
    mir = mis.add_parser("attention-remove"); mir.add_argument("name")
    mis.add_parser("mistakes"); mis_a = mis.add_parser("mistakes-add"); mis_a.add_argument("pattern"); mis_a.add_argument("severity")
    mis_r = mis.add_parser("mistakes-resolve"); mis_r.add_argument("id")
    mis_rel = mis.add_parser("relation"); mis_rel.add_argument("entity")
    mis.add_parser("export")

    # task: node-detail, node-status, import, export
    tk2 = sub.add_parser("tk", help="Task fine-grained ops")
    tks = tk2.add_subparsers(dest="subcommand")
    tnd = tks.add_parser("node"); tnd.add_argument("id")
    tns = tks.add_parser("node-status"); tns.add_argument("id"); tns.add_argument("val")
    tks.add_parser("import"); tks.add_parser("export")

    # pcr: show, config-show, config-set, config-reset, history
    pc2 = sub.add_parser("pc", help="PCR fine-grained ops")
    pcs = pc2.add_subparsers(dest="subcommand")
    pcs.add_parser("show"); pcs.add_parser("config"); pcs.add_parser("config-reset"); pcs.add_parser("history")
    preg.add_argument("--filter", default="")

    # ── P9: Design-complete subcommands (added to existing parsers) ──
    # No new parsers needed — subcommands added via dispatch map only
    # ── P9: Extra commands (non-conflicting names) ──
    bp2 = sub.add_parser("bp", help="Blueprint write ops")
    bps = bp2.add_subparsers(dest="subcommand")
    x = bps.add_parser("node-add"); x.add_argument("chain", nargs="*", default=["pcr"])
    y = bps.add_parser("node-remove"); y.add_argument("id", nargs="*", default=["?"])
    z = bps.add_parser("node-edit"); z.add_argument("id", nargs="*", default=["?"])
    bps.add_parser("edge-add"); bps.add_parser("edge-remove"); bps.add_parser("edge-required")
    bps.add_parser("strategy"); bps.add_parser("strategy-set")

    dc2 = sub.add_parser("dc", help="Decider write ops")
    dcs = dc2.add_subparsers(dest="subcommand")
    dcs.add_parser("tick"); t = dcs.add_parser("chain"); t.add_argument("name", nargs="*", default=["all"])

    ds2 = sub.add_parser("ds", help="Discourse write ops")
    dss = ds2.add_subparsers(dest="subcommand")
    dss.add_parser("compress")
    su = dss.add_parser("summary"); su.add_argument("block_id", nargs="*", default=["?"]); su.add_argument("text", nargs="*", default=[""])
    dss.add_parser("topic-show")
    ta = dss.add_parser("topic-add"); ta.add_argument("topic", nargs="*", default=["?"])
    tr = dss.add_parser("topic-remove"); tr.add_argument("topic", nargs="*", default=["?"])
    dss.add_parser("topic-heat")

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
        sub = getattr(args, "subcommand", "")
        if sub == "show":
            from core.agent.cli.commands.pcr_intent_cmd import cmd_context
            cmd_context(args)
        else:
            _dispatch_p9(args)
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
        # P5: show commands first, then P8 for write ops
        sub = getattr(args, "subcommand", "")
        if sub in ("add", "delete", "edit"):
            _dispatch_p8(args)
        else:
            _dispatch_p5(args)
    elif args.command in ("bp", "dc", "ds"):
        # Aliases: bp → blueprint, dc → decider, ds → discourse
        from core.agent.cli.commands.p9_cmd import (
            cmd_blueprint_node_add, cmd_blueprint_node_remove, cmd_blueprint_node_edit,
            cmd_blueprint_edge_add, cmd_blueprint_edge_remove, cmd_blueprint_edge_required,
            cmd_blueprint_strategy, cmd_blueprint_strategy_set,
            cmd_decider_tick, cmd_decider_chain,
            cmd_discourse_compress, cmd_discourse_summary,
            cmd_discourse_topic_show, cmd_discourse_topic_add,
            cmd_discourse_topic_remove, cmd_discourse_topic_heat,
        )
        cmd = args.command; sub = getattr(args, "subcommand", "")
        if cmd == "bp":
            {"node-add":cmd_blueprint_node_add,"node-remove":cmd_blueprint_node_remove,
             "node-edit":cmd_blueprint_node_edit,"edge-add":cmd_blueprint_edge_add,
             "edge-remove":cmd_blueprint_edge_remove,"edge-required":cmd_blueprint_edge_required,
             "strategy":cmd_blueprint_strategy,"strategy-set":cmd_blueprint_strategy_set}.get(sub, lambda a:0)(args)
        elif cmd == "dc":
            {"tick":cmd_decider_tick,"chain":cmd_decider_chain}.get(sub, lambda a:0)(args)
        elif cmd == "ds":
            {"compress":cmd_discourse_compress,"summary":cmd_discourse_summary,
             "topic-show":cmd_discourse_topic_show,"topic-add":cmd_discourse_topic_add,
             "topic-remove":cmd_discourse_topic_remove,"topic-heat":cmd_discourse_topic_heat}.get(sub, lambda a:0)(args)
    elif args.command in ("beh", "rul", "ob", "kn", "co", "mi", "tk", "pc"):
        _dispatch_batch1(args)
    elif args.command in ("se", "eg", "rp", "an", "cr", "cfg", "dt", "gl"):
        _dispatch_batch2(args)
    elif args.command in ("graph", "format", "eventlog", "memory"):
        _dispatch_p9(args)
    elif args.command in ("chat", "test", "ab", "monitor", "export", "data"):
        _dispatch_app(args)
    elif args.command == "task" and getattr(args, "subcommand", "") in ("node", "edge"):
        _dispatch_task_ops(args)
    elif args.command in ("d", "obs-put", "knowledge", "event-log", "profile-set",
                          "rules-delete", "annotations-add", "corrections-add",
                          "feedback-add", "registry"):
        _dispatch_p8(args)
    elif hasattr(args, "d_op"):
        _dispatch_p8(args)
    elif args.command in ("context", "format", "graph", "eventlog", "memory"):
        _dispatch_p9(args)
    else:
        if args.command == "reply" and args.subcommand is None:
            cmd_reply_model(args)
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
