"""HeuristicInventory — 二阶抽象启发库存（A24 / blog chapter3）.

启发 = 决策依据（与约束同构）, 注入上下文出现在所有决策处。
单元 = 四元组链: 现象(pattern_desc) → 起源/操作化(reasoning_path)
               → 边界(conditions) + 反例(counterexample)。

种子 ≠ 公理清单（2026-08-07 用户修正）:
  - wise 公理是项目内提炼产物（目标形态）, 当种子会自我印证闭环
  - 种子 = 认知结构模板（现象→起源→边界→操作化）+ 示范种子 few-shot
  - 示范种子是生成规范样板, 不是注入的公理

质量判据: 锚定形式科学约束空间（逻辑/集合/映射/概率公理）→
底层性 = 可迁移性 = 过时风险低。
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

INVENTORY_FILE = os.path.join("data", "heuristics.json")

# 结构模板（提炼管道输出规范）: 现象 → 起源/机制 → 边界 → 操作化
STRUCTURE_TEMPLATE = (
    "启发必须符合完整认知链: 现象(模式描述) → 起源(为什么/机制, 含操作化) "
    "→ 边界(适用条件) + 反例(何时不成立)。"
    "优先锚定形式科学约束空间（逻辑/集合/映射/图/概率公理）, "
    "锚定越深 → 可迁移性越高、过时风险越低。"
)


@dataclass
class Heuristic:
    """启发单元（四元组链 + belief）。"""
    heuristic_id: str
    pattern_desc: str          # 现象: 模式描述
    conditions: str            # 边界: 适用条件
    counterexample: str        # 反例: 何时不成立
    reasoning_path: str        # 起源 + 操作化: 推理路径
    coverage: float = 0.0      # 反推覆盖率（60-80% 合格; 100%=过拟合, 0%=幻觉）
    support: int = 0           # 支持样本数
    insight_score: float = 0.0 # 洞察力（收敛步骤 LLM 评分）
    source: str = "seed"       # seed | axiom | distilled | rule
    active: bool = True
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "heuristic_id": self.heuristic_id,
            "pattern_desc": self.pattern_desc,
            "conditions": self.conditions,
            "counterexample": self.counterexample,
            "reasoning_path": self.reasoning_path,
            "coverage": self.coverage,
            "support": self.support,
            "insight_score": self.insight_score,
            "source": self.source,
            "active": self.active,
            "ts": self.ts,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Heuristic":
        return Heuristic(
            heuristic_id=d.get("heuristic_id", ""),
            pattern_desc=d.get("pattern_desc", ""),
            conditions=d.get("conditions", ""),
            counterexample=d.get("counterexample", ""),
            reasoning_path=d.get("reasoning_path", ""),
            coverage=float(d.get("coverage", 0.0)),
            support=int(d.get("support", 0)),
            insight_score=float(d.get("insight_score", 0.0)),
            source=d.get("source", "distilled"),
            active=bool(d.get("active", True)),
            ts=float(d.get("ts", time.time())),
        )

    def format_for_prompt(self) -> str:
        """注入上下文的单条格式（与 engineering 约束并列）。"""
        return (
            f"• {self.pattern_desc}（{self.source}, 覆盖 {self.coverage:.0%}）"
            f"\n  适用: {self.conditions}"
            f"\n  反例: {self.counterexample}"
            f"\n  路径: {self.reasoning_path}"
        )


# ── 示范种子（few-shot 样板, 2026-08-07 用户深化） ──────────────────

SEED_HEURISTICS: List[Heuristic] = [
    Heuristic(
        heuristic_id="h_seed_diff",
        pattern_desc="差异即信息：低概率/异常/罕见现象携带信息而非噪声",
        conditions="出现低概率事件、异常值、反例时；前提是存在可比较的参照系",
        counterexample="无参照的孤立观察（孤岛）——无比较则差异无意义，不应强行解读",
        reasoning_path=(
            "起源: 差异源自比较，孤岛（无参照）时关系从比较中产生，没有参照差异无意义；"
            "哪怕内禀视角本身也是一种参照。"
            "操作化: 统一化相对化——把绝对断言转为相对参照系的断言，看似矛盾即可统一"
            "（卡尔曼'低概率=噪声'与信息论'低概率=高信息'统一于'能否被现有模型解释'）。"
            "锚定: 信息量 I=-log₂P 的相对性（概率公理）。"
        ),
        coverage=0.70,
        insight_score=0.95,
        source="seed",
    ),
    Heuristic(
        heuristic_id="h_seed_classify",
        pattern_desc="共性边界即分类：分析共性（集合内）与边界（集合外）即完成分类，分类后可转向集合操作",
        conditions="面对多个相似对象/模式需要抽象或批量处理时",
        counterexample="对象在同一参考维度下无真实共性（伪分类）；分类必须完备互斥（排中律），否则不产生准确性",
        reasoning_path=(
            "起源: 共性是某参考维度下的性质，边界也在此维度下探讨（相对化）。"
            "边界: 分类可追溯到排中律（A 或非 A），完备互斥是准确性源头。"
            "操作化: 分类后从个体操作转向集合操作（模板化/批量/分治）。"
            "锚定: 映射关系（多对一/一对一/一对多/多对多）约束空间有限完备；"
            "对形式模型的研究再研究（自指递归抽象）使内容深且抽象。"
        ),
        coverage=0.70,
        insight_score=0.95,
        source="seed",
    ),
]


class HeuristicInventory:
    """启发库存: 存储 / 检索 / 注入格式化 / 持久化。"""

    def __init__(self, path: str = INVENTORY_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._items: Dict[str, Heuristic] = {}
        self._load()
        self._seed_if_empty()

    # ── 持久化 ─────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for d in data if isinstance(data, list) else []:
                    h = Heuristic.from_dict(d)
                    if h.heuristic_id:
                        self._items[h.heuristic_id] = h
        except Exception:
            pass

    def _persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([h.to_dict() for h in self._items.values()],
                          f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            pass

    def _seed_if_empty(self) -> None:
        if not self._items:
            for h in SEED_HEURISTICS:
                self._items[h.heuristic_id] = h
            self._persist()

    # ── 操作 ───────────────────────────────────────────────

    def add(self, h: Heuristic) -> bool:
        if not h.heuristic_id or not h.pattern_desc:
            return False
        with self._lock:
            self._items[h.heuristic_id] = h
            self._persist()
        return True

    def get(self, heuristic_id: str) -> Optional[Heuristic]:
        return self._items.get(heuristic_id)

    def all(self, active_only: bool = True) -> List[Heuristic]:
        with self._lock:
            items = [h for h in self._items.values()
                     if (not active_only or h.active)]
        return sorted(items, key=lambda h: h.insight_score, reverse=True)

    def deactivate(self, heuristic_id: str, reason: str = "") -> bool:
        h = self._items.get(heuristic_id)
        if h is None:
            return False
        h.active = False
        self._persist()
        return True

    def stats(self) -> Dict[str, Any]:
        items = self.all(active_only=False)
        active = [h for h in items if h.active]
        by_source: Dict[str, int] = {}
        for h in items:
            by_source[h.source] = by_source.get(h.source, 0) + 1
        return {
            "total": len(items),
            "active": len(active),
            "by_source": by_source,
            "avg_coverage": round(
                sum(h.coverage for h in items) / len(items), 3) if items else 0.0,
            "avg_insight": round(
                sum(h.insight_score for h in items) / len(items), 3) if items else 0.0,
        }

    def check_health(self, threshold: float = 0.5) -> List[Heuristic]:
        """活性监测: active 且 coverage < 阈值 的蒸馏/规则启发（种子不查）。

        种子（人类常识示范）人为维护, 不自动停用; 蒸馏/规则启发覆盖跌破
        阈值 → stale（启发过时信号, 触发再抽象）。
        """
        stale: List[Heuristic] = []
        for h in self._items.values():
            if (h.active and h.source in ("distilled", "rule")
                    and h.coverage < threshold):
                stale.append(h)
        return stale

    def deactivate_stale(self, threshold: float = 0.5) -> List[str]:
        """批量停用活性不足的启发（A24 启发过时 → 再触发）。"""
        stale = self.check_health(threshold)
        if not stale:
            return []
        with self._lock:
            for h in stale:
                h.active = False
            self._persist()
        return [h.heuristic_id for h in stale]

    # ── 检索 / 注入 ────────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> List[Heuristic]:
        """关键词重叠检索（决策点注入用; 词元集合相似度）。"""
        if not query.strip():
            return self.all(active_only=True)[:top_k]
        q_tokens = set(_tokenize(query))
        scored: List[tuple] = []
        for h in self.all(active_only=True):
            hay = _tokenize(f"{h.pattern_desc} {h.conditions} {h.reasoning_path}")
            if not hay:
                continue
            overlap = len(q_tokens & hay) / max(1, len(q_tokens | hay))
            # 洞察力加权: 相关性 × 0.7 + insight × 0.3
            score = overlap * 0.7 + min(1.0, h.insight_score) * 0.3
            scored.append((score, h))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored[:top_k]]

    def format_for_prompt(self, query: str = "", top_k: int = 4) -> str:
        """注入格式化: 与 engineering 约束并列的决策依据块。"""
        hits = self.search(query, top_k)
        if not hits:
            return ""
        lines = ["[决策依据]", *[h.format_for_prompt() for h in hits]]
        return "\n".join(lines)


def _tokenize(text: str) -> set:
    """简单词元化（中英文混合: 中文按字符二元组, 英文按词）。"""
    import re
    tokens: set = set()
    for w in re.findall(r"[a-zA-Z_0-9]+", text.lower()):
        tokens.add(w)
    for seg in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(seg) == 1:
            tokens.add(seg)
        else:
            for i in range(len(seg) - 1):
                tokens.add(seg[i:i + 2])
    return tokens
