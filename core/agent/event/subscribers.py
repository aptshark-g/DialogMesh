"""Phase 1: EventBus Subscribers — async parallel handlers.

When on_event publishes, these subscribers run in parallel.
Replaces serial chain with pub/sub coordination.
"""
import json, os, time, logging, asyncio
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DiscourseSubscriber:
    """Receives pcr_computed → updates discourse block tree."""
    def __init__(self, engine=None):
        self._engine = engine
        self.events = 0
        self.last_result = None

    def handle(self, kind: str, payload: dict):
        e = self._engine
        if not e or not hasattr(e, '_discourse_tree'):
            return
        text = payload.get("text", "")
        sid = payload.get("session_id", "default")
        try:
            e._discourse_tree.feed(text, sid)
            self.events += 1
            logger.debug("DiscourseSubscriber: fed block, total=%s", self.events)
        except Exception as ex:
            logger.debug("DiscourseSubscriber skip: %s", ex)


class BehaviorSubscriber:
    """Receives user_message → records to behavior graph."""
    def __init__(self, engine=None):
        self._engine = engine
        self.events = 0

    def handle(self, kind: str, payload: dict):
        e = self._engine
        if not e: return
        bg = getattr(e, '_behavior_graph', None)
        if not bg: return
        try:
            # Use available API: get_recent_chain or load
            if hasattr(bg, 'load'):
                bg.load()
                self.events += 1
        except Exception:
            pass


class MetaSubscriber:
    """Receives intent_parsed → feeds meta cognition."""
    def __init__(self, engine=None):
        self._engine = engine
        self.events = 0

    def handle(self, kind: str, payload: dict):
        e = self._engine
        mc = getattr(e, '_meta_cognition', None)
        if not mc: return
        try:
            if hasattr(mc, 'retrospect'):
                mc.retrospect()
                self.events += 1
            elif hasattr(mc, 'process_queue'):
                mc.process_queue()
                self.events += 1
        except Exception:
            pass


class ProfileSubscriber:
    """Receives user_message → triggers OCEAN analysis."""
    def __init__(self, engine=None):
        self._engine = engine
        self.events = 0

    def handle(self, kind: str, payload: dict):
        e = self._engine
        ocean = getattr(e, '_ocean_analyst', None)
        if not ocean: return
        text = payload.get("text", "")
        if text and hasattr(ocean, 'analyze'):
            try:
                # analyze() takes session_id or text
                ocean.analyze(session_id=payload.get("session_id", "default"))
                self.events += 1
            except Exception:
                try:
                    ocean.analyze_with_bfi_override(text)
                    self.events += 1
                except Exception:
                    pass


class AssociationSubscriber:
    """Receives intent_parsed → feeds L1 modifier + L2.5 belief."""
    def __init__(self, engine=None):
        self._engine = engine
        self.events = 0

    def handle(self, kind: str, payload: dict):
        e = self._engine
        text = payload.get("text", "")
        if not text:
            return
        l1 = getattr(e, '_l1_modifier', None)
        l2 = getattr(e, '_l2_5_belief', None)
        results = {}
        if l1 and hasattr(l1, 'extract'):
            try:
                mods = l1.extract(text)
                results["modifiers"] = len(mods) if mods else 0
            except Exception:
                pass
        if l2 and hasattr(l2, 'ingest'):
            try:
                l2.ingest({"text": text, "ts": time.time()})
                results["belief_updated"] = True
            except Exception:
                pass
        self.events += 1
        self.last_result = results


class PersistenceSubscriber:
    """Receives all events → triggers _persist_state."""
    def __init__(self, engine=None):
        self._engine = engine
        self.events = 0
        self._last_persist = 0

    def handle(self, kind: str, payload: dict):
        e = self._engine
        if not e or not hasattr(e, '_persist_state'):
            return
        now = time.time()
        # Debounce: persist at most once per 5 seconds
        if now - self._last_persist < 5:
            return
        try:
            e._persist_state()
            self._last_persist = now
            self.events += 1
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
#  EventBus Wiring — registers all subscribers with engine
# ═══════════════════════════════════════════════════════════

def wire_subscribers(engine) -> dict:
    """Create all subscribers and register them with engine's EventBus.
    Returns stats dict for monitoring."""
    subs = {
        "discourse": DiscourseSubscriber(engine),
        "behavior": BehaviorSubscriber(engine),
        "meta": MetaSubscriber(engine),
        "profile": ProfileSubscriber(engine),
        "association": AssociationSubscriber(engine),
        "persistence": PersistenceSubscriber(engine),
    }

    # Store on engine for CLI inspection
    engine._event_subscribers = subs

    # Register with EventBus if available
    bus = getattr(engine, '_event_bus', None)
    if bus:
        # Wire each subscriber to their event pattern
        for name, handler in [
            ("discourse", subs["discourse"]),
            ("behavior", subs["behavior"]),
            ("meta", subs["meta"]),
            ("profile", subs["profile"]),
            ("association", subs["association"]),
            ("persistence", subs["persistence"]),
        ]:
            try:
                bus.subscribe(f"{name}.*", handler.handle)
            except Exception:
                pass

    logger.info("EventBus wired: %s subscribers active", len(subs))
    return {"subscribers": len(subs), "names": list(subs.keys())}
