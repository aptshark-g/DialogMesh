# -*- coding: utf-8 -*-
from __future__ import annotations
import logging, re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DANGEROUS_PATTERNS = [
    re.compile(r"(?i)\b(rm\s+-rf\s+/|format\s+[a-z]:|shutdown\s+-s\s+-t)"),
    re.compile(r"(?i)(DROP|DELETE|TRUNCATE)\s+(TABLE|DATABASE)"),
    re.compile(r"(?i)exec\(.*\)|eval\(.*\)|__import__\(.*\)"),
]

class AnswerConstraintValidator:
    def __init__(self, max_length: int = 4096, min_confidence: float = 0.0):
        self.max_length = max_length
        self.min_confidence = min_confidence

    def validate(self, answer_text: str, confidence: float, metadata: Optional[Dict] = None) -> List[Dict[str, Any]]:
        violations = []
        length = len(answer_text)
        if length > self.max_length:
            violations.append({"type": "length_exceeded", "severity": "warning", "message": f"回答长度 {length} 超过限制 {self.max_length}", "actual": length, "limit": self.max_length})
        if confidence < self.min_confidence:
            violations.append({"type": "low_confidence", "severity": "info", "message": f"置信度 {confidence:.2f} 低于阈值 {self.min_confidence}", "confidence": confidence, "threshold": self.min_confidence})
        for pat in _DANGEROUS_PATTERNS:
            m = pat.search(answer_text)
            if m:
                violations.append({"type": "dangerous_content", "severity": "error", "message": f"检测到危险内容: {m.group()[:50]}", "matched": m.group()})
        if not answer_text.strip():
            violations.append({"type": "empty_response", "severity": "error", "message": "回答为空"})
        return violations

    def is_safe(self, answer_text: str, confidence: float) -> Tuple[bool, List[Dict[str, Any]]]:
        violations = self.validate(answer_text, confidence)
        errors = [v for v in violations if v["severity"] == "error"]
        return len(errors) == 0, violations

__all__ = ["AnswerConstraintValidator"]
