"""English locale."""
LOCALE = {
    # App
    "app.title": "DialogMesh v4",
    "app.tagline": "Cognitive Runtime",

    # CLI - Runtime
    "cli.starting": "Starting Cognitive Runtime...",
    "cli.started": "Runtime started with {count} adapters",
    "cli.stopped": "Runtime stopped",
    "cli.not_running": "Runtime not running",
    "cli.event_sent": "Event sent: {text}",
    "cli.start_failed": "Failed to start runtime: {error}",

    # CLI - Status
    "cli.status.header": "{path}: {triggers} triggers, {success} success, {failure} failure, {latency:.0f}ms total",

    # CLI - Pipeline
    "cli.pipeline.created": "Pipeline '{name}' created",
    "cli.pipeline.not_found": "Pipeline '{name}' not found",
    "cli.pipeline.added": "Added {module} [{type}] to '{pipeline}'",
    "cli.pipeline.connected": "Connected {from_mod} -> {to_mod}",
    "cli.pipeline.param_set": "Set {module}.{key} = {value}",
    "cli.pipeline.exported": "Exported '{name}' to {path}",
    "cli.pipeline.default_created": "Default v4 DAG created: {nodes} nodes, {edges} edges",
    "cli.pipeline.no_pipelines": "No pipelines",

    # CLI - Inspect
    "cli.inspect.error": "Inspect error: {error}",
    "cli.inspect.unknown": "Unknown inspect command: {cmd}",
    "cli.no_observations": "No observations",
    "cli.no_skills": "No skills",
    "cli.no_knowledge": "(no frozen knowledge)",
    "cli.no_hypotheses": "(no hypotheses)",

    # CLI - Events
    "cli.events.replayed": "Replayed {count} events",
    "cli.events.no_events": "No events found",
    "cli.events.showing": "Showing {shown} of {total} events",

    # CLI - Maintenance
    "cli.maint.gc_done": "GC completed",
    "cli.maint.nodes": "Nodes: {count}",
    "cli.maint.edges": "Edges: {count}",
    "cli.maint.tiers": "Tiers: hot={hot}, warm={warm}, cold={cold}, archive={archive}",

    # CLI - Search
    "cli.search.results": "Search: {keyword} ({count} results)",
    "cli.search.no_results": "No results for: {keyword}",

    # CLI - Export
    "cli.export.knowledge": "Exported {count} knowledge nodes to {path}",
    "cli.export.skills": "Exported {count} skills to {path}",

    # CLI - Snapshot
    "cli.snapshot.restored": "Snapshot {id} found and valid",
    "cli.snapshot.not_found": "Snapshot {id} not found",
    "cli.snapshot.no_snapshots": "No snapshots found",

    # CLI - Config
    "cli.config.set": "Set {key} = {value} (runtime session only)",

    # CLI - Health
    "cli.health.pass": "PASS",
    "cli.health.fail": "FAIL",
    "cli.health.info": "INFO",
    "cli.health.all_pass": "All checks passed",
    "cli.health.some_fail": "Some checks FAILED",

    # TUI
    "tui.dashboard.title": "DialogMesh v4 Cognitive Runtime",
    "tui.dashboard.engine_off": "Engine not started",
    "tui.dashboard.obs_pool": "Observation Pool: {count} bundles",
    "tui.dashboard.last_ctx": "Last Context: {intent} ({items} items)",
    "tui.observations.title": "Observations",
    "tui.hypotheses.title": "Hypotheses (active only)",
    "tui.knowledge.title": "Knowledge Vault (frozen)",
    "tui.skills.title": "Skill Forge",
    "tui.world.title": "Semantic World Model",
    "tui.world.not_loaded": "World Graph not loaded",
    "tui.context.title": "Context Engineering (last IR)",
    "tui.context.no_data": "(no context compiled yet)",
    "tui.events.title": "Event Log (last 20)",
    "tui.events.total": "Total: {total} events, {unconsumed} unconsumed",
    "tui.world.graph_stats": "Graph: {world} ({nodes} nodes, {edges} edges)",

    # Commands / Help
    "tui.settings.title": "Settings",
    "tui.settings.lang": "Language: [{lang}] {name}",
    "tui.settings.press": "Press 'e' for English, 'z' for Chinese",
    "tui.settings.locale_count": "Current locale keys: {count}",
    "tui.settings.changed": "(changes take effect on next refresh)",
    "tui.no_observations": "(no observations)",
    "tui.no_hypotheses": "(no active hypotheses)",
    "tui.no_hypotheses_available": "(no hypotheses available)",
    "tui.no_knowledge": "(no frozen knowledge)",
    "tui.no_skills": "(no skills)",
    "tui.not_available": "(not available)",
    "tui.graph.stats": "Graph: {world} ({nodes} nodes, {edges} edges)",
    "tui.world.top_backbone": "Top Backbone:",
    "tui.world.communities": "Communities ({count}):",
    "tui.world.community_item": "  {cid}: {size} nodes",
    "tui.world.usage_hint": "Use: engine._world_graph = CodeWorldAdapter().build_graph('.')",
    "tui.context.intent": "Intent: {intent} ({total} items)",
    "tui.context.send_hint": "Send an event via CLI or API to trigger compilation.",
    "tui.context.domain_item": "  [{src}] {count} items (relevance: {rng})",
    "tui.context.domains": "Domains: {domains}",
    "tui.events.total": "Total: {total} events, {unconsumed} unconsumed",
    "tui.events.more": "... ({count} more events)",
    "tui.events.no_db": "Create data/ directory or send events to populate.",
    "tui.events.not_available": "EventLog not available: {error}",
    "tui.events.module_error": "EventLog module not available",
    "tui.error": "Error: {error}",
    "help.usage": "Commands: text=event, status=view, checkpoint=trigger, quit=exit",
}

def t(key, **kwargs):
    """Translate a key with optional formatting."""
    text = LOCALE.get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text
