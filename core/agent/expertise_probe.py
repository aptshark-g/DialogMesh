"""Expertise probe — archived to un_use/. Re-export for backward compat."""
try:
    from core.agent.predictor.cognitive_profile import CognitiveProfile
except ImportError:
    CognitiveProfile = None
