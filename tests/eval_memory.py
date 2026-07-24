"""Memory Evaluation Framework — 3-level benchmark for XML Memory Cards.

Level 1: Single-session fact recall
Level 2: Cross-session multi-entity retrieval
Level 3: Proactive service (plan prediction + anomaly detection)

Modeled after: LoCoMo (2024), GateMem, AI Agent Book Ch3 三层次框架
Backend: XML Memory Cards → extract → store → retrieve → LLM-as-Judge
"""

from __future__ import annotations
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import json, time, logging

logger = logging.getLogger(__name__)


@dataclass
class EvalSession:
    """One conversation session in an evaluation scenario."""
    session_id: str
    turns: List[Dict]               # [{role: "user", content: "..."}, ...]
    expected_memories: List[Dict]    # what should be remembered
    metadata: Dict = field(default_factory=dict)  # {labels, complexity, ...}


@dataclass
class EvalScenario:
    """A complete evaluation scenario — multi-session narrative."""
    scenario_id: str
    name: str
    level: int                      # 1, 2, or 3
    sessions: List[EvalSession]
    final_query: str                # question to ask after all sessions
    expected_answer: str            # ground truth
    answer_rubric: List[str]        # key points that must appear in answer


@dataclass
class EvalResult:
    scenario_id: str
    level: int
    agent_answer: str
    expected_answer: str
    score: float                    # 0-1, from LLM judge
    memories_generated: int
    memories_recalled: int
    rubric_hits: List[str]
    rubric_misses: List[str]


# ── Evaluation Suite ──

class MemoryEvaluator:
    """Run 3-level memory evaluation against our XML memory backend.

    Usage:
        eval = MemoryEvaluator(memory_extract_fn, memory_retrieve_fn)
        results = eval.run_all(scenarios)
    """

    def __init__(self, memory_extract_fn=None, memory_retrieve_fn=None, 
                 judge_fn=None):
        self.extract = memory_extract_fn      # (conversation_text) → List[MemoryCard]
        self.retrieve = memory_retrieve_fn    # (query) → str (context)
        self.judge = judge_fn or self._default_judge

    def run(self, scenario: EvalScenario) -> EvalResult:
        """Run one scenario: sessions → memories → query → judge."""
        all_memories = []
        total_generated = 0

        # Process each session sequentially
        for session in scenario.sessions:
            conversation = self._format_conversation(session.turns)
            if self.extract:
                memories = self.extract(conversation)
                all_memories.extend(memories)
                total_generated += len(memories)

        # Retrieve memories for final query
        context = ""
        if self.retrieve:
            context = self.retrieve(scenario.final_query)

        # LLM answers with retrieved context
        agent_answer = self._generate_answer(scenario.final_query, context)

        # Judge
        rubric_hits, rubric_misses, score = self.judge(
            agent_answer, scenario.expected_answer, scenario.answer_rubric
        )

        return EvalResult(
            scenario_id=scenario.scenario_id,
            level=scenario.level,
            agent_answer=agent_answer,
            expected_answer=scenario.expected_answer,
            score=score,
            memories_generated=total_generated,
            memories_recalled=len(all_memories),
            rubric_hits=rubric_hits,
            rubric_misses=rubric_misses,
        )

    def run_all(self, scenarios: List[EvalScenario]) -> Dict:
        """Run all scenarios, return aggregate results."""
        results = []
        for s in scenarios:
            results.append(self.run(s))

        by_level = defaultdict(list)
        for r in results:
            by_level[r.level].append(r)

        return {
            "total_scenarios": len(results),
            "overall_score": sum(r.score for r in results) / max(1, len(results)),
            "by_level": {
                level: {
                    "count": len(level_results),
                    "avg_score": sum(r.score for r in level_results) / len(level_results),
                    "avg_hits": sum(len(r.rubric_hits) for r in level_results) / len(level_results),
                }
                for level, level_results in by_level.items()
            },
            "details": [
                {
                    "scenario_id": r.scenario_id,
                    "level": r.level,
                    "score": r.score,
                    "rubric_hits": r.rubric_hits,
                    "rubric_misses": r.rubric_misses,
                }
                for r in results
            ],
        }

    @staticmethod
    def _format_conversation(turns: List[Dict]) -> str:
        return "\n".join(f"{t['role']}: {t['content']}" for t in turns)

    def _generate_answer(self, query: str, context: str) -> str:
        """Generate answer with context. Override with LLM call in production."""
        # Mock: in production this would call LLM
        return f"[Context: {context[:200]}]\nAnswer to: {query}"

    def _default_judge(self, answer: str, expected: str, 
                       rubric: List[str]) -> Tuple[List[str], List[str], float]:
        """Simple keyword-overlap judge. Replace with LLM-as-Judge in production."""
        answer_lower = answer.lower()
        hits = [r for r in rubric if r.lower() in answer_lower]
        misses = [r for r in rubric if r.lower() not in answer_lower]
        score = len(hits) / max(1, len(rubric))
        return hits, misses, score


# ── Built-in Test Scenarios ──

