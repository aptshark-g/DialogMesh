# -*- coding: utf-8 -*-
"""
core/agent/pcr/datacontract.py
────────────────────────────
Versioned data contracts for the Pre-Cognitive Router (PCR).

All dataclasses are frozen (immutable) and have no dependency on MemoryGraph
business objects. They can be serialized to/from JSON and are suitable for
IPC, testing, and cross-process communication.

Versioning strategy:
    - PCRVersion enum tracks contract versions.
    - New versions add new fields with defaults; old fields are never removed.
    - validate() checks structural constraints, not semantic correctness.
"""

from __future__ import annotations

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# Versioning
# ═══════════════════════════════════════════════════════════════════════════════

class PCRVersion(Enum):
    """Data contract version. Add new versions when fields change; never remove old ones."""
    V1 = "1.0"

    @classmethod
    def current(cls) -> str:
        """Return the current version string."""
        return cls.V1.value

    @classmethod
    def is_compatible(cls, a: str, b: str) -> bool:
        """Check if two version strings are compatible (exact match for now)."""
        return a == b

    @classmethod
    def validate(cls, version: str) -> None:
        """Validate a version string. Raises ValueError if invalid."""
        valid = {v.value for v in cls}
        if version not in valid:
            raise ValueError(f"Invalid PCR version: {version}. Valid: {valid}")


class Modality(Enum):
    """输入模态。支持未来多模态扩展，当前文本路径为默认。"""
    TEXT = "text"               # 纯文本（当前唯一生产路径）
    STRUCTURED = "structured"   # 结构化 JSON / 快捷指令
    IMAGE = "image"             # 图片（OCR 前）
    AUDIO = "audio"             # 语音（ASR 前）
    MULTIMODAL = "multimodal"   # 混合输入


