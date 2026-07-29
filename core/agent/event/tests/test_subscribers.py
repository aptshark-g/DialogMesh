"""Tests for EventBus subscribers (Phase 1)."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from core.agent.event.subscribers import (
    DiscourseSubscriber, BehaviorSubscriber, MetaSubscriber,
    ProfileSubscriber, AssociationSubscriber, PersistenceSubscriber,
    wire_subscribers,
)


class MockEngine:
    """Simulates engine attributes for subscriber testing."""
    def __init__(self):
        self._discourse_tree = None
        self._behavior_graph = None
        self._meta_cognition = None
        self._ocean_analyst = None
        self._l1_modifier = None
        self._l2_5_belief = None
        self._event_bus = DummyEventBus()
        self._event_subscribers = {}


class DummyEventBus:
    def publish(self, kind, payload):
        pass


class DummyMeta:
    def retrospect(self): return True
    def process_queue(self): return []


class DummyOcean:
    def analyze(self, session_id=""): return {}
    def analyze_with_bfi_override(self, text): return {}


class DummyL1:
    def extract(self, text): return [{"type": "mod"}]


class DummyL2:
    def ingest(self, data): return True


def test_discourse_subscriber():
    s = DiscourseSubscriber()
    assert s.events == 0
    assert hasattr(s, 'handle')


def test_behavior_subscriber():
    e = MockEngine()
    class DummyBG:
        def load(self): pass
    e._behavior_graph = DummyBG()
    s = BehaviorSubscriber(e)
    s.handle("user_message", {"text": "test"})
    assert s.events == 1


def test_meta_subscriber():
    e = MockEngine()
    e._meta_cognition = DummyMeta()
    s = MetaSubscriber(e)
    s.handle("intent_parsed", {"category": "test"})
    assert s.events == 1


def test_profile_subscriber():
    e = MockEngine()
    e._ocean_analyst = DummyOcean()
    s = ProfileSubscriber(e)
    s.handle("user_message", {"text": "test", "session_id": "s1"})
    assert s.events == 1


def test_association_subscriber():
    e = MockEngine()
    e._l1_modifier = DummyL1()
    e._l2_5_belief = DummyL2()
    s = AssociationSubscriber(e)
    s.handle("intent_parsed", {"text": "test message"})
    assert s.events == 1


def test_persistence_subscriber():
    e = MockEngine()
    e._persist_state_count = 0
    def persist():
        e._persist_state_count += 1
    e._persist_state = persist
    s = PersistenceSubscriber(e)
    s._last_persist = 0  # reset debounce
    s.handle("any", {"data": "test"})
    assert s.events == 1
    assert e._persist_state_count == 1


def test_persistence_debounce():
    e = MockEngine()
    e._persist_state_count = 0
    def persist():
        e._persist_state_count += 1
    e._persist_state = persist
    s = PersistenceSubscriber(e)
    s.handle("a", {})
    s.handle("b", {})  # should be debounced (5s window)
    assert s.events == 1  # only first fires
    assert e._persist_state_count == 1


def test_wire_all_subscribers():
    e = MockEngine()
    e._discourse_tree = object()
    e._behavior_graph = DummyBG()
    e._meta_cognition = DummyMeta()
    e._ocean_analyst = DummyOcean()
    e._l1_modifier = DummyL1()
    e._l2_5_belief = DummyL2()
    
    stats = wire_subscribers(e)
    assert stats["subscribers"] == 6
    assert len(e._event_subscribers) == 6


class DummyBG:
    def load(self): pass
