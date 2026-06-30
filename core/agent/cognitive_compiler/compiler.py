# -*- coding: utf-8 -*-
"""
core/agent/cognitive_compiler/compiler.py
──────────────────────────────────────
Cognitive compiler orchestrator.

设计要点：
  - 编译器只负责解析→补全→粘合度计算，不判断意图，不内部调用话题树/双结构
  - 三级模式：fast(<2ms, 纯规则) → hybrid(灰区调1.5B LLM, <30ms) → full(完整LLM)
  - 编译器输出 cohesion_score，话题路由由调用方显式执行
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.agent.cognitive_compiler.decomposer import SyntacticDecomposer, ParsedClause
from core.agent.cognitive_compiler.injector import HeaderInjector
from core.agent.cognitive_compiler.scorer import CohesionScorer


class CompilerMode(Enum):
    """编译器运行模式。"""
    FAST = "fast"       # 纯规则，<2ms
    HYBRID = "hybrid"   # 规则+LLM辅助，<30ms
    FULL = "full"       # 完整LLM，<200ms
    AUTO = "auto"       # 根据输入复杂度自动选择


@dataclass(frozen=False)
class CompiledInput:
    """编译后的结构化输入。"""
    query: str = ""                          # 补全后的查询文本
    raw_query: str = ""                    # 原始查询文本
    cohesion_score: float = 0.0              # 与当前话题的粘合度 (0-1)
    # 编译器不填 topic_node_id，由调用方利用 cohesion_score 执行路由
    topic_node_id: Optional[str] = None
    timeline_event_id: Optional[str] = None
    # 解析产物
    clauses: List[ParsedClause] = field(default_factory=list)
    injected_headers: Dict[str, Any] = field(default_factory=dict)
    # 编译元信息
    compilation_time_ms: float = 0.0
    mode_used: str = ""
    parse_trace: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "raw_query": self.raw_query,
            "cohesion_score": self.cohesion_score,
            "topic_node_id": self.topic_node_id,
            "timeline_event_id": self.timeline_event_id,
            "clauses": [c.to_dict() for c in self.clauses],
            "injected_headers": self.injected_headers,
            "compilation_time_ms": self.compilation_time_ms,
            "mode_used": self.mode_used,
            "parse_trace": self.parse_trace,
            "metadata": self.metadata,
        }


class CognitiveCompiler:
    """
    认知编译器。
    将原始用户输入编译为结构化、实体补全、粘合度标注的输入。
    """

    def __init__(
        self,
        decomposer: Optional[SyntacticDecomposer] = None,
        injector: Optional[HeaderInjector] = None,
        scorer: Optional[CohesionScorer] = None,
        mode: CompilerMode = CompilerMode.AUTO,
    ):
        self.decomposer = decomposer or SyntacticDecomposer()
        self.injector = injector or HeaderInjector()
        self.scorer = scorer or CohesionScorer()
        self.mode = mode

    def compile(
        self,
        user_input: str,
        turn_index: int,
        session_history: Optional[List[Dict[str, Any]]] = None,
        entity_cache: Optional[Any] = None,
    ) -> CompiledInput:
        """
        编译用户输入。
        三阶段：句法分解 → 头文件引入 → 粘合度计算。
        """
        start = time.time()
        session_history = session_history or []

        result = CompiledInput(raw_query=user_input)

        # Step 1: 确定模式
        mode = self._select_mode(user_input, turn_index)
        result.mode_used = mode.value

        # Step 2: 句法分解
        clauses, parse_trace = self.decomposer.decompose(user_input, mode=mode)
        result.clauses = clauses
        result.parse_trace.extend(parse_trace)

        # Step 3: 头文件引入（实体补全 + 代词消解）
        injected, headers = self.injector.inject(
            clauses, session_history, entity_cache=entity_cache
        )
        result.injected_headers = headers

        # 将本轮提取的实体压入 entity_cache（供下一轮回溯）
        if entity_cache is not None:
            entities = self._extract_entities_from_clauses(injected)
            if entities:
                entity_cache.push(turn_index, entities)

        # 重建查询文本
        result.query = self._rebuild_query(injected)

        # Step 4: 粘合度计算
        cohesion = self.scorer.calculate(result.query, session_history)
        result.cohesion_score = cohesion
        result.parse_trace.append(f"[COHESION] score={cohesion:.3f}")

        result.compilation_time_ms = (time.time() - start) * 1000
        return result

    def _extract_entities_from_clauses(self, clauses: List[ParsedClause]) -> List[Dict[str, Any]]:
        """从子句列表中提取实体，用于压入 entity_cache。"""
        entities = []
        for c in clauses:
            if c.backfilled and c.backfill_source:
                # 被回溯补全的实体，标记来源
                entities.append({"value": c.subject, "type": "backfilled", "source": c.backfill_source})
            if c.subject and not c.backfilled:
                entities.append({"value": c.subject, "type": "subject"})
            if c.object:
                entities.append({"value": c.object, "type": "object"})
        return entities

    def _select_mode(self, user_input: str, turn_index: int) -> CompilerMode:
        """根据输入复杂度选择编译模式。"""
        if self.mode != CompilerMode.AUTO:
            return self.mode

        # 极简输入 → fast
        if len(user_input) < 20 and turn_index < 3:
            return CompilerMode.FAST

        # 复杂输入（长句、多从句、多主语）→ full
        if self.decomposer._is_complex_input(user_input) or self.decomposer._has_multiple_subjects(user_input):
            return CompilerMode.FULL

        # 默认 hybrid
        return CompilerMode.HYBRID

    def _rebuild_query(self, clauses: List[ParsedClause]) -> str:
        """从分解后的子句重建查询文本。"""
        return " | ".join(c.to_query() for c in clauses)