# ═══════════════════════════════════════════════════════════════════════════════
# History Entry (shared sub-structure)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class HistoryEntry:
    """A single turn in the conversation history."""
    role: str = ""          # "user" | "assistant" | "system" | "tool"
    content: str = ""       # Raw text content of this turn
    expectation: str = ""  # Inferred expectation for this turn (optional, for PCR tracking)
    timestamp: float = 0.0  # 新增：时间戳（用于工作记忆衰减计算）
    metadata: Dict[str, Any] = field(default_factory=dict)  # Turn-level metadata (model, etc.)

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "content": self.content, "expectation": self.expectation, "timestamp": self.timestamp, "metadata": self.metadata}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HistoryEntry":
        return cls(
            role=d.get("role", ""),
            content=d.get("content", ""),
            expectation=d.get("expectation", ""),
            timestamp=float(d.get("timestamp", 0.0)),
            metadata=d.get("metadata", {}),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Input Contract
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PCRInput_v1:
    """
    PCR input contract v1.1 — 多模态扩展版。
    
    Minimal, serializable, zero coupling to business objects.
    新增字段：modality, raw_payload, timestamp（默认向后兼容 v1.0）
    """
    version: str = PCRVersion.V1.value
    modality: Modality = Modality.TEXT          # 输入模态，默认纯文本
    query: str = ""                              # 当前用户输入（已预处理，文本模态）
    raw_payload: Optional[Dict[str, Any]] = None  # 非文本模态：原始负载（图片/音频/结构化数据）
    session_id: str = ""                         # 会话标识
    turn_index: int = 0                          # 当前轮次（用于追踪深度计算）
    session_history: List[HistoryEntry] = field(default_factory=list)  # 最近 N 轮结构化历史
    process_context: Optional[Dict[str, Any]] = None   # 进程上下文（pid, name, modules, type）
    user_preferences: Dict[str, Any] = field(default_factory=dict)  # 用户持久偏好
    metadata: Dict[str, Any] = field(default_factory=dict)  # 扩展字段（版本兼容用）
    timestamp: float = field(default_factory=time.time)  # 新增：输入时间戳（工作记忆衰减计算）

    def __post_init__(self):
        if isinstance(self.modality, str):
            object.__setattr__(self, 'modality', Modality(self.modality))
        if self.query is None:
            raise ValueError("query cannot be None")
        if not isinstance(self.query, str):
            raise TypeError(f"query must be a string, got {type(self.query).__name__}")
        if not isinstance(self.session_id, str):
            raise TypeError(f"session_id must be a string, got {type(self.session_id).__name__}")
        if not isinstance(self.turn_index, int) or self.turn_index < 0:
            raise ValueError(f"turn_index must be a non-negative integer, got {self.turn_index}")

    def validate(self) -> Tuple[bool, Optional[str]]:
        """Structural validation. Returns (is_valid, error_message)."""
        if self.modality == Modality.TEXT:
            if not self.query or not isinstance(self.query, str):
                return False, "query must be non-empty string for TEXT modality"
        if self.query and len(self.query) > 10000:
            return False, f"query length must be 0–10000, got {len(self.query)}"
        if self.process_context is not None and not isinstance(self.process_context, dict):
            return False, "process_context must be a dict or None"
        if not isinstance(self.turn_index, int) or self.turn_index < 0:
            return False, "turn_index must be non-negative"
        return True, None

    def is_text_modality(self) -> bool:
        """判断是否为文本模态（TEXT 或 STRUCTURED）。"""
        return self.modality in (Modality.TEXT, Modality.STRUCTURED)

    def is_preprocessing_required(self) -> bool:
        """判断是否需要外部预处理（IMAGE / AUDIO / MULTIMODAL）。"""
        return self.modality in (Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to plain dict (JSON-compatible)."""
        return {
            "version": self.version,
            "modality": self.modality.value,
            "query": self.query,
            "raw_payload": self.raw_payload,
            "session_id": self.session_id,
            "turn_index": self.turn_index,
            "session_history": [h.to_dict() for h in self.session_history],
            "process_context": self.process_context,
            "user_preferences": self.user_preferences,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PCRInput_v1":
        """Deserialize from plain dict. Extra fields go into metadata."""
        known = {"version", "modality", "query", "raw_payload", "session_id", "turn_index",
                 "session_history", "process_context", "user_preferences", "metadata", "timestamp"}
        extra = {k: v for k, v in d.items() if k not in known}
        metadata = dict(d.get("metadata", {}))
        metadata.update(extra)
        # Convert modality string to enum
        raw_modality = d.get("modality", "text")
        modality = Modality(raw_modality) if isinstance(raw_modality, str) else raw_modality
        # Convert session_history dicts to HistoryEntry objects
        raw_history = d.get("session_history", [])
        history = []
        if isinstance(raw_history, list):
            for item in raw_history:
                if isinstance(item, dict):
                    history.append(HistoryEntry.from_dict(item))
                elif isinstance(item, HistoryEntry):
                    history.append(item)
        return cls(
            version=d.get("version", PCRVersion.V1.value),
            modality=modality,
            query=d.get("query", ""),
            raw_payload=d.get("raw_payload"),
            session_id=d.get("session_id", ""),
            turn_index=d.get("turn_index", 0),
            session_history=history,
            process_context=d.get("process_context"),
            user_preferences=d.get("user_preferences", {}),
            metadata=metadata,
            timestamp=float(d.get("timestamp", 0.0)) or time.time(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Cognitive Profile (output sub-structure)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CognitiveProfile_v1:
    """
    Cognitive profile output v1.0.
    
    Four dimensions (0–1 continuous) plus an overall confidence score.
    """
    metacognition: float = 0.0       # 0–1: awareness of knowledge boundaries
    divergence: float = 0.0          # 0–1: 0=convergent (imperative), 1=divergent (exploratory)
    tracking_depth: float = 0.0      # 0–1: sustained attention on same topic
    stability: float = 0.0           # 0–1: lexical / intent consistency across turns
    confidence: float = 0.0            # 0–1: overall reliability of the profile

    @property
    def metacognitive_level(self) -> float:
        return self.metacognition

    @property
    def divergence_ratio(self) -> float:
        return self.divergence

    @property
    def description_stability(self) -> float:
        return self.stability

    def __post_init__(self):
        for name, value in [
            ("metacognition", self.metacognition),
            ("divergence", self.divergence),
            ("stability", self.stability),
            ("confidence", self.confidence),
        ]:
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric, got {type(value).__name__}")
            if not (0.0 <= float(value) <= 1.0):
                raise ValueError(f"{name} must be in [0.0, 1.0], got {value}")
        # tracking_depth is a counter (>=0), not bounded to 1.0
        if not isinstance(self.tracking_depth, (int, float)):
            raise TypeError(f"tracking_depth must be numeric, got {type(self.tracking_depth).__name__}")
        if self.tracking_depth < 0:
            raise ValueError(f"tracking_depth must be >= 0, got {self.tracking_depth}")

    def is_reliable(self) -> bool:
        """Profile is considered reliable if overall confidence >= 0.6."""
        return self.confidence >= 0.6

    def validate(self) -> Tuple[bool, Optional[str]]:
        for name, value in [
            ("metacognition", self.metacognition),
            ("divergence", self.divergence),
            ("tracking_depth", self.tracking_depth),
            ("stability", self.stability),
            ("confidence", self.confidence),
        ]:
            if not isinstance(value, (int, float)):
                return False, f"{name} must be numeric, got {type(value).__name__}"
            if not (0.0 <= float(value) <= 1.0):
                return False, f"{name} must be in [0.0, 1.0], got {value}"
        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metacognition": self.metacognition,
            "divergence": self.divergence,
            "tracking_depth": self.tracking_depth,
            "stability": self.stability,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CognitiveProfile_v1":
        return cls(
            metacognition=float(d.get("metacognition", 0.0)),
            divergence=float(d.get("divergence", 0.0)),
            tracking_depth=float(d.get("tracking_depth", 0.0)),
            stability=float(d.get("stability", 0.0)),
            confidence=float(d.get("confidence", 0.0)),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Output Contract
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PCROutput_v1:
    """
    PCR output contract v1.0.
    
    Contains the full cognitive state + derived execution strategies.
    Downstream layers consume this directly without re-computation.
    """
    version: str = PCRVersion.V1.value

    # ── Core evaluation results ──
    expectation: str = "UNKNOWN"            # TOOL / ADVISOR / COMPANION / UNKNOWN
    noise_level: float = 0.0                # 0–1
    complexity_level: float = 0.0           # 0–1
    cognitive_profile: CognitiveProfile_v1 = field(default_factory=CognitiveProfile_v1)

    # ── Derived execution strategies ──
    execution_mode: str = "BALANCED"        # FAST_EXECUTE / CLARIFICATION / DEEP_RESEARCH / CONVERSATIONAL / BALANCED
    parser_config_overrides: Dict[str, Any] = field(default_factory=dict)  # Direct overrides for ParserConfig
    prompt_style: str = "BALANCED"          # BRIEF / EXPLANATORY / TUTORIAL / BALANCED
    ambiguity_strategy: str = "BALANCED"    # AGGRESSIVE_AUTO / CONSERVATIVE_ASK / BALANCED

    # ── Session-level suggestions ──
    suggested_next_actions: List[str] = field(default_factory=list)  # Frontend can render as buttons
    should_attach_process: bool = False       # Hint to frontend: user needs to attach a process
    should_refresh_analysis: bool = False     # Hint to auto-refresh process analysis

    # ── Telemetry & provenance ──
    trace_log: List[str] = field(default_factory=list)
    latency_ms: float = 0.0                   # Evaluation latency in milliseconds
    implementation: str = ""                  # Which PCR implementation produced this output
    cache_hit: bool = False                   # Whether this came from cache

    # ── Fallback markers ──
    is_fallback: bool = False                 # True if this was produced by fallback logic
    fallback_reason: Optional[str] = None     # Reason for fallback (if any)

    # ── Validation ──

    def __post_init__(self):
        if not isinstance(self.noise_level, (int, float)):
            raise TypeError(f"noise_level must be numeric, got {type(self.noise_level).__name__}")
        if not (0.0 <= self.noise_level <= 1.0):
            raise ValueError(f"noise_level must be in [0.0, 1.0], got {self.noise_level}")
        if not isinstance(self.complexity_level, (int, float)):
            raise TypeError(f"complexity_level must be numeric, got {type(self.complexity_level).__name__}")
        if not (0.0 <= self.complexity_level <= 1.0):
            raise ValueError(f"complexity_level must be in [0.0, 1.0], got {self.complexity_level}")

    def validate(self) -> Tuple[bool, Optional[str]]:
        if not (0.0 <= self.noise_level <= 1.0):
            return False, f"noise_level must be in [0.0, 1.0], got {self.noise_level}"
        if not (0.0 <= self.complexity_level <= 1.0):
            return False, f"complexity_level must be in [0.0, 1.0], got {self.complexity_level}"
        if self.expectation not in {"TOOL", "ADVISOR", "COMPANION", "UNKNOWN"}:
            return False, f"expectation must be TOOL/ADVISOR/COMPANION/UNKNOWN, got {self.expectation}"
        
        valid_cog, err = self.cognitive_profile.validate()
        if not valid_cog:
            return False, f"cognitive_profile invalid: {err}"
        
        return True, None

    # ── Derived properties (convenience, not stored) ──

    @property
    def auto_resolve_threshold(self) -> float:
        """Derived ambiguity auto-resolve threshold."""
        if self.noise_level < 0.4:
            return 0.7
        elif self.noise_level < 0.7:
            return 0.5
        return 0.3

    @property
    def max_ambiguities_before_ask(self) -> int:
        """Derived max ambiguities before asking user."""
        if self.noise_level < 0.3:
            return 5
        elif self.noise_level < 0.7:
            return 3
        return 1

    @property
    def min_confidence_threshold(self) -> float:
        """Derived minimum confidence for intent classification."""
        if self.cognitive_profile.confidence > 0.7:
            return 0.6
        elif self.cognitive_profile.confidence > 0.3:
            return 0.4
        return 0.25

    @property
    def max_sub_intents(self) -> int:
        """Derived max sub-intents for multi-intent splitting."""
        if self.complexity_level > 0.8:
            return 10
        elif self.complexity_level > 0.5:
            return 5
        return 3

    # ── Factory methods ──

    @classmethod
    def default_fallback(cls, reason: str = "PCR error or timeout") -> "PCROutput_v1":
        """Conservative fallback output: UNKNOWN + low thresholds + high ask tendency."""
        return cls(
            expectation="UNKNOWN",
            noise_level=0.5,
            complexity_level=0.5,
            execution_mode="CLARIFICATION",
            parser_config_overrides={
                "auto_resolve_threshold": 0.3,
                "max_ambiguities_before_ask": 1,
                "min_confidence_threshold": 0.25,
                "max_sub_intents": 2,
            },
            prompt_style="BALANCED",
            ambiguity_strategy="CONSERVATIVE_ASK",
            is_fallback=True,
            fallback_reason=reason,
            trace_log=[f"[FALLBACK] {reason}"],
        )

    @classmethod
    def fast_execute_tool(cls, query: str, latency_ms: float = 0.0) -> "PCROutput_v1":
        """Factory for a clean TOOL-mode output."""
        return cls(
            expectation="TOOL",
            noise_level=0.05,
            complexity_level=0.2,
            cognitive_profile=CognitiveProfile_v1(
                metacognition=0.8, divergence=0.1, tracking_depth=0.9, stability=0.95, confidence=0.9
            ),
            execution_mode="FAST_EXECUTE",
            parser_config_overrides={
                "auto_resolve_threshold": 0.7,
                "max_ambiguities_before_ask": 5,
                "min_confidence_threshold": 0.6,
                "max_sub_intents": 3,
            },
            prompt_style="BRIEF",
            ambiguity_strategy="AGGRESSIVE_AUTO",
            latency_ms=latency_ms,
            trace_log=[f"[FAST_EXECUTE] query='{query[:50]}'"],
        )

    @classmethod
    def companion_exploratory(cls, query: str, latency_ms: float = 0.0) -> "PCROutput_v1":
        """Factory for a COMPANION-mode output."""
        return cls(
            expectation="COMPANION",
            noise_level=0.2,
            complexity_level=0.6,
            cognitive_profile=CognitiveProfile_v1(
                metacognition=0.2, divergence=0.8, tracking_depth=0.1, stability=0.3, confidence=0.5
            ),
            execution_mode="CONVERSATIONAL",
            parser_config_overrides={
                "auto_resolve_threshold": 0.5,
                "max_ambiguities_before_ask": 3,
                "min_confidence_threshold": 0.3,
                "max_sub_intents": 5,
            },
            prompt_style="TUTORIAL",
            ambiguity_strategy="BALANCED",
            suggested_next_actions=["反汇编入口点", "扫描内存数值", "分析程序保护"],
            latency_ms=latency_ms,
            trace_log=[f"[COMPANION] query='{query[:50]}'"],
        )

    @classmethod
    def advisor_analysis(cls, query: str, latency_ms: float = 0.0) -> "PCROutput_v1":
        """Factory for an ADVISOR-mode output."""
        return cls(
            expectation="ADVISOR",
            noise_level=0.2,
            complexity_level=0.8,
            cognitive_profile=CognitiveProfile_v1(
                metacognition=0.7, divergence=0.6, tracking_depth=0.7, stability=0.8, confidence=0.8
            ),
            execution_mode="DEEP_RESEARCH",
            parser_config_overrides={
                "auto_resolve_threshold": 0.6,
                "max_ambiguities_before_ask": 4,
                "min_confidence_threshold": 0.5,
                "max_sub_intents": 8,
            },
            prompt_style="EXPLANATORY",
            ambiguity_strategy="BALANCED",
            latency_ms=latency_ms,
            trace_log=[f"[ADVISOR] query='{query[:50]}'"],
        )

    # ── Serialization ──

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "expectation": self.expectation,
            "noise_level": self.noise_level,
            "complexity_level": self.complexity_level,
            "cognitive_profile": self.cognitive_profile.to_dict(),
            "execution_mode": self.execution_mode,
            "parser_config_overrides": self.parser_config_overrides,
            "prompt_style": self.prompt_style,
            "ambiguity_strategy": self.ambiguity_strategy,
            "suggested_next_actions": self.suggested_next_actions,
            "should_attach_process": self.should_attach_process,
            "should_refresh_analysis": self.should_refresh_analysis,
            "trace_log": self.trace_log,
            "latency_ms": self.latency_ms,
            "implementation": self.implementation,
            "cache_hit": self.cache_hit,
            "is_fallback": self.is_fallback,
            "fallback_reason": self.fallback_reason,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PCROutput_v1":
        cog_dict = d.get("cognitive_profile", {})
        if isinstance(cog_dict, dict):
            cognitive_profile = CognitiveProfile_v1.from_dict(cog_dict)
        else:
            cognitive_profile = CognitiveProfile_v1()
        
        return cls(
            version=d.get("version", PCRVersion.V1.value),
            expectation=d.get("expectation", "UNKNOWN"),
            noise_level=float(d.get("noise_level", 0.0)),
            complexity_level=float(d.get("complexity_level", 0.0)),
            cognitive_profile=cognitive_profile,
            execution_mode=d.get("execution_mode", "BALANCED"),
            parser_config_overrides=d.get("parser_config_overrides", {}),
            prompt_style=d.get("prompt_style", "BALANCED"),
            ambiguity_strategy=d.get("ambiguity_strategy", "BALANCED"),
            suggested_next_actions=d.get("suggested_next_actions", []),
            should_attach_process=d.get("should_attach_process", False),
            should_refresh_analysis=d.get("should_refresh_analysis", False),
            trace_log=d.get("trace_log", []),
            latency_ms=float(d.get("latency_ms", 0.0)),
            implementation=d.get("implementation", ""),
            cache_hit=d.get("cache_hit", False),
            is_fallback=d.get("is_fallback", False),
            fallback_reason=d.get("fallback_reason"),
        )
