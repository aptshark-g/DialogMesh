# core/agent/discourse_block_tree/summary_engine.py
"""SummaryEngine — 渐进式摘要引擎（v1-v3）。

v1: 单轮压缩（逐轮压缩，保留主谓宾 + 关键属性）
v2: 块内合并（跨轮次合并，包含 top 3 实体 + 意图 + 行为序列）
v3: 演化摘要（主题级高阶压缩，规则实现，块内轮次 > 5 时触发）

MVP 约束:
- v1-v2 纯规则（< 1ms）
- v3 规则压缩（MVP 中暂缓 LLM 压缩）
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Dict, List, Optional

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

try:
    from core.agent.discourse_block_tree.models import (
        DiscourseBlock,
        EDU,
        ProgressiveSummary,
    )
except ImportError:
    import importlib.util
    import os
    import sys
    _models_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "discourse_block_tree", "models.py"
    )
    _spec = importlib.util.spec_from_file_location("discourse_models", _models_path)
    _models_module = importlib.util.module_from_spec(_spec)
    sys.modules["discourse_models"] = _models_module
    _spec.loader.exec_module(_models_module)
    DiscourseBlock = _models_module.DiscourseBlock
    EDU = _models_module.EDU
    ProgressiveSummary = _models_module.ProgressiveSummary

logger = logging.getLogger(__name__)

class SummaryEngine:
    """渐进式摘要引擎。"""

    def __init__(self, v3_trigger_turn_count: int = 5):
        # 从配置读取默认值
        config = get_discourse_config() if get_discourse_config else None
        sum_cfg = config.summary if config else None

        self.v3_trigger_turn_count = v3_trigger_turn_count if (sum_cfg is None) else sum_cfg.v3_trigger_turn_count

        logger.debug(f"SummaryEngine initialized (v3_trigger={self.v3_trigger_turn_count})")

    # ── 公共接口 ──────────────────────────────────────────────────

    def summarize_block(self, block: DiscourseBlock) -> ProgressiveSummary:
        """为话语块生成渐进式摘要（v1-v3）。

        如果块已有摘要，只更新缺失的级别。
        """
        if block.summary is None:
            block.summary = ProgressiveSummary()

        summary = block.summary

        # v1: 单轮压缩（基于每个 EDU）
        if summary.v1 is None:
            summary.v1 = self._generate_v1(block)
            summary.v1_timestamp = time.time()

        # v2: 块内合并（基于整个块）
        if summary.v2 is None:
            summary.v2 = self._generate_v2(block)
            summary.v2_timestamp = time.time()

        # v3: 演化摘要（触发条件：块内轮次 > 5）
        if summary.v3 is None and block.turn_count > self.v3_trigger_turn_count:
            summary.v3 = self._generate_v3(block)
            summary.v3_timestamp = time.time()
            summary.v3_trigger_reason = f"turn_count>{self.v3_trigger_turn_count}"

        return summary

    def update_v1(self, block: DiscourseBlock) -> str:
        """更新 v1 摘要（新 EDU 加入后调用）。"""
        v1 = self._generate_v1(block)
        if block.summary is None:
            block.summary = ProgressiveSummary(v1=v1, v1_timestamp=time.time())
        else:
            block.summary.v1 = v1
            block.summary.v1_timestamp = time.time()
            # v2/v3 需要重新生成
            block.summary.v2 = None
            block.summary.v3 = None
        return v1

    # ── v1: 单轮压缩 ───────────────────────────────────────────────

    def _generate_v1(self, block: DiscourseBlock) -> str:
        """v1: 逐轮压缩，每个 EDU 生成一句话摘要。

        格式: [NOT]Subject Predicate [NOT]Object (attrs)
        例如: "User likes Python (stable, easy)"
        """
        parts = []
        for edu in block.edus:
            part = self._compress_edu(edu)
            if part:
                parts.append(part)
        return "; ".join(parts) if parts else "(empty block)"

    @staticmethod
    def _compress_edu(edu: EDU) -> str:
        """压缩单个 EDU 为一句话摘要。"""
        attrs = []
        if edu.negation:
            attrs.append("NOT")
        if edu.uncertainty:
            attrs.append("MAYBE")
        if edu.imperative:
            attrs.append("CMD")
        if edu.question:
            attrs.append("Q")

        subject = edu.subject or "?"
        predicate = edu.predicate or "?"
        obj = edu.object or ""

        # 属性修饰
        subj_attrs = f"[{','.join(edu.subject_attrs)}]" if edu.subject_attrs else ""
        obj_attrs = f"[{','.join(edu.object_attrs)}]" if edu.object_attrs else ""

        attr_prefix = f"({' '.join(attrs)}) " if attrs else ""
        subject_str = f"{subj_attrs}{subject}" if subj_attrs else subject
        object_str = f"{obj_attrs}{obj}" if obj_attrs else obj

        if obj:
            return f"{attr_prefix}{subject_str} {predicate} {object_str}"
        else:
            return f"{attr_prefix}{subject_str} {predicate}"

    # ── v2: 块内合并 ───────────────────────────────────────────────

    def _generate_v2(self, block: DiscourseBlock) -> str:
        """v2: 块内合并摘要。

        包含:
        - 主导意图
        - Top 3 实体（按提及次数排序）
        - 关键行为序列（谓语列表）
        - 否定/不确定性标记
        """
        # 1. 主导意图
        intent = block.intent_label or "general"

        # 2. Top 3 实体
        entity_counter = Counter()
        for edu in block.edus:
            for e in edu.raw_entities:
                entity_counter[e] += 1
        top_entities = [e for e, _ in entity_counter.most_common(3)]
        entities_str = ", ".join(top_entities) if top_entities else "none"

        # 3. 行为序列（谓语列表，去重）
        predicates = []
        seen_pred = set()
        for edu in block.edus:
            if edu.predicate and edu.predicate not in seen_pred:
                seen_pred.add(edu.predicate)
                predicates.append(edu.predicate)
        actions_str = " → ".join(predicates[:5]) if predicates else "none"

        # 4. 特殊标记
        markers = []
        if any(e.negation for e in block.edus):
            markers.append("NEG")
        if any(e.uncertainty for e in block.edus):
            markers.append("UNCERTAIN")
        if any(e.imperative for e in block.edus):
            markers.append("CMD")
        markers_str = f" [{' '.join(markers)}]" if markers else ""

        return f"[{intent}]{markers_str} entities={entities_str} actions={actions_str}"

    # ── v3: 演化摘要 ───────────────────────────────────────────────

    def _generate_v3(self, block: DiscourseBlock) -> str:
        """v3: 演化摘要（主题级高阶压缩）。

        MVP 规则实现（暂缓 LLM 压缩）:
        - 基于 v2 摘要，进一步压缩为一句话主题描述
        - 包含: 主题 + 核心行为 + 结论
        """
        v2 = block.summary.v2 if block.summary else ""
        if not v2:
            v2 = self._generate_v2(block)

        # 提取核心信息
        intent = block.intent_label or "general"
        top_entities = []
        for edu in block.edus:
            top_entities.extend(edu.raw_entities)
        top_entities = list(dict.fromkeys(top_entities))[:3]  # 去重，取前3
        entities_str = "/".join(top_entities) if top_entities else "topic"

        # 结论性谓语（最后一个明确谓语）
        final_predicate = ""
        for edu in reversed(block.edus):
            if edu.predicate:
                final_predicate = edu.predicate
                break

        # 否定/不确定结论
        conclusion = ""
        if any(e.negation for e in block.edus):
            conclusion = " (rejected)"
        elif any(e.uncertainty for e in block.edus):
            conclusion = " (uncertain)"
        elif any(e.imperative for e in block.edus):
            conclusion = " (pending)"
        else:
            conclusion = " (confirmed)"

        return f"Topic:{entities_str} | Intent:{intent} | Conclusion:{final_predicate}{conclusion}"