def build_standard_scenarios() -> List[EvalScenario]:
    """Construct 3-level evaluation scenarios per AI Agent Book framework."""

    # === Level 1: Basic Recall (单会话, 简单事实) ===
    l1_scenarios = [
        EvalScenario(
            scenario_id="L1_001_simple_fact",
            name="Simple Fact Recall",
            level=1,
            sessions=[
                EvalSession(
                    session_id="s1",
                    turns=[
                        {"role": "user", "content": "我的会员号是 UA-12345678"},
                        {"role": "assistant", "content": "已记录您的会员号"},
                    ],
                    expected_memories=[{"type": "fact", "key": "mileageplus", "value": "UA-12345678"}],
                ),
            ],
            final_query="我的会员号是多少？",
            expected_answer="UA-12345678",
            answer_rubric=["UA-12345678", "会员号"],
        ),
        EvalScenario(
            scenario_id="L1_002_preference",
            name="Simple Preference",
            level=1,
            sessions=[
                EvalSession(
                    session_id="s1",
                    turns=[
                        {"role": "user", "content": "我订机票都要靠窗的座位，我是素食者"},
                        {"role": "assistant", "content": "了解了，靠窗+素食餐"},
                    ],
                    expected_memories=[
                        {"type": "preference", "domain": "travel", "key": "seat", "value": "window"},
                        {"type": "preference", "domain": "travel", "key": "meal", "value": "vegetarian"},
                    ],
                ),
            ],
            final_query="帮我订一趟去东京的航班",
            expected_answer="靠窗座位+素食餐已为您安排",
            answer_rubric=["靠窗", "素食", "东京"],
        ),
    ]

    # === Level 2: Cross-Session Multi-Entity (跨会话, 多实体) ===
    l2_scenarios = [
        EvalScenario(
            scenario_id="L2_001_two_cars",
            name="Two Cars Service",
            level=2,
            sessions=[
                EvalSession(session_id="s1", turns=[
                    {"role": "user", "content": "我的特斯拉 Model 3 需要保养，车牌京A12345"},
                    {"role": "assistant", "content": "已记录特斯拉保养需求"},
                ], expected_memories=[{"type": "fact", "key": "car_1", "value": "Tesla Model 3 京A12345"}]),
                EvalSession(session_id="s2", turns=[
                    {"role": "user", "content": "对了我的宝马 X5 也该保养了，车牌京B67890"},
                    {"role": "assistant", "content": "已记录宝马保养需求"},
                ], expected_memories=[{"type": "fact", "key": "car_2", "value": "BMW X5 京B67890"}]),
            ],
            final_query="帮我的车预约保养",
            expected_answer="您有两辆车：Tesla Model 3(京A12345)和BMW X5(京B67890)，请问为哪辆预约？",
            answer_rubric=["两辆车", "Tesla", "BMW", "请问哪辆"],
        ),
        EvalScenario(
            scenario_id="L2_002_cancel_trip",
            name="Cancel Composite Trip",
            level=2,
            sessions=[
                EvalSession(session_id="s1", turns=[
                    {"role": "user", "content": "订一趟去洛杉矶的机票，3月15日"},
                    {"role": "assistant", "content": "已预订LAX机票"},
                ], expected_memories=[{"type": "event", "category": "travel", "key": "la_trip", "value": "机票"}]),
                EvalSession(session_id="s2", turns=[
                    {"role": "user", "content": "再订洛杉矶机场附近酒店，3月15-20日"},
                    {"role": "assistant", "content": "已预订酒店"},
                ], expected_memories=[{"type": "event", "category": "travel", "key": "la_trip", "value": "酒店"}]),
            ],
            final_query="取消我的洛杉矶之旅",
            expected_answer="已取消洛杉矶机票和酒店预订（3月15-20日）",
            answer_rubric=["取消", "机票", "酒店", "洛杉矶"],
        ),
    ]

    # === Level 3: Proactive Service (跨会话推理, 主动帮助) ===
    l3_scenarios = [
        EvalScenario(
            scenario_id="L3_001_passport_expiry",
            name="Passport Expiry Warning",
            level=3,
            sessions=[
                EvalSession(session_id="s1", turns=[
                    {"role": "user", "content": "我的护照号是E12345678，有效期到2025年6月"},
                    {"role": "assistant", "content": "已记录护照信息"},
                ], expected_memories=[{"type": "fact", "key": "passport", "value": "E12345678 expires 2025-06"}]),
                EvalSession(session_id="s2", turns=[
                    {"role": "user", "content": "现在几月了？"},
                    {"role": "assistant", "content": "现在是2025年3月"},
                ], expected_memories=[]),
            ],
            final_query="帮我订一趟国际航班，3个月后的",
            expected_answer="已预订国际航班。⚠️提醒：您的护照E12345678将于2025年6月到期，建议提前办理续签",
            answer_rubric=["护照", "到期", "提醒", "续签"],
        ),
        EvalScenario(
            scenario_id="L3_002_family_health",
            name="Family Annual Checkup",
            level=3,
            sessions=[
                EvalSession(session_id="s1", turns=[
                    {"role": "user", "content": "我妈妈有高血压，每3个月需要复查一次"},
                    {"role": "assistant", "content": "已记录阿姨健康情况"},
                ], expected_memories=[{"type": "person", "entity": "妈妈", "health": "高血压"}]),
                EvalSession(session_id="s2", turns=[
                    {"role": "user", "content": "我爸最近膝盖不舒服，应该是老毛病了"},
                    {"role": "assistant", "content": "已记录叔叔情况"},
                ], expected_memories=[{"type": "person", "entity": "爸爸", "health": "膝盖"}]),
            ],
            final_query="最近该安排什么医疗事项吗？",
            expected_answer="建议：①您妈妈的3个月复查（上次未记录时间，可能需要安排）；②您爸爸的膝盖问题可以预约骨科",
            answer_rubric=["妈妈", "爸爸", "复查", "膝盖", "安排"],
        ),
    ]

    return l1_scenarios + l2_scenarios + l3_scenarios
