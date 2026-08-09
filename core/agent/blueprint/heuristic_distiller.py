"""HeuristicDistiller — 二阶抽象提炼管道（变化驱动, A24 / blog chapter3）.

管道: 取材 → 发散（部分信息猜测家族, temp=0.8 调先验）
     → 收敛（暴露全上下文, temp=0.1 筛选 + 拒绝理由）
     → 反事实扩展（低 coverage 高 insight → 主动构造连锁猜想）
     → LLM 反推验证（coverage 60-80%; 100%=过拟合, 0%=幻觉）
     → 沉淀进 HeuristicInventory。

触发 = 变化驱动（失败/用户纠正/公理冲突/启发过时/缺公理感）,
定时蒸馏仅兜底。LLM 必须（掩盖/暴露切换先验后验）;
无 LLM → 规则聚类兜底（source="rule", 仅冷启动）。
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any, Dict, List, Optional

from core.agent.blueprint.heuristic_inventory import (
    Heuristic, HeuristicInventory, SEED_HEURISTICS, STRUCTURE_TEMPLATE,
)

logger = logging.getLogger(__name__)

# 发散变体家族（远迁移文献: Gentner 结构对齐 / Gick&Holyoak 类比迁移 /
# Barnett&Ceci 情境维度 / Holyoak&Thagard 三约束）
DIVERGE_VARIANTS: Dict[str, str] = {
    "commonalize": (
        "以下决策样本表面不同, 请找出它们共同的底层机制"
        "（结构对齐, 忽略表面差异 — Gentner 结构映射）。"
    ),
    "forward_mask": (
        "样本只给了结果/后果部分, 请猜测缺失的前置机制"
        "（缺什么导致了这个结果）— 前向掩盖。"
    ),
    "reverse_mask": (
        "样本只给了前置/起因部分, 请猜测可能的后果与应用场景"
        "（若前提成立, 会怎样）— 反向掩盖。"
    ),
    "far_transfer": (
        "把 A 域样本的经验尝试映射到 B 域样本（远迁移）: "
        "若 A 的判断准则成立, 在 B 中它对应什么? "
        "（暴露结构线索以提升迁移率 — Gick & Holyoak）。"
    ),
}

CANDIDATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pattern_desc": {"type": "string"},
                    "conditions": {"type": "string"},
                    "counterexample": {"type": "string"},
                    "reasoning_path": {"type": "string"},
                    "insight_score": {"type": "number"},
                },
                "required": ["pattern_desc", "conditions",
                             "counterexample", "reasoning_path"],
            },
        }
    },
    "required": ["candidates"],
}

VERDICT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "keep": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "insight_score": {"type": "number"},
                    "information_value": {"type": "number"},
                },
                "required": ["index", "keep", "reason", "insight_score",
                             "information_value"],
            },
        }
    },
    "required": ["verdicts"],
}

MATCH_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "matches": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["matches"],
}

COVERAGE_MIN = 0.60
COVERAGE_MAX = 0.80
MIN_SAMPLES = 3
VERIFY_SAMPLE_SIZE_MAX = 20  # 反推采样上限（成本护栏）


class HeuristicDistiller:
    """变化驱动的二阶抽象提炼管道。"""

    def __init__(self, llm_provider=None, inventory: Optional[HeuristicInventory] = None,
                 trace_store=None, verify_sample_size: int = 12):
        """verify_sample_size: 反推验证采样数（LLM 成本优化, 默认 12;
        采样越大覆盖率估计越稳, 成本线性上升）。"""
        self._llm = llm_provider
        self._inventory = inventory or HeuristicInventory()
        self._trace_store = trace_store
        self._verify_sample_size = max(4, min(VERIFY_SAMPLE_SIZE_MAX,
                                              int(verify_sample_size)))
        self._runs = 0

    # ── 触发入口（变化驱动） ────────────────────────────────

    def try_distill(self, reason: str = "", samples: Optional[List[Dict[str, Any]]] = None,
                    context: str = "", variant: str = "commonalize") -> Dict[str, Any]:
        """变化触发入口: 失败/用户纠正/公理冲突/活性/缺公理感 → 提炼。"""
        samples = samples or self._collect_samples()
        if len(samples) < MIN_SAMPLES:
            return {"triggered": False, "reason": "insufficient_samples",
                    "collected": len(samples)}
        if self._llm is None:
            return self._rule_baseline(samples)

        self._runs += 1
        try:
            candidates = self._diverge(samples, variant)
            kept = self._converge(candidates, samples)
            expanded = self._counterfactual(kept, samples)
            verified: List[Heuristic] = []
            for cand in expanded:
                coverage = self._verify(cand, samples)
                if COVERAGE_MIN <= coverage <= COVERAGE_MAX:
                    h = self._candidate_to_heuristic(cand, coverage)
                    if self._inventory.add(h):
                        verified.append(h)
            logger.info("Distill[%s]: candidates=%d kept=%d expanded=%d verified=%d",
                        variant, len(candidates), len(kept), len(expanded), len(verified))
            return {
                "triggered": True, "reason": reason, "runs": self._runs,
                "candidates": len(candidates), "kept": len(kept),
                "expanded": len(expanded), "verified": len(verified),
                "heuristics": [h.heuristic_id for h in verified],
            }
        except Exception as e:
            logger.debug("distill failed: %s", e)
            return {"triggered": True, "error": str(e)[:120], "verified": 0}

    # ── 样本收集（全模块原料） ──────────────────────────────

    def _collect_samples(self, limit: int = 20) -> List[Dict[str, Any]]:
        samples: List[Dict[str, Any]] = []
        if self._trace_store is not None:
            for t in self._trace_store.get_all():
                samples.append({
                    "intent": getattr(t, "intent", ""),
                    "tool_sequence": list(getattr(t, "tool_sequence", [])),
                    "strategy": getattr(t, "strategy", ""),
                    "node_count": getattr(t, "node_count", 0),
                })
        return samples[:limit]

    # ── 发散（部分信息猜测家族, temp=0.8 调先验） ────────────

    def _diverge(self, samples: List[Dict[str, Any]], variant: str) -> List[Dict[str, Any]]:
        seeds = "\n\n".join(h.format_for_prompt() for h in SEED_HEURISTICS[:2])
        prompt = (
            "你是二阶抽象引擎: 从决策样本中提炼'判断准则'（启发）。\n"
            f"结构模板: {STRUCTURE_TEMPLATE}\n\n"
            f"示范种子（启发该长什么样）:\n{seeds}\n\n"
            f"发散变体: {DIVERGE_VARIANTS.get(variant, DIVERGE_VARIANTS['commonalize'])}\n\n"
            f"决策样本:\n{json.dumps(samples, ensure_ascii=False)[:4000]}\n\n"
            "请生成 3-5 个候选启发, 每个含 pattern_desc/conditions/"
            "counterexample/reasoning_path/insight_score(0-1)。"
            "输出 JSON: {\"candidates\": [...]}"
        )
        data = self._llm_call(prompt, temperature=0.8, schema=CANDIDATE_SCHEMA)
        candidates = (data or {}).get("candidates", []) if isinstance(data, dict) else []
        return candidates[:5]

    # ── 收敛（暴露全上下文, temp=0.1 筛选 + 拒绝理由） ───────

    def _converge(self, candidates: List[Dict[str, Any]],
                  samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        prompt = (
            "你是二阶抽象验证器: 用完整上下文验证候选启发。\n"
            f"完整决策上下文:\n{json.dumps(samples, ensure_ascii=False)[:4000]}\n\n"
            f"候选启发:\n{json.dumps(candidates, ensure_ascii=False)[:3000]}\n\n"
            "逐候选判定: keep(true/false) + reason(拒绝理由=知识边界) + "
            "insight_score(0-1, 综合洞察) + information_value(0-1, 语义价值: "
            "新颖性/可迁移性/是否揭示机制 — 不因低频就高, 垃圾=低值)。"
            "输出 JSON: {\"verdicts\": [...]}"
        )
        data = self._llm_call(prompt, temperature=0.1, schema=VERDICT_SCHEMA)
        verdicts = (data or {}).get("verdicts", []) if isinstance(data, dict) else []
        kept: List[Dict[str, Any]] = []
        for v in verdicts:
            idx = int(v.get("index", -1))
            if 0 <= idx < len(candidates) and v.get("keep"):
                cand = dict(candidates[idx])
                cand["insight_score"] = float(v.get("insight_score", 0.5))
                cand["information_value"] = float(v.get("information_value", 0.5))
                cand["_reject_reason"] = v.get("reason", "")
                kept.append(cand)
        return kept

    # ── 反事实扩展（低 coverage 高 insight → 主动构造连锁猜想） ──

    def _counterfactual(self, candidates: List[Dict[str, Any]],
                        samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对高洞察候选（insight>=0.7）构造'若启发为真→哪些行为该变',
        在样本中找证据连接, 更新 reasoning_path。"""
        expanded: List[Dict[str, Any]] = []
        for cand in candidates:
            if float(cand.get("insight_score", 0.0)) < 0.7:
                expanded.append(cand)
                continue
            prompt = (
                "你是反事实扩展器: 启发 coverage 可能偏低但洞察高 — "
                "构造'如果该启发为真 → 哪些行为应该改变', "
                "再在决策样本中找支持/反对的证据连接。\n\n"
                f"启发:\n{json.dumps(cand, ensure_ascii=False)[:2000]}\n\n"
                f"决策样本:\n{json.dumps(samples, ensure_ascii=False)[:3000]}\n\n"
                "输出 JSON: {\"reasoning_path\": \"扩展后的推理路径(引用证据)\", "
                "\"evidence\": [\"样本i 支持/反对: 理由\"], \"updated_insight\": 0.8}"
            )
            data = self._llm_call(prompt, temperature=0.3)
            if isinstance(data, dict) and data.get("reasoning_path"):
                cand["reasoning_path"] = (
                    f"{cand.get('reasoning_path', '')}\n"
                    f"[反事实] {data['reasoning_path']}"
                )
                cand["insight_score"] = float(data.get("updated_insight", cand.get("insight_score", 0.5)))
            expanded.append(cand)
        return expanded

    # ── 反推验证（LLM 采样, coverage 60-80%） ───────────────

    def _verify(self, cand: Dict[str, Any], samples: List[Dict[str, Any]]) -> float:
        batch = random.sample(samples, min(self._verify_sample_size, len(samples)))
        heur_text = (
            f"现象: {cand.get('pattern_desc', '')}\n"
            f"适用: {cand.get('conditions', '')}\n"
            f"路径: {cand.get('reasoning_path', '')}"
        )
        prompt = (
            "你是启发覆盖率验证器: 判断启发能否解释给定的历史决策。\n\n"
            f"启发:\n{heur_text}\n\n"
            f"历史决策样本（逐条判定 能解释=1 不能=0）:\n"
            f"{json.dumps(batch, ensure_ascii=False)[:4000]}\n\n"
            "输出 JSON: {\"matches\": [1,0,1,...]} 长度与样本数一致"
        )
        data = self._llm_call(prompt, temperature=0.1, schema=MATCH_SCHEMA)
        matches = (data or {}).get("matches", []) if isinstance(data, dict) else []
        if not matches:
            return 0.0
        return sum(1 for m in matches if int(m) > 0) / len(matches)

    # ── 沉淀 ───────────────────────────────────────────────

    @staticmethod
    def _candidate_to_heuristic(cand: Dict[str, Any], coverage: float) -> Heuristic:
        import time
        return Heuristic(
            heuristic_id=f"h_d_{abs(hash((cand.get('pattern_desc', '') or '')[:32])) % 10**8}_{int(time.time() % 10**5)}",
            pattern_desc=str(cand.get("pattern_desc", ""))[:300],
            conditions=str(cand.get("conditions", ""))[:300],
            counterexample=str(cand.get("counterexample", ""))[:300],
            reasoning_path=str(cand.get("reasoning_path", ""))[:600],
            coverage=round(coverage, 3),
            support=1,
            insight_score=float(cand.get("insight_score", 0.5)),
            source="distilled",
        )

    # ── 规则兜底（无 LLM, 冷启动） ──────────────────────────

    def _rule_baseline(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """规则聚类兜底（增强: P×I 信息论路由, CompressionRouter 语义）.

        原实现只数"完全相同序列"（覆盖窄）; 现在按频率 P × 意图价值 I 路由:
          P(≥0.5) → aggregate（高频聚合, 可复用链路, 覆盖高）
          P(<0.3) 且 意图独特 → preserve（低频高价值, 保留链路, 覆盖低）
          其余 → filter（不沉淀）
        对齐博客 §8.5（Shannon 自信息分治: 高概率凝练 / 低概率保留）。
        """
        seq_counts: Dict[tuple, int] = {}
        seq_intents: Dict[tuple, set] = {}
        for s in samples:
            tools = getattr(s, "tool_sequence", None)
            if tools is None and isinstance(s, dict):
                tools = s.get("tool_sequence", [])
            tools = tuple(tools or [])
            if len(tools) >= 2:
                seq_counts[tools] = seq_counts.get(tools, 0) + 1
                intent = (getattr(s, "intent", None)
                          or (s.get("intent", "") if isinstance(s, dict) else ""))
                seq_intents.setdefault(tools, set()).add(intent or "general")
        total = len(samples) or 1
        added = 0
        for seq, count in seq_counts.items():
            freq = count / total
            semantic_value = self._semantic_value_proxy(
                intent_count=len(seq_intents.get(seq, set())),
                seq_len=len(seq),
                total_seqs=len(seq_counts),
            )
            route = self._info_route(freq, semantic_value)
            if route == "filter":
                continue
            h = Heuristic(
                heuristic_id=f"h_rule_{abs(hash(seq)) % 10**6}",
                pattern_desc=f"工具链 {' → '.join(seq)}（{count} 次, 频率 {freq:.0%}）",
                conditions=("同类意图下工具链路可复用（高频聚合）"
                            if route == "aggregate"
                            else "低频高价值场景保留该链路（信息论路由）"),
                counterexample="场景变化或工具失效时不应机械复用",
                reasoning_path=("信息论路由 P×I（CompressionRouter 语义）: "
                                "高频 → 聚合凝练 / 低频高价值 → 保留"
                                if route == "preserve"
                                else "规则聚类兜底（无 LLM）: 高频序列计数"),
                coverage=0.65 if route == "aggregate" else 0.55,
                support=count, source="rule",
            )
            if self._inventory.add(h):
                added += 1
        return {"triggered": True, "mode": "rule", "added": added,
                "scanned": len(samples)}

    @staticmethod
    def _info_route(frequency: float, semantic_value: float = 0.0) -> str:
        """信息论路由（P×I, 2026-08-07 修正）:
          频率 ≥0.5 → aggregate（高频凝练）;
          频率 <0.3 且 语义价值 ≥0.6 → preserve（低频高价值, 深路径保留）;
          低频低价值 → filter（不因稀有而保留 — 用户深化: 单频率太粗糙）;
          其余 → filter。"""
        if frequency >= 0.5:
            return "aggregate"
        if frequency < 0.3 and semantic_value >= 0.6:
            return "preserve"
        return "filter"

    @staticmethod
    def _semantic_value_proxy(intent_count: int, seq_len: int, total_seqs: int) -> float:
        """语义价值代理（无 LLM 规则兜底用）:
          意图多样性（多意图共用 = 更可能揭示通用机制）+
          序列新颖度（序列总数少 = 罕见但可能高价值）+
          序列长度（长链路 = 更复杂, 更值得沉淀）。"""
        intent_score = min(1.0, intent_count / 3.0)
        novelty = min(1.0, total_seqs / 5.0) if total_seqs > 0 else 0.0
        length_score = min(1.0, seq_len / 5.0)
        return round(0.5 * intent_score + 0.3 * novelty + 0.2 * length_score, 3)

    # ── LLM 调用辅助 ────────────────────────────────────────

    def _llm_call(self, prompt: str, temperature: float,
                  schema: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        from core.agent.llm_providers.base import GenerateRequest
        req = GenerateRequest(
            prompt=prompt,
            temperature=temperature,
            max_tokens=1500,
            timeout_ms=60000,
            response_format="json",
            json_schema=schema,
            metadata={"purpose": "heuristic_distill"},
        )
        result = self._llm.generate(req)
        if result.structured is not None:
            return result.structured
        return None
