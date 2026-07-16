"""DialogMesh v4 CLI — semantic world runtime.

Design: README.md §CLI 命令大全 (27 commands)
Delegates: scripts/dialogmesh.py → this module
"""
import sys, os, json, argparse, time, logging
from typing import Optional

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


class V4CLI:
    """v4 CLI adapter: builds world model lazily, exposes engine inspection."""

    def __init__(self, api_key: str = None):
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self._engine = None
        self._pool = None
        self._provider = None
        self._objects = None
        self._ort = None

    # ── Lazy init ──

    def _init_engine(self):
        if self._engine is not None:
            return
        from core.agent.v4.runtime.engine import CognitiveRuntimeEngine

        if self._api_key:
            from core.agent.llm_providers.openai_provider import OpenAIProvider
            llm = OpenAIProvider("deepseek", {
                "api_key": self._api_key,
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
            })
        else:
            from core.agent.llm_providers.mock_provider import MockProvider
            llm = MockProvider("mock", {})

        self._engine = CognitiveRuntimeEngine(llm_provider=llm)
        self._engine.start()
        self._provider = llm

    def _init_world(self):
        self._init_engine()
        if self._pool is not None:
            return
        from core.agent.v4.observation_compiler.pool import ObservationPool
        from core.agent.v4.document.pipeline import DocumentIngestionPipeline
        from core.agent.v4.chunking.strategies import default_registry, RuntimeConstraints
        from core.agent.v4.context.graph_source import ConceptGraph
        from core.agent.v4.compiler.semantic_path import SemanticIndex
        from core.agent.v4.compiler.relation_substrate import RelationSubstrate
        from core.agent.v4.compiler.content_provider import ContentProvider
        from core.agent.v4.compiler.object_builder import build_object_graph
        from core.agent.v4.compiler.object_runtime import ObjectRuntime

        self._pool = ObservationPool()
        import glob
        docs = glob.glob("docs/v3.0/DESIGN_*.md")[:10]
        pipeline = DocumentIngestionPipeline(pool=self._pool, registry=default_registry())
        for d in docs:
            pipeline.ingest_file(d, constraints=RuntimeConstraints(500))

        graph = ConceptGraph(); graph.build_from_pool(self._pool)
        idx = SemanticIndex(); idx.build_from_pool(self._pool, graph)
        rs = RelationSubstrate(); rs.build_from_concept_graph(graph); rs.build_from_heading(idx, graph)
        prov = ContentProvider(self._pool, idx); prov.set_relation_substrate(rs)
        self._objects = build_object_graph(self._pool, graph, idx)
        self._ort = ObjectRuntime(provider=prov); self._ort.set_store(self._objects)

        self._engine.set_observation_pool(self._pool)
        self._engine.set_content_provider(prov)
        self._engine.set_object_store(self._objects, self._ort, prov)

    # ── Status ──

    def status(self) -> str:
        self._init_world()
        e = self._engine
        lines = [
            "=== DialogMesh v4 Status ===",
            f"  Running: {getattr(e, '_running', False)}",
            f"  Event counter: {e._event_counter.count}/{e._event_counter.threshold}",
        ]
        if self._pool:
            s = self._pool.stats()
            lines.append(f"  Pool: {s.get('total_bundles', '?')} bundles, {s.get('total_observations', '?')} obs")
        if self._objects:
            lines.append(f"  Objects: {len(self._objects)}")
        if self._ort:
            lines.append(f"  Runtime: ready")
        ctx = getattr(e, 'last_context', None)
        if ctx:
            lines.append(f"  Last context: {len(ctx.entries) if ctx.entries else 0} entries")
        return "\n".join(lines)

    # ── Inspect ──

    def inspect_observations(self, detail: bool = False) -> str:
        self._init_world()
        if not self._pool:
            return "Pool not loaded."
        s = self._pool.stats()
        lines = [f"Observations: {s.get('total_observations', '?')} total"]
        by_domain = s.get("by_domain", {})
        for d, n in by_domain.items():
            lines.append(f"  {d}: {n}")
        return "\n".join(lines)

    def inspect_hypotheses(self, detail: bool = False, hid: str = None) -> str:
        return "Hypothesis engine: pipeline available (use /status for stats)"

    def inspect_knowledge(self) -> str:
        self._init_world()
        if not self._objects:
            return "Knowledge space not loaded."
        return f"Knowledge objects: {len(self._objects)} (sampling 5)\n" + \
               "\n".join(f"  - {name}" for name in list(self._objects.keys())[:5])

    def inspect_skills(self) -> str:
        return "Skill layer: distillation on Slow Path"

    def inspect_world(self) -> str:
        self._init_world()
        if not self._objects:
            return "World not loaded."
        return f"World graph: {len(self._objects)} objects"

    def inspect_context(self) -> str:
        self._init_world()
        ctx = getattr(self._engine, 'last_context', None)
        if not ctx or not ctx.entries:
            return "No context compiled yet."
        lines = [f"Last context: {len(ctx.entries)} entries"]
        for e in ctx.entries:
            t = getattr(e, "type", "?")
            d = getattr(e, "domain", "?")
            c = getattr(e, "content", "")[:100]
            lines.append(f"  [{d}/{t}] {c}")
        return "\n".join(lines)

    # ── Events ──

    def send_event(self, text: str) -> str:
        self._init_world()
        from core.agent.v4.event_ir import DialogAdapter
        e = self._engine
        ad = DialogAdapter()
        resp = e.on_event(ad.adapt(text, session_id="cli_session", turn_number=1))
        return resp or "(no response)"

    # ── Health ──

    def health(self) -> str:
        self._init_engine()
        return "OK" if self._engine and getattr(self._engine, '_running', False) else "DOWN"

    # ── Maintenance ──

    def maintenance_stats(self) -> str:
        return "Storage: in-memory (pool + graph). Persistence: event_log.db"

    def events_history(self) -> str:
        return "Event log: data/event_log.db"

    def search(self, query: str) -> str:
        self._init_world()
        if not self._objects:
            return "No objects loaded."
        results = [name for name in self._objects if query.lower() in name.lower()]
        return f"Found {len(results)} matching '{query}':\n" + \
               "\n".join(f"  - {r}" for r in results[:10])

    def export_knowledge(self) -> str:
        self._init_world()
        if not self._objects:
            return "{}"
        return json.dumps({name: {"identity": obj.identity}
                          for name, obj in list(self._objects.items())[:10]},
                         ensure_ascii=False, indent=2)

    # ── Snapshot ──

    def snapshot_list(self) -> str:
        return "Snapshots not yet implemented (Phase 3)"


