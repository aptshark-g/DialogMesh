# -*- coding: utf-8 -*-
"""
service/models.py
─────────────────
Service layer data models for DialogMesh.

All models are ``@dataclass``-based with JSON serialization support
(``to_dict()`` / ``from_dict()``).

Design notes:
  - ``Session.to_persistent_dict()`` excludes ``ws_connections`` (memory-only).
  - ``CognitiveProfile`` and ``AdaptiveThresholds`` are first-class dataclasses
    rather than raw dicts for type safety.
  - ``version`` on ``Session`` enables optimistic locking in the store layer.
"""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Cognitive & Adaptive Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CognitiveProfile:
    """Layer-1 cognitive portrait derived from PCR analysis."""

    metacognition: float = 0.0
    divergence: float = 0.0
    tracking_depth: float = 0.0
    stability: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metacognition": self.metacognition,
            "divergence": self.divergence,
            "tracking_depth": self.tracking_depth,
            "stability": self.stability,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CognitiveProfile":
        return cls(
            metacognition=d.get("metacognition", 0.0),
            divergence=d.get("divergence", 0.0),
            tracking_depth=d.get("tracking_depth", 0.0),
            stability=d.get("stability", 0.0),
            confidence=d.get("confidence", 0.0),
        )


@dataclass
class AdaptiveThresholds:
    """Adaptive thresholds that regulate parser behavior based on feedback."""

    noise_threshold: float = 0.30
    complexity_threshold: float = 0.50
    confidence_threshold: float = 0.40
    noise_fast_path: float = 0.30

    def feedback(self, required_clarification: bool = False) -> None:
        """
        Adjust thresholds based on whether a clarification was required.

        Args:
            required_clarification: ``True`` if the last turn required user
                clarification (becomes more conservative); ``False`` on
                successful resolution (becomes slightly more aggressive).
        """
        if required_clarification:
            # Too aggressive → lower thresholds (more conservative)
            self.noise_threshold = max(0.1, self.noise_threshold * 0.95)
            self.noise_fast_path = max(0.1, self.noise_fast_path * 0.95)
            self.complexity_threshold = max(0.2, self.complexity_threshold * 0.95)
            self.confidence_threshold = min(0.9, self.confidence_threshold * 1.05)
        else:
            # Success → can afford slightly higher thresholds
            self.noise_threshold = min(0.5, self.noise_threshold * 1.02)
            self.noise_fast_path = min(0.5, self.noise_fast_path * 1.02)
            self.complexity_threshold = min(0.8, self.complexity_threshold * 1.02)
            self.confidence_threshold = max(0.2, self.confidence_threshold * 0.98)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "noise_threshold": self.noise_threshold,
            "complexity_threshold": self.complexity_threshold,
            "confidence_threshold": self.confidence_threshold,
            "noise_fast_path": self.noise_fast_path,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AdaptiveThresholds":
        return cls(
            noise_threshold=d.get("noise_threshold", 0.30),
            complexity_threshold=d.get("complexity_threshold", 0.50),
            confidence_threshold=d.get("confidence_threshold", 0.40),
            noise_fast_path=d.get("noise_fast_path", 0.30),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Turn & Session Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TurnRecord:
    """Single turn record in a conversation."""

    sequence: int
    timestamp: float
    role: str = "user"
    content: str = ""
    modality: str = "text"
    intent_result: Optional[Dict[str, Any]] = None
    clarification: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    pcr_latency_ms: float = 0.0
    parser_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TurnRecord":
        return cls(
            sequence=d["sequence"],
            timestamp=d["timestamp"],
            role=d.get("role", "user"),
            content=d.get("content", ""),
            modality=d.get("modality", "text"),
            intent_result=d.get("intent_result"),
            clarification=d.get("clarification"),
            latency_ms=d.get("latency_ms", 0.0),
            pcr_latency_ms=d.get("pcr_latency_ms", 0.0),
            parser_latency_ms=d.get("parser_latency_ms", 0.0),
        )


@dataclass
class Session:
    """User session with full context for the DialogMesh engine."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    tenant_id: str = "default"
    user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 3600)
    state: str = "active"  # active | idle | clarifying | closed | expired
    parse_context: Optional[Dict[str, Any]] = None
    cognitive_profile: Optional[CognitiveProfile] = None
    turn_count: int = 0
    history: List[TurnRecord] = field(default_factory=list)
    pending_clarification: Optional[str] = None
    ws_connections: List[str] = field(default_factory=list)
    version: int = 1
    adaptive_thresholds: Optional[AdaptiveThresholds] = None

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity_at = time.time()

    def to_persistent_dict(self) -> Dict[str, Any]:
        """Serialize to persistent format (excludes ``ws_connections``)."""
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "expires_at": self.expires_at,
            "state": self.state,
            "parse_context": self.parse_context,
            "cognitive_profile": (
                self.cognitive_profile.to_dict() if self.cognitive_profile else None
            ),
            "turn_count": self.turn_count,
            "history": [t.to_dict() for t in self.history],
            "pending_clarification": self.pending_clarification,
            "version": self.version,
            "adaptive_thresholds": (
                self.adaptive_thresholds.to_dict() if self.adaptive_thresholds else None
            ),
        }

    @classmethod
    def from_persistent_dict(cls, data: Dict[str, Any]) -> "Session":
        """Restore from persistent format."""
        cog_data = data.get("cognitive_profile")
        at_data = data.get("adaptive_thresholds")
        sess = cls(
            session_id=data["session_id"],
            tenant_id=data.get("tenant_id", "default"),
            user_id=data.get("user_id"),
            created_at=data.get("created_at", time.time()),
            last_activity_at=data.get("last_activity_at", time.time()),
            expires_at=data.get("expires_at", time.time() + 3600),
            state=data.get("state", "active"),
            parse_context=data.get("parse_context"),
            cognitive_profile=(
                CognitiveProfile.from_dict(cog_data) if cog_data else None
            ),
            turn_count=data.get("turn_count", 0),
            pending_clarification=data.get("pending_clarification"),
            version=data.get("version", 1),
            adaptive_thresholds=(
                AdaptiveThresholds.from_dict(at_data) if at_data else None
            ),
        )
        for t_data in data.get("history", []):
            sess.history.append(TurnRecord.from_dict(t_data))
        return sess

    def to_dict(self) -> Dict[str, Any]:
        """Full serialization including transient fields."""
        d = self.to_persistent_dict()
        d["ws_connections"] = self.ws_connections
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Session":
        """Restore from full serialization."""
        return cls.from_persistent_dict(d)


@dataclass
class SessionSummary:
    """Lightweight summary of a session for listing and monitoring."""

    session_id: str
    last_active: float
    turn_count: int
    state: str
    health_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionSummary":
        return cls(
            session_id=d["session_id"],
            last_active=d.get("last_active", 0.0),
            turn_count=d.get("turn_count", 0),
            state=d.get("state", ""),
            health_score=d.get("health_score", 0.0),
        )


@dataclass
class UserProfile:
    """Persistent user profile across sessions."""

    user_id: str
    tenant_id: str = "default"
    profile: Dict[str, Any] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UserProfile":
        return cls(
            user_id=d["user_id"],
            tenant_id=d.get("tenant_id", "default"),
            profile=d.get("profile", {}),
            preferences=d.get("preferences", {}),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
        )
