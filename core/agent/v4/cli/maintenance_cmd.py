"""CLI storage maintenance commands."""
from __future__ import annotations


def _maintenance_gc(engine):
    """Run manual GC and tier migration."""
    try:
        from core.agent.v4.persistence.unified_store import UnifiedGraphStore
        store = UnifiedGraphStore("data/dialogmesh.db")
        store.open()
        result = store.run_maintenance()
        store.close()

        print("GC completed:")
        for tier, count in result.items():
            if count > 0:
                print(f"  {tier}: {count} nodes migrated")
        return 0
    except Exception as e:
        print(f"Maintenance error: {e}")
        return 1


def _maintenance_stats(engine):
    """Show tiered storage stats."""
    try:
        from core.agent.v4.persistence.unified_store import UnifiedGraphStore
        store = UnifiedGraphStore("data/dialogmesh.db")
        store.open()
        stats = store.stats
        store.close()

        print(f"Nodes: {stats.get('node_count', 0)}")
        print(f"Edges: {stats.get('edge_count', 0)}")

        # Tier distribution
        try:
            warm = len(store.query_nodes(tier="warm"))
            cold = len(store.query_nodes(tier="cold"))
            archive = len(store.query_nodes(tier="archive"))
            total = stats.get('node_count', 0)
            hot = max(0, total - warm - cold - archive)
            print(f"Tiers: hot={hot}, warm={warm}, cold={cold}, archive={archive}")
        except Exception:
            pass

        # Event log stats
        try:
            from core.agent.v4.api_event_log import EventLog
            el = EventLog("data/event_log.db")
            el.open()
            es = el.stats
            el.close()
            print(f"EventLog: {es['total']} total, {es['unconsumed']} unconsumed")
        except Exception:
            pass

        return 0
    except Exception as e:
        print(f"Maintenance stats error: {e}")
        return 1