# ── CLI entry point ──

def main():
    parser = argparse.ArgumentParser(description="DialogMesh v4 CLI")
    sub = parser.add_subparsers(dest="command")

    # Runtime
    sub.add_parser("start")
    sub.add_parser("status")
    p_event = sub.add_parser("event")
    p_event.add_argument("text")
    sub.add_parser("health")

    # Inspect
    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("target", choices=["observations", "hypotheses", "knowledge",
                                               "skills", "world", "context"])
    p_inspect.add_argument("--detail", action="store_true")
    p_inspect.add_argument("--id")
    p_inspect.add_argument("--json", action="store_true")

    # Maintenance
    sub.add_parser("snapshot").add_argument("action", choices=["list"])
    sub.add_parser("config").add_argument("action", choices=["show"])
    sub.add_parser("maintenance").add_argument("action", choices=["stats"])
    sub.add_parser("events").add_argument("action", choices=["history"])
    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    sub.add_parser("export").add_argument("target", choices=["knowledge"])

    args = parser.parse_args()

    cli = V4CLI()

    if args.command == "start":
        cli._init_engine()
        print("Engine started.")
    elif args.command == "status":
        print(cli.status())
    elif args.command == "event":
        print(cli.send_event(args.text))
    elif args.command == "health":
        print(cli.health())
    elif args.command == "inspect":
        target = args.target
        if target == "observations":
            print(cli.inspect_observations(detail=args.detail))
        elif target == "hypotheses":
            print(cli.inspect_hypotheses(detail=args.detail, hid=args.id))
        elif target == "knowledge":
            print(cli.inspect_knowledge())
        elif target == "skills":
            print(cli.inspect_skills())
        elif target == "world":
            print(cli.inspect_world())
        elif target == "context":
            print(cli.inspect_context())
    elif args.command == "snapshot":
        print(cli.snapshot_list())
    elif args.command == "config":
        print("Configuration: see core/agent/v4/compiler/parameter_registry.py")
    elif args.command == "maintenance":
        print(cli.maintenance_stats())
    elif args.command == "events":
        print(cli.events_history())
    elif args.command == "search":
        print(cli.search(args.query))
    elif args.command == "export":
        print(cli.export_knowledge())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
