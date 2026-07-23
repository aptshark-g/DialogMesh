"""Chain Trigger Conditions — Decider-gated execution.

Each chain has a `should_trigger(state, event_log)` predicate.
The engine calls this BEFORE running the chain.
If False, the chain is skipped for this tick.
"""

from core.agent.state.global_decider import EventType, StateSnapshot


def should_trigger_pcr(state: StateSnapshot, event_log: list) -> bool:
    """PCR always triggers — it's the entry point."""
    return True


def should_trigger_router(state: StateSnapshot, event_log: list) -> bool:
    """Router triggers after PCR, unless Meta recently flagged low confidence."""
    recent_meta = [e for e in event_log[-5:] if e.type == EventType.META_REVIEWED]
    if recent_meta:
        return True  # Meta may want to recalibrate — always allow
    return True


def should_trigger_intent(state: StateSnapshot, event_log: list) -> bool:
    """Intent triggers after Router, unless ATOMIC zone (skip parsing)."""
    recent_route = [e for e in event_log[-3:] if e.type == EventType.MESSAGE_RECEIVED]
    if recent_route and recent_route[-1].payload.get('zone') == 'ATOMIC':
        return False  # ATOMIC → skip intent parsing, go straight to LLM
    return True


def should_trigger_planner(state: StateSnapshot, event_log: list) -> bool:
    """Planner triggers only for PRECISION or ABYSS zones."""
    recent_route = [e for e in event_log[-3:] if e.type == EventType.MESSAGE_RECEIVED]
    if recent_route:
        zone = recent_route[-1].payload.get('zone', '')
        if zone in ('PRECISION', 'ABYSS'):
            return True
        return False  # ATOMIC/EXPLORE/PSYCHE/MIXED → skip planning
    return True


def should_trigger_context(state: StateSnapshot, event_log: list) -> bool:
    """Context always triggers — needed for LLM prompt."""
    return True


def should_trigger_llm(state: StateSnapshot, event_log: list) -> bool:
    """LLM always triggers — core path."""
    return True


def should_trigger_profile(state: StateSnapshot, event_log: list) -> bool:
    """Profile triggers every tick when trust is stable, 
    or when behavior shows significant pattern change."""
    recent_behavior = [e for e in event_log[-10:] if e.type == EventType.BEHAVIOR_RECORDED]
    if len(recent_behavior) >= 3:
        # Frequent behavior events → profile should update
        return True
    # Default: every tick when PCR has expectation
    recent_pcr = [e for e in event_log[-3:] if e.type == EventType.PCR_COMPUTED]
    return len(recent_pcr) > 0


def should_trigger_behavior(state: StateSnapshot, event_log: list) -> bool:
    """Behavior records every interaction."""
    return True


def should_trigger_abc(state: StateSnapshot, event_log: list) -> bool:
    """ABC evaluates every interaction when LLM response is available."""
    return True


def should_trigger_mind(state: StateSnapshot, event_log: list) -> bool:
    """Mind learns every interaction."""
    return True


def should_trigger_meta(state: StateSnapshot, event_log: list) -> bool:
    """Meta triggers only every 5 ticks, or when behavior pattern count is high."""
    if state.tick > 0 and state.tick % 5 == 0:
        return True
    if state.behavior_actions >= 3 and state.behavior_actions % 3 == 0:
        return True  # Pattern milestone → review
    return False


# ── Condition table ──
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
