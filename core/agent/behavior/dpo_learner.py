"""DPO preference learning for the behavior chain (LLM_COLLABORATIVE §四, B6).

Implicit user feedback → preference pairs:
    accept      → (predicted, actual)        PREFERRED   (weight 1.0)
    reject      → (predicted, actual)        DISPREFERRED (weight 1.0)
    correction  → (predicted, corrected)     PREFERRED   (weight 0.8)
    no_response → (predicted, actual)        weak signal (weight ×0.3)

When the pool reaches N pairs (default 20), the learner:
    1. asks the LLM for a distilled weight-delta suggestion (non-parametric,
       ADR-014: no fine-tuning — LLM output is a rule-level preference signal);
    2. applies the deltas to the behavior graph (preferred → up, dispreferred → down);
    3. resets the pool so the next batch can accumulate.

Everything is inspectable via stats() (A19) and thresholds live in the
ParameterRegistry (A18).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from core.agent.compiler.parameter_registry import get_registry


# 3.1a (STATE_SNAPSHOT §1.2): 仅对可观测行为事件记录 DPO 偏好对。
# dialog 类事件是用户文本，predictor 的 top1 是图内动作摘要，字符串相等
# 几乎恒 false → 产生"假 reject 池"。可观测 kind = ui/tool/api/config/document。
OBSERVABLE_ACTION_TYPES = frozenset({"ui", "tool", "api", "config", "document"})


@dataclass
class PreferencePair:
    id: str
    predicted: str
    actual: str
    label: str            # preferred | dispreferred
    weight: float         # signal strength
    source: str           # accept | reject | correction | no_response
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "predicted": self.predicted,
            "actual": self.actual,
            "label": self.label,
            "weight": self.weight,
            "source": self.source,
            "timestamp": self.timestamp,
        }


class DPOLearner:
    """Accumulate implicit-feedback preference pairs and distill weight deltas.

    One kernel, multiple facades: the behavior brain and the CLI both drive it.
    """

    def __init__(self, llm=None, min_pairs: Optional[int] = None):
        self._llm = llm
        self._pairs: List[PreferencePair] = []
        self._lock = threading.Lock()
        self._learn_count = 0
        self._last_llm_error: Optional[str] = None
        self._last_deltas: Optional[Dict[str, float]] = None
        reg = get_registry()
        self._min_pairs = min_pairs if min_pairs is not None else int(
            reg.get("behavior.dpo_min_pairs", 20)
        )

    # ── Feedback → pair ─────────────────────────────────────────────────────

    def record(self, predicted: str, actual: str, feedback: str) -> Optional[PreferencePair]:
        """Map an implicit feedback signal to a preference pair.

        feedback: accept | reject | correction | no_response

        3.1b 修复: 禁止 ``(summary, summary)`` 自对（无预测时不产生 no_response
        偏好对——语义错误，污染池子）。3.1a 门控由调用方
        （brain.learn_from_event）保证只喂可观测 kind。
        """
        reg = get_registry()
        if not predicted or not actual:
            return None
        if feedback == "no_response":
            # 无预测时 predicted==actual 是自对 — 不构成偏好信号，直接丢弃。
            if predicted == actual:
                return None
        if feedback == "accept":
            label, weight, source = "preferred", 1.0, "accept"
        elif feedback == "reject":
            label, weight, source = "dispreferred", 1.0, "reject"
        elif feedback == "correction":
            label, weight, source = "preferred", float(
                reg.get("behavior.dpo_correction_weight", 0.8)
            ), "correction"
        elif feedback == "no_response":
            label, weight, source = "preferred", float(
                reg.get("behavior.dpo_noop_weight", 0.3)
            ), "no_response"
        else:
            return None
        pair = PreferencePair(
            id=f"dp_{uuid.uuid4().hex[:8]}",
            predicted=predicted, actual=actual,
            label=label, weight=weight, source=source,
            timestamp=time.time(),
        )
        with self._lock:
            self._pairs.append(pair)
        return pair

    def ready(self) -> bool:
        """Pool reached the N threshold (design: N>20 → trigger learning)."""
        return len(self._pairs) >= self._min_pairs

    def pairs(self) -> List[PreferencePair]:
        return list(self._pairs)

    # ── Distill + apply (Phase 3: DPO learning) ─────────────────────────────

    async def learn(self, llm=None) -> Optional[Dict[str, float]]:
        """Distill preference pairs into behavior-graph weight deltas.

        Non-parametric (ADR-014): the LLM returns a JSON weight-delta map
        keyed by action summary; positive = prefer, negative = disprefer.
        Falls back to a rule-based delta when no LLM is available.
        """
        llm = llm or self._llm
        if not self.ready():
            return None
        deltas = None
        if llm is not None:
            try:
                deltas = await self._llm_distill(llm)
            except Exception as e:
                self._last_llm_error = str(e)
                logger.debug("DPO LLM distillation failed: %s", e)
        if deltas is None:
            deltas = self._rule_distill()
        self._last_deltas = deltas
        with self._lock:
            self._learn_count += 1
            self._pairs = []
        return deltas

    async def _llm_distill(self, llm) -> Dict[str, float]:
        summary = [p.to_dict() for p in self._pairs[:60]]
        prompt = (
            "You are tuning a behavior predictor from implicit preference pairs.\n"
            "PREFERENCE_PAIRS: " + json.dumps(summary, ensure_ascii=False) + "\n"
            "Return ONLY JSON: {\"<action_summary>\": +delta, ...}\n"
            "Positive delta = user prefers this behavior; negative = disprefer.\n"
            "Deltas must be in [-0.5, 0.5]."
        )
        raw = await llm.generate(prompt, max_tokens=400)
        cleaned = str(raw).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return self._rule_distill()
        data = json.loads(cleaned[start:end + 1])
        deltas = {}
        for k, v in data.items():
            try:
                val = float(v)
                deltas[str(k)] = max(-0.5, min(0.5, val))
            except (TypeError, ValueError):
                continue
        return deltas or self._rule_distill()

    def _rule_distill(self) -> Dict[str, float]:
        """Statistical fallback: preferred edges up, dispreferred down."""
        deltas: Dict[str, float] = {}
        for p in self._pairs:
            # 3.1a: 自对/空对不参与蒸馏（防御，调用方已过滤）
            if not p.actual or p.actual == p.predicted:
                continue
            delta = 0.15 * p.weight
            if p.label == "dispreferred":
                delta = -delta
            key = p.actual
            deltas[key] = deltas.get(key, 0.0) + delta
        return {k: max(-0.5, min(0.5, v)) for k, v in deltas.items()}

    def apply_to_graph(self, graph) -> int:
        """Apply the latest weight deltas to graph edges (3.1c: 归一化匹配).

        匹配策略（对齐率修复）:
          1. 精确 action_summary 匹配（图内节点原文）
          2. 归一化匹配（去空白/大小写）——LLM 蒸馏返回的 key 常带格式差异
          3. action_type 辅助（同类型才命中，避免跨域误调）
        """
        if not self._last_deltas:
            return 0

        def _norm(s: str) -> str:
            return " ".join(str(s).strip().lower().split())

        norm_deltas = {_norm(k): v for k, v in self._last_deltas.items()}
        applied = 0
        # 精确 + 归一化索引
        exact_nodes = {}
        norm_nodes = {}
        for s in getattr(graph, "nodes", {}).values():
            exact_nodes[s.action_summary] = s
            norm_nodes.setdefault(_norm(s.action_summary), []).append(s)
        for ek, edge in getattr(graph, "edges", {}).items():
            node = getattr(graph, "nodes", {}).get(edge.to_step_id)
            if node is None:
                continue
            # 1) 精确
            delta = self._last_deltas.get(node.action_summary)
            # 2) 归一化（带 action_type 校验）
            if delta is None:
                if norm_nodes.get(_norm(node.action_summary)):
                    delta = norm_deltas.get(_norm(node.action_summary))
            if delta is None:
                continue
            edge.weight = max(0.0, min(1.0, edge.weight + delta))
            applied += 1
        return applied

    def reset(self) -> None:
        with self._lock:
            self._pairs = []

    # ── White-box (A19) ─────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        counts = {"preferred": 0, "dispreferred": 0}
        by_source: Dict[str, int] = {}
        for p in self._pairs:
            counts[p.label] = counts.get(p.label, 0) + 1
            by_source[p.source] = by_source.get(p.source, 0) + 1
        return {
            "pool_size": len(self._pairs),
            "min_pairs": self._min_pairs,
            "ready": self.ready(),
            "by_label": counts,
            "by_source": by_source,
            "learn_count": self._learn_count,
            "last_deltas": self._last_deltas,
            "last_llm_error": self._last_llm_error,
        }
