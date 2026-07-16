"""ProjectionResolver — dynamic content generation per world.

Design: docs/v3.0/DESIGN_SEMANTIC_OBJECT.md §3

Resolvers don't cache content. They delegate to ContentProvider.
DesignResolver is the only complete implementation in Phase A.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Optional


class ProjectionResolver(ABC):
    """Generates content for one world-view of a SemanticObject.

    Does not cache. Does not know storage. Delegates to ContentProvider.
    """
    name: str = ""

    @abstractmethod
    def resolve(self, target, view: str, provider) -> str:
        """Generate projection content.

        target: SemanticObject
        view: "summary" | "definition" | "detail" | "history" | "full"
        provider: ContentProvider
        """
        ...


class DesignResolver(ProjectionResolver):
    """Design document projection — the only complete resolver in Phase A."""

    name = "DesignResolver"

    def resolve(self, target, view: str, provider) -> str:
        path = target.semantic_path
        if not path:
            return ""

        if view == "summary":
            return provider.query_design(path, limit=1, max_chars=200)
        elif view == "definition":
            return provider.query_design(path, pattern="definition", limit=2, max_chars=600)
        elif view == "history":
            return provider.query_design(path, pattern="evolution", limit=3, max_chars=800)
        else:  # detail / full
            return provider.query_design(path, limit=5, max_chars=1200)


class CodeResolver(ProjectionResolver):
    """Code projection (stub)."""
    name = "CodeResolver"

    def resolve(self, target, view: str, provider) -> str:
        return provider.code_lookup(target.name)


class KnowledgeResolver(ProjectionResolver):
    """Knowledge projection (stub)."""
    name = "KnowledgeResolver"

    def resolve(self, target, view: str, provider) -> str:
        return provider.knowledge_lookup(target.name)


class ConversationResolver(ProjectionResolver):
    """Conversation projection (stub)."""
    name = "ConversationResolver"

    def resolve(self, target, view: str, provider) -> str:
        return provider.conversation_lookup(target.name)


class SkillResolver(ProjectionResolver):
    """Skill projection (stub)."""
    name = "SkillResolver"

    def resolve(self, target, view: str, provider) -> str:
        return provider.skill_lookup(target.name)


class CausalResolver(ProjectionResolver):
    """Causal projection: high-confidence edges with mechanism.

    Design: DESIGN_RELATION_SUBSTRATE.md §4.2
    """
    name = "CausalResolver"

    def resolve(self, target, view: str, provider) -> str:
        edges = provider.relation_query(
            source=target.identity, min_confidence=0.5)

        # causal = edges that HAVE a mechanism explanation
        causal = [e for e in edges if hasattr(e, 'mechanism') and e.mechanism]

        if not causal:
            structural = [e for e in edges if hasattr(e, 'relation_kind')
                          and e.relation_kind == "structural"][:3]
            if structural:
                parts = [f"{target.name} {e.predicate} {e.target}"
                         for e in structural]
                return " | ".join(parts)
            return ""

        if view == "summary":
            best = causal[0]
            return (f"{target.name} {best.predicate} {best.target}: "
                    f"{best.mechanism[:200]}")
        else:
            parts = []
            for e in causal[:3]:
                parts.append(
                    f"{target.name} {e.predicate} {e.target}\n"
                    f"  why: {e.mechanism}\n"
                    f"  confidence: {e.confidence:.2f}"
                )
            return "\n".join(parts)


class BehaviorResolver(ProjectionResolver):
    """Behavior projection: behavioral edges from user navigation.

    Design: DESIGN_RELATION_SUBSTRATE.md §4.2
    """
    name = "BehaviorResolver"

    def resolve(self, target, view: str, provider) -> str:
        edges = provider.relation_query(
            source=target.identity,
            relation_kind="behavioral",
            min_confidence=0.1)

        if not edges:
            return ""

        after = [e for e in edges if hasattr(e, 'predicate')
                 and e.predicate == "navigated_to"]
        before_edges = provider.relation_query(
            target=target.identity,
            relation_kind="behavioral",
            min_confidence=0.1)
        before = [e.source for e in before_edges[:3]]

        parts = []
        if before:
            parts.append(f"users often arrive from: {', '.join(before)}")
        if after:
            parts.append(f"users often continue to: {', '.join(e.target for e in after[:3])}")
        return " | ".join(parts) if parts else ""


class ImplementationResolver(ProjectionResolver):
    """Implementation projection (stub)."""
    name = "ImplementationResolver"

    def resolve(self, target, view: str, provider) -> str:
        return provider.code_lookup(target.name)


# ---- Registry ----

class ResolverRegistry:
    """Global registry of ProjectionResolvers."""

    _registry: Dict[str, ProjectionResolver] = {}

    @classmethod
    def register(cls, resolver: ProjectionResolver):
        cls._registry[resolver.name] = resolver

    @classmethod
    def get(cls, name: str) -> Optional[ProjectionResolver]:
        return cls._registry.get(name)

    @classmethod
    def init_defaults(cls):
        """Register all built-in resolvers."""
        for r in [DesignResolver(), CodeResolver(), KnowledgeResolver(),
                  ConversationResolver(), SkillResolver(),
                  CausalResolver(), BehaviorResolver(), ImplementationResolver()]:
            cls.register(r)


# Init defaults on import
ResolverRegistry.init_defaults()
