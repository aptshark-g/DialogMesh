"""Chain Trigger Conditions — data-driven via zone_strategy. No hardcoded zone names."""

from core.agent.router.zone_strategy import should_skip_chain, get_zone_config
from core.agent.state.global_decider import StateSnapshot


def should_trigger_pcr(state: StateSnapshot, event_log: list) -> bool:
    return True


def should_trigger_router(state: StateSnapshot, event_log: list) -> bool:
    return True


def should_trigger_intent(state: StateSnapshot, event_log: list) -> bool:
    zone = _get_active_zone(event_log)
    return not should_skip_chain(zone, "intent")


def should_trigger_planner(state: StateSnapshot, event_log: list) -> bool:
    zone = _get_active_zone(event_log)
    return not should_skip_chain(zone, "planning")


def should_trigger_profile(state: StateSnapshot, event_log: list) -> bool:
    zone = _get_active_zone(event_log)
    if should_skip_chain(zone, "profile"):
        return False
    # Also trigger on behavior burst (Learn from user patterns)
    recent_behavior = [e for e in event_log[-10:] if e.type.value == "behavior_recorded"]
    return len(recent_behavior) >= 3 or True


def should_trigger_context(state: StateSnapshot, event_log: list) -> bool:
    return True


def should_trigger_llm(state: StateSnapshot, event_log: list) -> bool:
    return True


def should_trigger_behavior(state: StateSnapshot, event_log: list) -> bool:
    return True


def should_trigger_abc(state: StateSnapshot, event_log: list) -> bool:
    return True


def should_trigger_mind(state: StateSnapshot, event_log: list) -> bool:
    return True


def should_trigger_meta(state: StateSnapshot, event_log: list) -> bool:
    if state.tick > 0 and state.tick % 5 == 0:
        return True
    if state.behavior_actions >= 3 and state.behavior_actions % 3 == 0:
        return True
    return False


def _get_active_zone(event_log: list) -> str:
    """Extract current zone from event log."""
    for e in reversed(event_log):
        payload = getattr(e, 'payload', {})
        if isinstance(payload, dict) and 'zone' in payload:
            return payload['zone']
    return "MIXED"


TRIGGER_CONDITIONS = {
    "pcr": should_trigger_pcr,
    "routing": should_trigger_router,
    "intent": should_trigger_intent,
    "planning": should_trigger_planner,
    "context": should_trigger_context,
    "llm": should_trigger_llm,
    "profile": should_trigger_profile,
    "behavior": should_trigger_behavior,
    "abc": should_trigger_abc,
    "mind": should_trigger_mind,
    "meta": should_trigger_meta,
}
