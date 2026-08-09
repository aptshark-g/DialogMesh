"""Causal provenance — A23 溯源置信层 × A24 逆向动力系统（D-12 升级）。

检验流程（P0 溯源置信，融合 A24 发散/收束/可逆推）::

    发散 (DMN): 掩盖上下文 → LLM 高温度(0.8) 无约束候选假设
                + 规则来源（键合图/行为链/骨架）结构假设
    收束 (ECN): 带上下文低温度(0.1) 筛选
                - do-calculus HARD_BLOCK 第一道负向筛选
                - 证据覆盖检查第二道
                - 驳回假设记录拒绝理由（知识边界学习）
    溯源置信:  1 - ∏(1 - max_conf_per_source)
               键合图 0.95 / 人工 0.9 / 行为链 0.7 / do-calculus 0.6 / LLM 0.3-0.5
    可逆推:    收束后的因果声明必须反推回证据，coverage 60-80%
               (100% = 过拟合, 0% = 没学到)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# 来源 → 可信度（A23/D-12）
SOURCE_CONFIDENCE: Dict[str, float] = {
    "bond_graph": 0.95,     # 键合图（物理拓扑）
    "human": 0.9,           # 人工标注/用户确认
    "behavior": 0.7,        # 行为链序列证据
    "do_calculus": 0.6,     # 负向验证通过
    "llm": 0.3,             # LLM 推断（低置信起点）
}


@dataclass
class CausalHypothesis:
    """发散阶段的一个候选因果假设。"""
    cause: str
    effect: str
    source: str                  # bond_graph/human/behavior/do_calculus/llm
    rationale: str = ""
    confidence: float = 0.0
    rejected: bool = False
    reject_reason: str = ""


@dataclass
class ProvenanceResult:
    """收束后的溯源置信结论。"""
    cause: str
    effect: str
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)
    coverage: float = 0.0        # 可逆推覆盖率 (60-80% 目标区间)
    accepted: bool = False
    rejected: List[Dict[str, str]] = field(default_factory=list)


def diverge(cause: str, effect: str, rule_hints: List[str] = None,
            llm=None) -> List[CausalHypothesis]:
    """DMN 发散：从多来源生成候选因果假设。

    - 规则来源：键合图/行为链/骨架的结构假设（零成本）。
    - LLM 来源：掩盖上下文，高温度无约束猜测（仅当 llm 可用）。
    """
    hypotheses: List[CausalHypothesis] = []

    # 规则来源发散
    for hint in (rule_hints or []):
        src = "bond_graph" if "bond" in hint.lower() else "behavior"
        hypotheses.append(CausalHypothesis(
            cause=cause, effect=effect, source=src,
            rationale=hint, confidence=SOURCE_CONFIDENCE[src],
        ))

    # LLM 来源发散（掩盖上下文：只给变量名，不给具体场景）
    if llm is not None:
        prompt = (
            f"给定两个变量 X={cause!r} 与 Y={effect!r}，"
            "不依赖任何具体上下文，发散列出最多 3 种 X 导致 Y 的可能机制。"
            '逐条输出，格式 "机制: ..."'
        )
        try:
            resp = str(llm.generate(prompt, max_tokens=200, temperature=0.8))
            for line in resp.splitlines():
                line = line.strip()
                if line and (line.startswith("机制") or line.startswith("mechanism")):
                    hypotheses.append(CausalHypothesis(
                        cause=cause, effect=effect, source="llm",
                        rationale=line, confidence=SOURCE_CONFIDENCE["llm"],
                    ))
        except Exception:
            pass

    return hypotheses


def converge(hypotheses: List[CausalHypothesis], do_validator=None,
             evidence_facts: List[str] = None) -> ProvenanceResult:
    """ECN 收束：负向筛选 → 证据覆盖 → 来源融合置信。

    do_validator 提供 ``verify_negative(from, to) -> "HARD_BLOCK"|"WARN"|"PASS"``。
    """
    if not hypotheses:
        return ProvenanceResult(
            cause="", effect="", confidence=0.0, accepted=False,
        )

    cause = hypotheses[0].cause
    effect = hypotheses[0].effect
    kept: List[CausalHypothesis] = []
    rejected: List[Dict[str, str]] = []

    # 第一道：do-calculus 负向（HARD_BLOCK 排除）
    if do_validator is not None:
        try:
            level = do_validator.verify_negative(cause, effect)
            if level == "HARD_BLOCK":
                return ProvenanceResult(
                    cause=cause, effect=effect, confidence=0.0,
                    sources=[], coverage=0.0, accepted=False,
                    rejected=[{"cause": cause, "effect": effect,
                               "reason": "do-calculus HARD_BLOCK"}],
                )
        except Exception:
            pass

    # 第二道：证据覆盖检查（可逆推：因果声明必须能反推回证据）
    facts = evidence_facts or []
    for h in hypotheses:
        if h.rejected:
            rejected.append({"cause": h.cause, "effect": h.effect,
                             "reason": h.reject_reason})
            continue
        if facts:
            matched = sum(1 for f in facts if h.rationale and h.rationale in f)
            coverage = matched / max(1, len(facts))
            # A24: coverage 目标 60-80%；过低=没学到，过高=过拟合。
            if coverage < 0.4:
                h.rejected = True
                h.reject_reason = f"coverage {coverage:.0%} < 40% (没学到)"
                rejected.append({"cause": h.cause, "effect": h.effect,
                                 "reason": h.reject_reason})
                continue
            h.confidence = min(1.0, h.confidence + coverage * 0.2)
        kept.append(h)

    if not kept:
        return ProvenanceResult(
            cause=cause, effect=effect, confidence=0.0,
            sources=[], coverage=0.0, accepted=False, rejected=rejected,
        )

    # 来源融合：1 - ∏(1 - max_conf_per_source)
    per_source = {}
    for h in kept:
        cur = per_source.get(h.source, 0.0)
        if h.confidence > cur:
            per_source[h.source] = h.confidence
    fused = 1.0
    for conf in per_source.values():
        fused *= (1.0 - conf)
    confidence = round(1.0 - fused, 3)

    # 可逆推覆盖率：收束后保留假设覆盖证据的比例
    coverage = 0.0
    if facts:
        matched = sum(1 for h in kept for f in facts
                      if h.rationale and h.rationale in f)
        coverage = round(matched / max(1, len(facts)), 3)

    return ProvenanceResult(
        cause=cause, effect=effect,
        confidence=confidence,
        sources=list(per_source.keys()),
        coverage=coverage,
        accepted=confidence >= 0.7 and 0.4 <= coverage <= 0.9,
        rejected=rejected,
    )
