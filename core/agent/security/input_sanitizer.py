# -*- coding: utf-8 -*-
"""
core/agent/security/input_sanitizer.py
─────────────────────────────────────
Industrial-grade input sanitization for prompt injection protection.

Detects and scores common attack vectors:
  • Instruction override  ("ignore previous instructions", "system prompt")
  • Delimiter injection     (repeated ```, ---, XML tags to break context)
  • Context leakage         ("print your system prompt", "输出你的系统提示")
  • Role play               ("you are now", "从这一刻起你是")
  • Multi-language attacks  (same attacks in Chinese, English, mixed)

Design principles:
  • Rule-based + heuristic scoring (no extra model dependency)
  • Returns (is_safe, score, reasons) — caller decides action
  • Score 0-1: 0 = clean, 1 = definitely malicious
  • Threshold configurable per environment (strict 0.1 / standard 0.3 / lenient 0.5)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass(frozen=False)
class SanitizationResult:
    """Result of input sanitization check."""
    is_safe: bool = True
    score: float = 0.0  # 0.0 = clean, 1.0 = definitely malicious
    threshold: float = 0.3
    reasons: List[str] = field(default_factory=list)
    matched_patterns: List[str] = field(default_factory=list)
    sanitized_text: Optional[str] = None  # If redaction applied


class InputSanitizer:
    """
    Prompt injection detector.

    Usage:
        sanitizer = InputSanitizer()
        result = sanitizer.check(user_input)
        if not result.is_safe:
            # Block or sanitize
            pass
    """

    # ── Configuration ────────────────────────────────────────────────────

    DEFAULT_THRESHOLD = 0.30
    STRICT_THRESHOLD = 0.10
    LENIENT_THRESHOLD = 0.50

    def __init__(self, threshold: Optional[float] = None):
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        self._compile_patterns()

    # ── Attack Pattern Definitions ─────────────────────────────────────────

    def _compile_patterns(self) -> None:
        """Compile all detection patterns with weights."""

        # Category 1: Instruction override (highest severity)
        self._instruction_override = [
            # English
            (r"ignore\s+(all\s+)?previous\s+(instructions?|prompts?|commands?|context)", 0.90),
            (r"ignore\s+(the\s+)?(above|above\s+instructions?|system\s+prompt)", 0.85),
            (r"disregard\s+(all\s+)?(previous|prior)\s+(instructions?|rules?)", 0.85),
            (r"override\s+(previous|all\s+prior)\s+(instructions?|settings?)", 0.85),
            (r"new\s+instruction[s]?\s*:", 0.70),
            (r"system\s+prompt\s*[:=]", 0.80),
            (r"system\s+instruction[s]?\s*[:=]", 0.80),
            (r"developer\s+mode\s*[:=]", 0.75),
            (r"DAN\s+mode|do\s+anything\s+now", 0.75),
            # Chinese
            (r"忽略\s*(所有\s*)?(之前的?|上述|以上)\s*(指令|提示|命令|上下文)", 0.90),
            (r"无视\s*(所有\s*)?(之前的?|上述|以上)\s*(指令|规则|设置)", 0.85),
            (r"覆盖\s*(之前|所有)\s*(指令|设置|配置)", 0.85),
            (r"新的?\s*指令\s*[:：]", 0.70),
            (r"系统提示\s*[:：]", 0.80),
            (r"系统指令\s*[:：]", 0.80),
            (r"开发者模式\s*[:：]", 0.75),
            # Mixed / code-like
            (r"<!--\s*system\s*[:：]", 0.80),
            (r"\/\/\s*ignore\s+previous", 0.70),
            (r"#\s*ignore\s+all\s+above", 0.70),
        ]

        # Category 2: Context leakage / prompt extraction
        self._context_leakage = [
            (r"print\s+(your\s+)?(system\s+)?prompt", 0.80),
            (r"show\s+(your\s+)?(system\s+)?instructions", 0.80),
            (r"reveal\s+(your\s+)?(system\s+)?prompt", 0.80),
            (r"what\s+are\s+your\s+(system\s+)?instructions", 0.75),
            (r"repeat\s+(the\s+)?(words\s+)?above", 0.70),
            (r"output\s+(the\s+)?(system\s+)?prompt", 0.80),
            # Chinese
            (r"输出\s*(你的?)?\s*系统提示", 0.80),
            (r"打印\s*(你的?)?\s*系统提示", 0.80),
            (r"显示\s*(你的?)?\s*系统指令", 0.80),
            (r"泄露\s*(你的?)?\s*系统提示", 0.80),
            (r"你的\s*系统提示\s*是\s*什么", 0.75),
            (r"重复\s*(上面|前文|之前的?)\s*(内容|文字|话)", 0.70),
            (r"你\s*的\s*初始\s*提示\s*是", 0.75),
        ]

        # Category 3: Role play / persona override
        self._role_play = [
            (r"you\s+are\s+now\s+", 0.70),
            (r"from\s+now\s+on\s+you\s+are\s+", 0.70),
            (r"act\s+as\s+", 0.50),  # Lower — "act as" can be legitimate
            (r"pretend\s+to\s+be\s+", 0.60),
            (r"simulate\s+being\s+", 0.60),
            (r"take\s+on\s+the\s+role\s+of\s+", 0.50),
            # Chinese
            (r"你\s*(现在|从这一刻起|从现在开始)\s*是\s*", 0.70),
            (r"你\s*(现在|从这一刻起|从现在开始)\s*扮演\s*", 0.60),
            (r"假装\s*你是\s*", 0.60),
            (r"模拟\s*(成为|作为)\s*", 0.60),
            (r"扮演\s*一个\s*", 0.50),
        ]

        # Category 4: Delimiter injection (breaking out of markdown/XML context)
        self._delimiter_injection = [
            (r"```\s*\n\s*```", 0.60),  # Empty code block sequence
            (r"```\s*\n.*?\n```\s*\n```", 0.70),  # Multiple code blocks
            (r"---\s*\n\s*---\s*\n\s*---", 0.60),  # Repeated horizontal rules
            (r"<\/?[a-zA-Z]+\s*[^>]*>", 0.40),  # HTML tags (lower — can be legitimate)
            (r"\[\/system\]|\[\/user\]|\[\/assistant\]", 0.80),  # Fake role tags
            (r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>", 0.90),  # Special tokens
        ]

        # Category 5: Obfuscation / encoding tricks
        self._obfuscation = [
            (r"\x00", 0.50),  # Null bytes
            (r"[\x01-\x08\x0b-\x0c\x0e-\x1f]", 0.40),  # Control chars
            (r"[\u200b-\u200f\u2060-\u2064]", 0.60),  # Zero-width characters
            (r"base64\s*[:：]?\s*[A-Za-z0-9+/]{20,}=*=", 0.50),  # Base64 encoded payload
            (r"hex\s*[:：]?\s*[0-9a-fA-F]{20,}", 0.50),  # Hex encoded payload
        ]

        # Compile all
        self._patterns: List[Tuple[re.Pattern, float, str]] = []
        for raw_list, cat_name in [
            (self._instruction_override, "instruction_override"),
            (self._context_leakage, "context_leakage"),
            (self._role_play, "role_play"),
            (self._delimiter_injection, "delimiter_injection"),
            (self._obfuscation, "obfuscation"),
        ]:
            for pattern_str, weight in raw_list:
                try:
                    compiled = re.compile(pattern_str, re.IGNORECASE | re.DOTALL)
                    self._patterns.append((compiled, weight, cat_name))
                except re.error:
                    continue  # Skip invalid patterns

    # ── Public API ─────────────────────────────────────────────────────────

    def check(self, text: str) -> SanitizationResult:
        """
        Check input for prompt injection attacks.

        Returns SanitizationResult with is_safe=False if score >= threshold.
        """
        if not text:
            return SanitizationResult(is_safe=True, score=0.0, threshold=self.threshold)

        score = 0.0
        reasons: List[str] = []
        matched: List[str] = []

        # Check each pattern
        for pattern, weight, category in self._patterns:
            if pattern.search(text):
                score += weight
                matched.append(f"{category}:{pattern.pattern[:40]}")
                if len(reasons) < 5:  # Limit reasons
                    reasons.append(f"[{category}] matched: {pattern.pattern[:40]}")

        # Cap at 1.0
        score = min(1.0, score)

        # Apply length penalty for very long inputs (potential prompt stuffing)
        if len(text) > 2000:
            score += 0.05
            score = min(1.0, score)
            if score >= self.threshold:
                reasons.append("[length] Input exceeds 2000 chars")

        is_safe = score < self.threshold

        return SanitizationResult(
            is_safe=is_safe,
            score=round(score, 4),
            threshold=self.threshold,
            reasons=reasons,
            matched_patterns=matched,
            sanitized_text=self._redact(text) if not is_safe else None,
        )

    def redact(self, text: str) -> str:
        """Force redaction of sensitive patterns."""
        return self._redact(text)

    # ── Internal ───────────────────────────────────────────────────────────

    def _redact(self, text: str) -> str:
        """Replace matched patterns with [REDACTED]."""
        result = text
        for pattern, _, _ in self._patterns:
            result = pattern.sub("[REDACTED]", result)
        return result

    # ── Factory presets ────────────────────────────────────────────────────

    @classmethod
    def strict(cls) -> "InputSanitizer":
        """Strict mode: blocks more aggressively."""
        return cls(threshold=cls.STRICT_THRESHOLD)

    @classmethod
    def lenient(cls) -> "InputSanitizer":
        """Lenient mode: only blocks obvious attacks."""
        return cls(threshold=cls.LENIENT_THRESHOLD)
