"""DialogMesh v4 CLI — Runtime DAG Editor and Status Monitor."""
from __future__ import annotations
import argparse, sys, os
from typing import Dict, Optional

# Global registry of active pipelines
_pipelines: Dict[str, "RuntimeDAG"] = {}
_engine: Optional["CognitiveRuntimeEngine"] = None


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="dialogmesh",
        description="DialogMesh v4 CLI — Runtime DAG Editor and Status Monitor",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # start
    start = sub.add_parser("start", help="Start the cognitive runtime engine")
    start.add_argument("--config", "-c", help="Path to runtime.yaml")

    # stop
    sub.add_parser("stop", help="Stop the runtime engine")

    # status
    sub.add_parser("status", help="Show runtime engine stats")

    # event
    event = sub.add_parser("event", help="Send a user event to the runtime")

    # events (audit) — separate from event (send)
    evt = sub.add_parser("events", help="Event audit and replay")
    evt_sub = evt.add_subparsers(dest="evt_cmd")
    evt_sub.add_parser("history", help="Show event history")
    evt_sub.add_parser("replay", help="Replay unconsumed events")
    event.add_argument("text", help="Event text")

    # pipeline
    pipe = sub.add_parser("pipeline", help="Runtime DAG builder commands")
    pipe_sub = pipe.add_subparsers(dest="pipe_cmd")

    create = pipe_sub.add_parser("create", help="Create a new pipeline")
    create.add_argument("name", help="Pipeline name")

    add = pipe_sub.add_parser("add", help="Add a module to a pipeline")
    add.add_argument("pipeline", help="Pipeline name")
    add.add_argument("module", help="Module name")
    add.add_argument("type", help="Module type")
    add.add_argument("--path", "-p", default="async", help="Path (async/slow/deep)")

    connect = pipe_sub.add_parser("connect", help="Connect two modules")
    connect.add_argument("pipeline", help="Pipeline name")
    connect.add_argument("from_mod", help="Source module")
    connect.add_argument("to_mod", help="Target module")

    param = pipe_sub.add_parser("param", help="Set a module parameter")
    param.add_argument("pipeline", help="Pipeline name")
    param.add_argument("module", help="Module name")
    param.add_argument("key", help="Parameter key")
    param.add_argument("value", help="Parameter value")

    show = pipe_sub.add_parser("show", help="Show a pipeline")
    show.add_argument("name", help="Pipeline name")

    p_list = pipe_sub.add_parser("list", help="List all pipelines")

    export = pipe_sub.add_parser("export", help="Export pipeline to YAML")
    export.add_argument("name", help="Pipeline name")
    export.add_argument("path", help="Output YAML path")

    default = pipe_sub.add_parser("default", help="Build default v4 DAG")

    # inspect
    inv = sub.add_parser("inspect", help="View system state")
    inv_sub = inv.add_subparsers(dest="inspect_cmd")

    # v4 — with detail support
    obs = inv_sub.add_parser("observations", help="View Observation pool")
    obs.add_argument("--detail", action="store_true", help="Show full detail")
    obs.add_argument("--id", help="Show single observation by ID")
    obs.add_argument("--page", type=int, default=1, help="Page number")
    obs.add_argument("--page-size", type=int, default=10)
    obs.add_argument("--json", action="store_true")

    hyp = inv_sub.add_parser("hypotheses", help="View Hypothesis competition")
    hyp.add_argument("--detail", action="store_true")
    hyp.add_argument("--id", help="Show single hypothesis by ID")
    hyp.add_argument("--page", type=int, default=1, help="Page number")
    hyp.add_argument("--page-size", type=int, default=10)
    hyp.add_argument("--json", action="store_true")

    kno = inv_sub.add_parser("knowledge", help="View frozen Knowledge")
    kno.add_argument("--detail", action="store_true")
    kno.add_argument("--json", action="store_true")
    kno.add_argument("--id", help="Show single knowledge by ID")

    ski = inv_sub.add_parser("skills", help="View distilled Skills")
    ski.add_argument("--detail", action="store_true")
    ski.add_argument("--id", help="Show single skill by name")
    ski.add_argument("--page", type=int, default=1)
    ski.add_argument("--page-size", type=int, default=10)
    ski.add_argument("--json", action="store_true")

    wor = inv_sub.add_parser("world", help="View World Graph")
    wor.add_argument("--detail", action="store_true")
    wor.add_argument("--id", help="Show single node by unit_id")

    ctx = inv_sub.add_parser("context", help="View last context IR")
    ctx.add_argument("--detail", action="store_true")

    # v3.2 — simple viewers (no detail needed)
    inv_sub.add_parser("behavior", help="View v3.2 behavior patterns")
    inv_sub.add_parser("causal", help="View v3.2 causal chains")
    inv_sub.add_parser("constraints", help="View engineering constraints")
    inv_sub.add_parser("discourse", help="View discourse tree")
    inv_sub.add_parser("fusion", help="View fusion engine")
    inv_sub.add_parser("summary", help="View L1/L2 summaries")
    inv_sub.add_parser("store", help="View tiered storage")
    inv_sub.add_parser("pcr", help="View parameter registry")
    inv_sub.add_parser("topics", help="View topic tree")
    # snapshot
    snap = sub.add_parser("snapshot", help="Snapshot management")
    snap_sub = snap.add_subparsers(dest="snap_cmd")
    snap_sub.add_parser("list", help="List snapshots")
    restore = snap_sub.add_parser("restore", help="Restore from snapshot")
    restore.add_argument("snapshot_id", help="Snapshot ID")

    # config
    cfg = sub.add_parser("config", help="Configuration management")
    cfg_sub = cfg.add_subparsers(dest="cfg_cmd")
    cfg_sub.add_parser("show", help="Show current configuration")
    cfg_set = cfg_sub.add_parser("set", help="Set a configuration value")
    cfg_set.add_argument("key", help="Parameter key")
    cfg_set.add_argument("value", help="Parameter value")

    # health
    sub.add_parser("health", help="Run system health check")

    # event commands
    evt = sub.add_parser("event", help="Event management")
    evt_sub = evt.add_subparsers(dest="evt_cmd")
    evt_sub.add_parser("history", help="Show event history")
    evt_sub.add_parser("replay", help="Replay unconsumed events")

    # maintenance
    mnt = sub.add_parser("maintenance", help="Storage maintenance")
    mnt_sub = mnt.add_subparsers(dest="mnt_cmd")
    mnt_sub.add_parser("gc", help="Run garbage collection")
    mnt_sub.add_parser("stats", help="Show storage stats")

    # search
    sch = sub.add_parser("search", help="Cross-module search")
    sch.add_argument("keyword", help="Search keyword")

    # export
    exp = sub.add_parser("export", help="Export data")
    exp_sub = exp.add_subparsers(dest="exp_cmd")
    exp_sub.add_parser("knowledge", help="Export frozen Knowledge")
    exp_sub.add_parser("skills", help="Export Skills")

    # session
    ses = sub.add_parser("session", help="Session management")
    ses_sub = ses.add_subparsers(dest="ses_cmd")
    ses_sub.add_parser("list", help="List active sessions")
    ses_show = ses_sub.add_parser("show", help="Show session details")
    ses_show.add_argument("session_id", help="Session ID")

    return parser


