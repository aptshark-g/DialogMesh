"""CLI session management commands."""
from __future__ import annotations


def _session_list(engine):
    """List active sessions."""
    try:
        # Engine tracks sessions via _event_buffer and adapter state
        if engine is None:
            print("Engine not started")
            return 1
        print("Active sessions:")
        print(f"  Events buffered: {len(getattr(engine, '_event_buffer', []))}")
        print(f"  Adapters active: {engine.adapter_count}")
        async_stats = engine.stats.get("async", {}) if hasattr(engine, 'stats') else {}
        print(f"  Async path: {getattr(async_stats, 'trigger_count', 0)} triggers, "
              f"{getattr(async_stats, 'success_count', 0)} success")
        return 0
    except Exception as e:
        print(f"Session error: {e}")
        return 1


def _session_show(engine, session_id: str):
    """Show session details."""
    print(f"Session: {session_id}")
    return _session_list(engine)
