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
                mc.retrospect(target=payload.get("category", kind))
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
        reply = payload.get("reply", "")
        if text and hasattr(ocean, 'analyze'):
            try:
                # API: analyze(engine, turn_text, llm_response)
                ocean.analyze(e, text, reply or text)
                self.events += 1
            except Exception:
                pass


class AssociationSubscriber:
    """Receives intent_parsed → L1 resolve (pronoun) + L2.5 belief ingest.

    Aligned with D-6: the L1 contract is PronounResolver.resolve(text)
    (not the legacy stanza-Document ModifierExtractor). BeliefAccumulator
    receives a proper Evidence dataclass, not a bare dict.

    Phase 6 (蓝图 §7.3): 关联链改为独立服务（M→1 定向通道 + EventLog），
    不再通过全广播订阅。此类保留仅供兼容引用，wire_subscribers 不再注册它。
    """
    def __init__(self, engine=None):
        self._engine = engine
        self.events = 0
        self._turn = 0

    def handle(self, kind: str, payload: dict):
        e = self._engine
        text = payload.get("text", "")
        if not text:
            return
        resolver = getattr(e, '_pronoun_resolver', None)
        l2 = getattr(e, '_l2_5_belief', None)
        results = {}
        if resolver and hasattr(resolver, 'resolve'):
            try:
                enriched = resolver.resolve(text)
                results["enriched"] = enriched != text
                results["entities"] = len(resolver.recent_entities())
            except Exception:
                pass
        if l2 and hasattr(l2, 'ingest'):
            try:
                from core.agent.association.l2_5_belief import Evidence
                self._turn += 1
                l2.ingest(Evidence(
                    entity_id=f"event:{kind}:{self._turn}",
                    entity_name=text[:32],
                    relation_type="co_occurrence",
                    confidence=0.5,
                    turn_num=self._turn,
                    source="event_subscriber",
                ))
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


def _trace_handle(name, handler, engine, kind, payload):
    """Wrap subscriber handle with auto-tracing."""
    from core.agent.event.tracer import PipelineTracer as _PT, MetricsCollector as _MC
    import time as _time
    start = _time.time()
    success = True
    try:
        handler(kind, payload)
    except Exception:
        success = False
    latency = (_time.time() - start) * 1000
    _MC.record(name, "success" if success else "error", latency)
    # Also record to engine's tracer if available
    tracer = getattr(engine, '_tracer', None)
    if tracer:
        tracer.record(name, kind, success, latency)

def wire_subscribers(engine) -> dict:
    """Create all subscribers, wrap with tracing, register with EventBus."""
    # Phase 6（蓝图 §7.3）: 关联链 = 独立服务，不做全广播订阅（防广播风暴）。
    # 关联链事件经 engine._publish 定向投递到 AssociationService。
    subs = {
        "discourse": DiscourseSubscriber(engine),
        "behavior": BehaviorSubscriber(engine),
        "meta": MetaSubscriber(engine),
        "profile": ProfileSubscriber(engine),
        "persistence": PersistenceSubscriber(engine),
    }

    # Wrap each handle with tracer for full-chain visibility
    for name, sub in subs.items():
        original = sub.handle
        def make_wrapped(orig, sname):
            def wrapped(kind, payload):
                import time as _t
                st = _t.time(); ok = True
                try: orig(kind, payload)
                except: ok = False
                lat = (_t.time() - st) * 1000
                try:
                    from core.agent.event.tracer import MetricsCollector
                    MetricsCollector.record(sname, "success" if ok else "error", lat)
                    if hasattr(engine, '_tracer') and engine._tracer:
                        engine._tracer.record(sname, kind, ok, lat)
                except: pass
            return wrapped
        sub.handle = make_wrapped(original, name)

    engine._event_subscribers = subs

    # Register with EventBus if available（G2-P6: 统一到 v2 总线，同步桥订阅）
    bus = getattr(engine, '_event_bus', None)
    if bus:
        # Wire each subscriber to their event pattern.
        # v2 EventBus 回调收到 Event(subject, data) —— 解包为 (kind, payload)。
        for name, handler in [
            ("discourse", subs["discourse"]),
            ("behavior", subs["behavior"]),
            ("meta", subs["meta"]),
            ("profile", subs["profile"]),
            ("persistence", subs["persistence"]),
        ]:
            try:
                sub = getattr(bus, "subscribe_sync", None)
                if sub is None:
                    continue
                sub(f"{name}.*",
                    lambda ev, h=handler: h.handle(ev.subject, ev.data or {}))
            except Exception:
                pass

    logger.info("EventBus wired: %s subscribers active", len(subs))
    return {"subscribers": len(subs), "names": list(subs.keys())}