def main(argv=None):
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "start":
        return cmd_start(args)
    elif args.command == "stop":
        return cmd_stop(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "event":
        return cmd_event(args)
    elif args.command == "pipeline":
        return cmd_pipeline(args)
    elif args.command == "inspect":
        return cmd_inspect(args)
    elif args.command == "snapshot":
        return cmd_snapshot(args)
    elif args.command == "config":
        return cmd_config(args)
    elif args.command == "health":
        return cmd_health(args)
    elif args.command == "events":
        return cmd_events(args)
    elif args.command == "maintenance":
        return cmd_maintenance(args)
    elif args.command == "search":
        return cmd_search(args)
    elif args.command == "export":
        return cmd_export(args)
    elif args.command == "session":
        return cmd_session(args)
    else:
        parser.print_help()
        return 0


# ---- Command implementations ----

def cmd_inspect(args):
    global _engine
    cmd = args.inspect_cmd
    try:
        from core.agent.v4.cli.inspect import (
            _inspect_observations, _inspect_hypotheses, _inspect_knowledge,
            _inspect_skills, _inspect_world, _inspect_context,
        )
        from core.agent.v4.cli.inspect_v3 import (
            _inspect_behavior, _inspect_causal, _inspect_constraints,
            _inspect_discourse, _inspect_fusion, _inspect_summary,
            _inspect_store, _inspect_pcr, _inspect_topics,
        )

        dispatch = {
            "observations": lambda: _inspect_observations(
                _engine, detail=args.detail, item_id=getattr(args, 'id', None),
                page=args.page, page_size=args.page_size),
            "hypotheses": lambda: _inspect_hypotheses(
                _engine, detail=args.detail, item_id=getattr(args, 'id', None),
                page=args.page, page_size=args.page_size),
            "knowledge": lambda: _inspect_knowledge(
                _engine, detail=args.detail, item_id=getattr(args, 'id', None)),
            "skills": lambda: _inspect_skills(
                _engine, detail=args.detail, item_id=getattr(args, 'id', None),
                page=args.page, page_size=args.page_size),
            "world": lambda: _inspect_world(
                _engine, detail=args.detail, item_id=getattr(args, 'id', None)),
            "context": lambda: _inspect_context(
                _engine, detail=args.detail,
                json_output=getattr(args, "json", False)),
            "behavior": lambda: _inspect_behavior(_engine),
            "causal": lambda: _inspect_causal(_engine),
            "constraints": lambda: _inspect_constraints(_engine),
            "discourse": lambda: _inspect_discourse(_engine),
            "fusion": lambda: _inspect_fusion(_engine),
            "summary": lambda: _inspect_summary(_engine),
            "store": lambda: _inspect_store(_engine),
            "pcr": lambda: _inspect_pcr(_engine),
            "topics": lambda: _inspect_topics(_engine),
        }
        fn = dispatch.get(cmd)
        if fn:
            return fn()
        print(f"Unknown inspect command: {cmd}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Inspect error: {e}", file=sys.stderr)
        return 1

def cmd_snapshot(args):
    global _engine
    try:
        from core.agent.v4.cli.snapshot import _snapshot_list, _snapshot_restore
        if args.snap_cmd == "list":
            return _snapshot_list(_engine)
        elif args.snap_cmd == "restore":
            return _snapshot_restore(_engine, args.snapshot_id)
        print(f"Unknown snapshot command: {args.snap_cmd}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Snapshot error: {e}", file=sys.stderr)
        return 1


def cmd_config(args):
    global _engine
    try:
        from core.agent.v4.cli.config_cmd import _config_show, _config_set
        if args.cfg_cmd == "show":
            return _config_show(_engine)
        elif args.cfg_cmd == "set":
            return _config_set(_engine, args.key, args.value)
        print(f"Unknown config command: {args.cfg_cmd}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1


def cmd_health(args):
    global _engine
    try:
        from core.agent.v4.cli.health import _health_check
        return _health_check(_engine)
    except Exception as e:
        print(f"Health check error: {e}", file=sys.stderr)
        return 1

def cmd_events(args):
    global _engine
    try:
        from core.agent.v4.cli.event_cmd import _event_history, _event_replay
        if args.evt_cmd == "history":
            return _event_history(_engine)
        elif args.evt_cmd == "replay":
            return _event_replay(_engine)
        print(f"Unknown events command: {args.evt_cmd}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Events error: {e}", file=sys.stderr)
        return 1


def cmd_maintenance(args):
    global _engine
    try:
        from core.agent.v4.cli.maintenance_cmd import _maintenance_gc, _maintenance_stats
        if args.mnt_cmd == "gc":
            return _maintenance_gc(_engine)
        elif args.mnt_cmd == "stats":
            return _maintenance_stats(_engine)
        print(f"Unknown maintenance command: {args.mnt_cmd}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Maintenance error: {e}", file=sys.stderr)
        return 1


def cmd_search(args):
    global _engine
    try:
        from core.agent.v4.cli.search_cmd import _search
        return _search(_engine, args.keyword)
    except Exception as e:
        print(f"Search error: {e}", file=sys.stderr)
        return 1

def cmd_export(args):
    global _engine
    try:
        from core.agent.v4.cli.export_cmd import _export_knowledge, _export_skills
        if args.exp_cmd == "knowledge":
            return _export_knowledge(_engine)
        elif args.exp_cmd == "skills":
            return _export_skills(_engine)
        print(f"Unknown export command: {args.exp_cmd}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Export error: {e}", file=sys.stderr)
        return 1


def cmd_session(args):
    global _engine
    try:
        from core.agent.v4.cli.session_cmd import _session_list, _session_show
        if args.ses_cmd == "list":
            return _session_list(_engine)
        elif args.ses_cmd == "show":
            return _session_show(_engine, args.session_id)
        print(f"Unknown session command: {args.ses_cmd}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Session error: {e}", file=sys.stderr)
        return 1

def cmd_start(args):
    global _engine
    try:
        from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
        _engine = CognitiveRuntimeEngine(config_path=args.config)
        _engine.start()
        print(f"Runtime started with {_engine.adapter_count} adapters")
        return 0
    except Exception as e:
        print(f"Failed to start runtime: {e}", file=sys.stderr)
        return 1


def cmd_stop(args):
    global _engine
    if _engine is not None:
        _engine.stop()
        _engine = None
        print("Runtime stopped")
    return 0


def cmd_status(args):
    global _engine
    if _engine is None:
        print("Runtime not running")
        return 1

    for path_name, stats in _engine.stats.items():
        print(f"{path_name}: {stats.trigger_count} triggers, "
              f"{stats.success_count} success, {stats.failure_count} failure, "
              f"{stats.total_latency_ms:.0f}ms total")
    return 0


def cmd_event(args):
    global _engine
    if _engine is None:
        print("Runtime not running", file=sys.stderr)
        return 1

    try:
        from core.agent.v4.event_ir import EventIR
        event = EventIR(
            id=f"cli_{int(__import__('time').time())}",
            kind="dialog.message",
            payload={"text": args.text, "source": "cli"},
        )
        _engine.on_event(event)
        print(f"Event sent: {args.text[:50]}...")
        return 0
    except Exception as e:
        print(f"Failed to send event: {e}", file=sys.stderr)
        return 1


def cmd_pipeline(args):
    global _pipelines

    try:
        from core.agent.v4.cli.builder import RuntimeBuilder

        if args.pipe_cmd == "create":
            _pipelines[args.name] = RuntimeBuilder(args.name)
            print(f"Pipeline '{args.name}' created")
        elif args.pipe_cmd == "list":
            if not _pipelines:
                print("No pipelines")
            for name in _pipelines:
                dag = _pipelines[name].build()
                print(f"  {name}: {len(dag.nodes)} nodes, {len(dag.edges)} edges")
        elif args.pipe_cmd == "show":
            builder = _pipelines.get(args.name)
            if builder is None:
                print(f"Pipeline '{args.name}' not found", file=sys.stderr)
                return 1
            dag = builder.build()
            print(f"Pipeline: {dag.name} ({len(dag.nodes)} nodes, {len(dag.edges)} edges)")
            for node in dag.nodes:
                print(f"  [{node.path}] {node.name}")
            for edge in dag.edges:
                print(f"  {edge.from_module} -> {edge.to_module}")
        elif args.pipe_cmd == "add":
            builder = _pipelines.get(args.pipeline)
            if builder is None:
                print(f"Pipeline '{args.pipeline}' not found", file=sys.stderr)
                return 1
            builder.add_module(args.module, args.type, path=args.path)
            print(f"Added {args.module} [{args.type}] to '{args.pipeline}'")
        elif args.pipe_cmd == "connect":
            builder = _pipelines.get(args.pipeline)
            if builder is None:
                print(f"Pipeline '{args.pipeline}' not found", file=sys.stderr)
                return 1
            builder.connect(args.from_mod, args.to_mod)
            print(f"Connected {args.from_mod} -> {args.to_mod}")
        elif args.pipe_cmd == "param":
            builder = _pipelines.get(args.pipeline)
            if builder is None:
                print(f"Pipeline '{args.pipeline}' not found", file=sys.stderr)
                return 1
            builder.param(args.module, args.key, args.value)
            print(f"Set {args.module}.{args.key} = {args.value}")
        elif args.pipe_cmd == "export":
            builder = _pipelines.get(args.name)
            if builder is None:
                print(f"Pipeline '{args.name}' not found", file=sys.stderr)
                return 1
            dag = builder.build()
            dag.save(args.path)
            print(f"Exported '{args.name}' to {args.path}")
        elif args.pipe_cmd == "default":
            builder = RuntimeBuilder("v4-default")
            dag = builder.build_default_v4_dag()
            _pipelines["v4-default"] = builder
            print(f"Default v4 DAG created: {len(dag.nodes)} nodes, {len(dag.edges)} edges")
            for node in dag.nodes:
                print(f"  [{node.path}] {node.name}")
        else:
            print("Unknown pipeline command", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Pipeline error: {e}", file=sys.stderr)
        return 1

    return 0
