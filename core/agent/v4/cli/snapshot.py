"""CLI snapshot management commands."""
from __future__ import annotations


def _snapshot_list(engine, limit: int = 10):
    """List snapshots from UnifiedGraphStore."""
    try:
        from core.agent.v4.persistence.unified_store import UnifiedGraphStore
        store = UnifiedGraphStore("data/dialogmesh.db")
        store.open()
        snapshots = store.get_snapshots(limit=limit)
        store.close()

        if not snapshots:
            print("No snapshots found")
            return 0

        print(f"{'ID':<25s} {'Created':<20s} {'Nodes':<8s} {'Edges':<8s}")
        print("-" * 65)
        for s in snapshots:
            ts = str(s.created_at)[:19]
            print(f"{s.snapshot_id:<25s} {ts:<20s} {s.node_count:<8d} {s.edge_count:<8d}")
        return 0
    except Exception as e:
        print(f"Snapshot list error: {e}")
        return 1


def _snapshot_restore(engine, snapshot_id: str):
    """Restore from a snapshot."""
    try:
        from core.agent.v4.persistence.snapshot import SnapshotManager
        from core.agent.v4.persistence.unified_store import UnifiedGraphStore
        store = UnifiedGraphStore("data/dialogmesh.db")
        store.open()
        mgr = SnapshotManager(store)
        ok = mgr.restore_from_snapshot(snapshot_id)
        store.close()

        if ok:
            print(f"Snapshot {snapshot_id} found and valid")
            return 0
        print(f"Snapshot {snapshot_id} not found")
        return 1
    except Exception as e:
        print(f"Snapshot restore error: {e}")
        return 1
