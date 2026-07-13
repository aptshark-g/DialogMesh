"""CLI event audit and replay commands."""
from __future__ import annotations


def _event_history(engine, limit: int = 20, kind: str = None):
    """Show event history from EventLog."""
    try:
        from core.agent.v4.api_event_log import EventLog
        el = EventLog("data/event_log.db")
        el.open()
        events = el.replay_unconsumed(limit=limit * 2)  # Get more for filtering
        el.close()

        if kind:
            events = [e for e in events if e["kind"] == kind]

        shown = events[:limit]
        if not shown:
            print("No events found")
            return 0

        print(f"{'Event ID':<25s} {'Kind':<20s} {'Created'}")
        print("-" * 70)
        for ev in shown:
            print(f"{ev['event_id']:<25s} {ev['kind']:<20s} {ev['created_at']}")
        print(f"Showing {len(shown)} of {len(events)} events")
        return 0
    except Exception as e:
        print(f"Event history error: {e}")
        return 1


def _event_replay(engine, unconsumed_only: bool = True):
    """Replay unconsumed events."""
    try:
        from core.agent.v4.api_event_log import EventLog
        from core.agent.v4.event_ir import EventIR

        el = EventLog("data/event_log.db")
        el.open()
        events = el.replay_unconsumed(limit=100)
        count = 0
        for ev in events:
            if unconsumed_only and ev.get("consumed", False):
                continue
            event_ir = EventIR(
                id=ev["event_id"],
                kind=ev["kind"],
                payload=ev.get("payload", {}),
            )
            if engine:
                engine.on_event(event_ir)
            el.ack_event(ev["event_id"])
            count += 1

        el.close()
        print(f"Replayed {count} events")
        return 0
    except Exception as e:
        print(f"Event replay error: {e}")
        return 1
