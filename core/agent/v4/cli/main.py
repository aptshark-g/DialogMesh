"""DialogMesh v4 CLI — Runtime DAG Editor and Status Monitor."""
from __future__ import annotations
import argparse, json, sys, os
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
    else:
        parser.print_help()
        return 0


# ---- Command implementations ----

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
