"""Shared domain models — re-exports from canonical locations.

Classes were scattered across v3/v4 during the merge to v6.
This module provides backward-compatible imports for tests.
"""
try:
    from core.agent.context.cross_domain_ir import IntentCategory
except ImportError:
    from enum import Enum
    class IntentCategory(str, Enum):  # fallback
        GENERAL = "general"
        TECHNICAL = "technical" 
        CREATIVE = "creative"
        ANALYTICAL = "analytical"

try:
    from core.agent.models_v3 import DependencyType, TaskStatus
except ImportError:
    from enum import Enum
    class DependencyType(Enum):  # fallback
        BLOCKS = "blocks"
        REQUIRES = "requires"
        RELATED = "related"
    class TaskStatus(Enum):  # fallback
        PENDING = "pending"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"

try:
    from core.agent.predictor.cognitive_profile import CognitiveProfile
except ImportError:
    from dataclasses import dataclass
    @dataclass
    class CognitiveProfile:  # fallback
        openness: float = 0.5
        conscientiousness: float = 0.5
        extraversion: float = 0.5
        agreeableness: float = 0.5
        neuroticism: float = 0.5
