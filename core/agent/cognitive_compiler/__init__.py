# -*- coding: utf-8 -*-
"""
core/agent/cognitive_compiler/__init__.py
───────────────────────────────────────
Cognitive compiler exports.
"""

from core.agent.cognitive_compiler.compiler import CognitiveCompiler, CompileInput
CompiledInput = CompileInput  # backward compat — class renamed
from core.agent.cognitive_compiler.decomposer import (
    CompilerMode, SyntacticDecomposer, ParsedClause,
)
from core.agent.cognitive_compiler.injector import HeaderInjector
from core.agent.cognitive_compiler.scorer import CohesionScorer
from core.agent.cognitive_compiler.dual_manager import DualStructureManager, TimelineEvent
from core.agent.cognitive_compiler.entity_cache import EntityCache

__all__ = [
    "CognitiveCompiler",
    "CompiledInput",
    "CompilerMode",
    "SyntacticDecomposer",
    "ParsedClause",
    "HeaderInjector",
    "CohesionScorer",
    "DualStructureManager",
    "TimelineEvent",
    "EntityCache",
]
