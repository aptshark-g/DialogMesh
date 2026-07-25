"""DialogMesh v6 Bootstrap — wire all modules into AgentOrchestrator.

10-chain pipeline: Compass → PCR → DualTrack → L4 → Behavior → Context → Engineering → LLM
Cold path: EventLog → MetaSubscriber → FeedbackBridge → Cold→Hot feedback

Usage:
    orch = bootstrap()
    result = orch.process("user input")
"""

from __future__ import annotations
from typing import Optional
import logging
import os

logger = logging.getLogger(__name__)


def bootstrap(pcr_router=None, intent_pipeline=None, l4_engine=None,
              behavior_collab=None, engineering_chain=None,
              llm=None, discourse_tree=None, event_log_db=None) -> "AgentOrchestrator":
    """Create and wire a complete AgentOrchestrator.

    All parameters optional — missing modules gracefully degrade.
    LLM auto-detects DeepSeek key if available.

    Usage:
        orch = bootstrap()                  # auto-detect everything
        orch = bootstrap(llm=my_provider)    # custom LLM
        result = orch.process("user input")
    """
    from core.agent.orchestrator.agent_native import AgentOrchestrator

    # ═══ LLM auto-detect ═══
    llm = llm or _auto_detect_llm()

    # ═══ EventLog (cold path) ═══
    event_log = None
    if event_log_db is None:
        event_log_db = os.path.join("data", "event_log.db")
    try:
        from core.agent.api.api_event_log import EventLog
        os.makedirs(os.path.dirname(event_log_db) or "data", exist_ok=True)
        event_log = EventLog(event_log_db)
        event_log.open()
        logger.info("EventLog ready: %s", event_log_db)
    except Exception as e:
        logger.warning("EventLog unavailable: %s", e)

    # ═══ Context (unified) ═══
    context_assembly = _load_unified_context()

    # ═══ Cognition Hub ═══
    cognition_hub = _load_cognition_hub()

    # ═══ Feedback Bridge (cold→hot) ═══
    feedback_bridge = _load_feedback_bridge()

    # ═══ Compass (multi-lens) ═══
    compass = _load_compass()

    # ═══ Cognitive Bridge (v4) ═══
    cognitive_bridge = _load_cognitive_bridge()

    # ═══ Wire everything ═══
    orch = AgentOrchestrator(
        pcr_router=pcr_router,
        intent_splitter=intent_pipeline,
        l4_engine=l4_engine,
        behavior_collab=behavior_collab,
        engineering_chain=engineering_chain,
        llm=llm,
        discourse_tree=discourse_tree,
        cognitive_bridge=cognitive_bridge,
        event_log=event_log,
        context_assembly=context_assembly,
        cognition_hub=cognition_hub,
        feedback_bridge=feedback_bridge,
        compass_selector=compass,
    )

    logger.info("DialogMesh v6 bootstrap complete")
    _log_module_status(orch)
    return orch


def _load_unified_context():
    try:
        from core.agent.assembly.unified_context import UnifiedContext
        return UnifiedContext()
    except Exception as e:
        logger.debug("UnifiedContext: %s", e)
        return None


def _load_cognition_hub():
    try:
        from core.agent.cognition.hub import CognitionHub
        return CognitionHub()
    except Exception as e:
        logger.debug("CognitionHub: %s", e)
        return None


def _load_feedback_bridge():
    try:
        from core.agent.meta.feedback_bridge import FeedbackBridge
        return FeedbackBridge()
    except Exception as e:
        logger.debug("FeedbackBridge: %s", e)
        return None


def _load_compass():
    try:
        from core.agent.perception.compass import create_default_compass
        return create_default_compass()
    except Exception as e:
        logger.debug("Compass: %s", e)
        return None


def _load_cognitive_bridge():
    try:
        from core.agent.v4.cognitive_bridge import V4CognitiveBridge
        return V4CognitiveBridge()
    except Exception as e:
        logger.debug("V4CognitiveBridge: %s", e)
        return None


def _auto_detect_llm():
    """Auto-detect available LLM: check env key first, then quick connectivity."""
    import os
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        logger.info("LLM: none (set DEEPSEEK_API_KEY for DeepSeek)")
        return None
    try:
        from core.agent.llm_providers.deepseek_direct import DeepSeekProvider
        llm = DeepSeekProvider(api_key=api_key)
        logger.info("LLM: DeepSeek (%s)", llm.model)
        return llm
    except Exception as e:
        logger.debug("DeepSeek: %s", e)
    return None


def _log_module_status(orch):
    statuses = []
    if orch._compass: statuses.append("Compass")
    if orch.pcr: statuses.append("PCR")
    if orch.intent: statuses.append("Intent")
    if orch.l4: statuses.append("L4")
    if orch._context_assembly: statuses.append("Context")
    if orch.llm: statuses.append("LLM")
    if orch._event_log: statuses.append("EventLog")
    if orch._cognition_hub: statuses.append("Cognition")
    if orch._feedback_bridge: statuses.append("Feedback")
    logger.info("Loaded: %s", ", ".join(statuses))
    if not orch.llm:
        logger.info("(LLM not connected — pipeline runs in structural mode)")


# ═══ Quick test ═══

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    orch = bootstrap()
    r = orch.process("先定位延迟，然后修复它")
    print(f"\nPipeline OK — latency: {r.get('latency_ms')}ms")
    print(f"Keys: {list(r.keys())}")
