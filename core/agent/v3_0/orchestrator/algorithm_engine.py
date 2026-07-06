# -*- coding: utf-8 -*-
"""
core/agent/v3_0/orchestrator/algorithm_engine.py
++++++
DialogMesh v3.0 AlgorithmEngine — 算法引擎（认知双工中的"快思考"侧）。

职责：
  - 基于规则的快速 PCR 分析（噪声检测、期望推断）
  - 基于关键词/模式的快速意图解析
  - 为 HybridEngine 提供低延迟的算法侧结果

设计原则：
  - 纯同步：所有方法为同步调用，适配 ThreadPoolExecutor 并行执行
  - 低延迟：所有方法应在 <10ms 内完成
  - 可预测：给定相同输入，一定产生相同输出（确定性）
  - Fallback 优先：当 LLM 不可用时，算法引擎提供兜底能力

对应工程文档：ENGINEERING_MULTILAYER_LLM.md §5.1, §7.1
版本：3.0.0
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================

class AlgorithmResult:
    """算法引擎的通用输出结构。"""

    def __init__(
        self,
        output: Optional[Dict[str, Any]] = None,
        confidence: float = 0.5,
        source_label: str = "algorithm",
        clarification_required: bool = False,
        fallback_reason: Optional[str] = None,
    ):
        self.output = output or {}
        self.confidence = confidence
        self.source_label = source_label
        self.clarification_required = clarification_required
        self.fallback_reason = fallback_reason


# ============================================================
# 噪声检测器
# ============================================================

class NoiseDetector:
    """基于规则的三维度噪声检测。

    设计文档定义：
      N = alpha * N_semantic + beta * N_structural + gamma * N_referential
      alpha=0.5, beta=0.3, gamma=0.2（默认权重）
    """

    _FILLER_WORDS = {
        "的", "了", "是", "在", "有", "就", "和", "这", "那", "也", "还",
        "啊", "哦", "嗯", "呢", "吧", "吗", "哈", "嘿", "喂",
    }
    _EMOJI_PATTERN = re.compile(r"[😀-🙏🌀-🗿🚀-🛸🌟-💯]+", re.UNICODE)
    _SYMBOL_ONLY = re.compile(r"^[\s!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?~`。，、；：？！…—·￥""''（）【】《》]+$")

    def __init__(
        self,
        alpha: float = 0.5,
        beta: float = 0.3,
        gamma: float = 0.2,
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma

    def analyze(self, user_input: str) -> Dict[str, Any]:
        """对用户输入进行三维噪声分析。"""
        text = user_input.strip()
        semantic = self._calc_semantic_noise(text)
        structural = self._calc_structural_noise(text)
        referential = self._calc_referential_noise(text)
        overall = self.alpha * semantic + self.beta * structural + self.gamma * referential

        return {
            "semantic_noise": round(semantic, 3),
            "structural_noise": round(structural, 3),
            "referential_noise": round(referential, 3),
            "overall_noise": round(overall, 3),
        }

    def _calc_semantic_noise(self, text: str) -> float:
        """语义噪声：填充词密度 + 表情符号 + 极短输入"""
        if not text:
            return 0.8
        if self._SYMBOL_ONLY.match(text):
            return 1.0
        emoji_match = self._EMOJI_PATTERN.search(text)
        if emoji_match and len(text) < 10:
            return 0.9
        if len(text) < 3:
            return 0.7
        words = text.split()
        if not words:
            chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
            if not chars:
                return 0.3
            filler_count = sum(1 for c in chars if c in self._FILLER_WORDS)
            filler_density = filler_count / len(chars) if chars else 0.0
        else:
            filler_count = sum(1 for w in words if w in self._FILLER_WORDS)
            filler_density = filler_count / len(words) if words else 0.0
        return round(min(1.0, filler_density * 2.0), 3)

    def _calc_structural_noise(self, text: str) -> float:
        """结构噪声：语法混乱度、格式异常"""
        if not text:
            return 0.8
        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', text))
        has_english = bool(re.search(r'[a-zA-Z]{2,}', text))
        repeated = re.search(r'(.)\1{3,}', text)
        abnormal_punct = len(re.findall(r'[!@#$%^&*+=]{2,}', text))
        score = 0.0
        if has_chinese and has_english and not text.startswith(('0x', 'pid', 'proc')):
            score += 0.3
        if repeated:
            score += 0.3
        if abnormal_punct > 0:
            score += min(0.4, abnormal_punct * 0.1)
        if len(text) > 500:
            score += 0.2
        if has_english and re.search(r'0x[0-9a-fA-F]+', text):
            score = max(0.0, score - 0.2)
        return round(min(1.0, score), 3)

    def _calc_referential_noise(self, text: str) -> float:
        """指代噪声：代词使用密度"""
        if not text:
            return 0.5
        pronouns = {"它", "他", "她", "它们", "他们", "她们", "这", "那",
                     "这个", "那个", "这些", "那些", "这里", "那里", "这么", "那么"}
        chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
        if not chars:
            return 0.2
        pronoun_count = sum(text.count(p) for p in pronouns)
        pronoun_density = pronoun_count / max(1, len(chars))
        return round(min(1.0, pronoun_density * 3.0), 3)


# ============================================================
# 期望推断器
# ============================================================

class ExpectationInferencer:
    """基于模式匹配的期望推断 TOOL / ADVISOR / COMPANION。"""

    _TOOL_PATTERNS = [
        r'\b(read|write|scan|hack|patch|dump|inject|search|find|list|show|get|set|create|delete|update)\b',
        r'\b(0x[0-9a-fA-F]+)\b',
        r'\b(pid|proc|dll|exe|sys|drv)\b',
    ]
    _ADVISOR_PATTERNS = [
        r'\b(what|why|how|analyze|explain|review|check|evaluate|compare|difference|meaning)\b',
        r'\b(think|opinion|suggest|recommend|advise)\b',
        r'\b(code|bug|error|issue|problem|solution)\b',
    ]
    _COMPANION_PATTERNS = [
        r'\b(hi|hello|hey|good morning|good evening|how are you|what.up|sup)\b',
        r'\b(chat|talk|discuss|tell me about|let.s)\b',
        r'\b(like|love|hate|feel|think|wonder)\b',
    ]

    def infer(self, user_input: str, noise_analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """推断用户期望的响应模式。"""
        text = user_input.strip().lower()
        scores = {
            "TOOL": self._match_score(text, self._TOOL_PATTERNS),
            "ADVISOR": self._match_score(text, self._ADVISOR_PATTERNS),
            "COMPANION": self._match_score(text, self._COMPANION_PATTERNS),
        }
        if noise_analysis and noise_analysis.get("overall_noise", 0) > 0.7:
            for k in scores:
                scores[k] *= 0.5
        primary = max(scores, key=lambda k: scores[k])
        confidence = scores[primary]
        if confidence < 0.3:
            primary = "UNKNOWN"
        return {
            "primary": primary,
            "confidence": round(confidence, 3),
            "scores": {k: round(v, 3) for k, v in scores.items()},
        }

    def _match_score(self, text: str, patterns: List[str]) -> float:
        score = 0.0
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += 0.25
        return min(1.0, score)


# ============================================================
# 规则意图解析器
# ============================================================

class RuleBasedIntentParser:
    """基于关键词和模式的快速意图解析器。"""

    def __init__(self):
        self._rules: List[tuple] = [
            (r'\bscan\b', 'SCAN_MEMORY', 0.75),
            (r'\bread.*(mem|address|value)', 'READ_MEMORY', 0.80),
            (r'\bwrite.*(mem|address|value)', 'WRITE_MEMORY', 0.80),
            (r'\b(hack|patch|nop|inject)\b', 'HACK_VALUE', 0.75),
            (r'\b(cheat|speedhack|aobscan)\b', 'HACK_VALUE', 0.70),
            (r'\b(help|how.*use|tutorial|guide)\b', 'ASK_HELP', 0.85),
            (r'^(hi|hello|hey)\s*$', 'GREETING', 0.95),
            (r'\b(set|config|settings|preference)\b', 'SETTINGS', 0.70),
            (r'\b(analyze|explain|review|check)\b', 'ANALYZE', 0.65),
            (r'^(bye|exit|quit|goodbye)\s*$', 'EXIT', 0.95),
        ]

    def parse(self, user_input: str) -> Dict[str, Any]:
        """解析意图并返回结构化的意图推断。"""
        text = user_input.lower().strip()
        best_category = 'UNKNOWN'
        best_confidence = 0.40
        for pattern, category, conf_base in self._rules:
            if re.search(pattern, text, re.IGNORECASE):
                if conf_base > best_confidence:
                    best_category = category
                    best_confidence = conf_base
        matches = sum(1 for p, _, _ in self._rules if re.search(p, text, re.IGNORECASE))
        if matches > 2:
            ambiguity = "high"
        elif matches > 1:
            ambiguity = "medium"
        else:
            ambiguity = "low"
        return {
            "intent_inference": {
                "primary_intent": best_category,
                "confidence": round(best_confidence, 3),
                "ambiguity_assessment": ambiguity,
            },
            "confidence": round(best_confidence, 3),
        }


# ============================================================
# 认知快照生成器
# ============================================================

class CognitiveSnapshotGenerator:
    """基于启发式规则生成认知快照（元认知、发散性、稳定性）。"""

    def generate(self, user_input: str, noise: Dict[str, Any],
                 expectation: Dict[str, Any]) -> Dict[str, float]:
        text = user_input.strip()
        metacognition = 0.5
        if re.search(r'\b(why|how|compare|analyze|evaluate|difference)\b', text, re.IGNORECASE):
            metacognition += 0.2
        if expectation.get("primary") == "TOOL":
            metacognition = max(0.3, metacognition - 0.1)
        divergence = 0.3
        if noise.get("referential_noise", 0) > 0.5:
            divergence += 0.2
        if expectation.get("primary") == "COMPANION":
            divergence += 0.2
        if expectation.get("primary") == "TOOL":
            divergence = max(0.1, divergence - 0.1)
        stability = 0.7
        if noise.get("overall_noise", 0) > 0.6:
            stability -= 0.2
        return {
            "metacognition": round(min(1.0, max(0.0, metacognition)), 3),
            "divergence": round(min(1.0, max(0.0, divergence)), 3),
            "stability": round(min(1.0, max(0.0, stability)), 3),
        }


# ============================================================
# AlgorithmEngine 主类
# ============================================================

class AlgorithmEngine:
    """算法引擎 — 认知双工中的"快思考"侧。

    用法：
        engine = AlgorithmEngine()
        pcr_result = engine.analyze_pcr(user_input)
        intent_result = engine.parse_intent(user_input)
    """

    def __init__(
        self,
        noise_detector: Optional[NoiseDetector] = None,
        expectation_inferencer: Optional[ExpectationInferencer] = None,
        intent_parser: Optional[RuleBasedIntentParser] = None,
        snapshot_generator: Optional[CognitiveSnapshotGenerator] = None,
    ):
        self.noise_detector = noise_detector or NoiseDetector()
        self.expectation_inferencer = expectation_inferencer or ExpectationInferencer()
        self.intent_parser = intent_parser or RuleBasedIntentParser()
        self.snapshot_generator = snapshot_generator or CognitiveSnapshotGenerator()

    def analyze_pcr(self, user_input: str) -> Dict[str, Any]:
        """PCR 分析：噪声检测 + 期望推断 + 认知快照 + 综合置信度。"""
        noise = self.noise_detector.analyze(user_input)
        expectation = self.expectation_inferencer.infer(user_input, noise)
        snapshot = self.snapshot_generator.generate(user_input, noise, expectation)
        noise_factor = 1.0 - noise.get("overall_noise", 0.0)
        expectation_factor = expectation.get("confidence", 0.5)
        confidence = 0.4 * noise_factor + 0.4 * expectation_factor + 0.2 * snapshot.get("stability", 0.5)
        return {
            "noise_analysis": noise,
            "expectation_inference": expectation,
            "cognitive_snapshot": snapshot,
            "confidence": round(min(1.0, max(0.0, confidence)), 3),
        }

    def parse_intent(self, user_input: str) -> Dict[str, Any]:
        """意图解析：基于规则快速分类。"""
        return self.intent_parser.parse(user_input)

    def generate_plan(self, intent_category: str, user_input: str) -> Dict[str, Any]:
        """基于规则的快速规划生成，作为算法侧规划降级路径。"""
        simple_skills = {
            "SCAN_MEMORY": ["parse_address", "read_memory", "validate_result"],
            "READ_MEMORY": ["find_address", "read_value", "format_output"],
            "WRITE_MEMORY": ["verify_address", "prepare_value", "write_value", "confirm"],
            "HACK_VALUE": ["scan_target", "analyze_protection", "apply_patch", "verify"],
            "ASK_HELP": ["analyze_question", "search_knowledge", "compose_answer"],
            "ANALYZE": ["collect_data", "analyze_pattern", "generate_report"],
        }
        default_steps = ["understand_request", "execute", "report"]
        steps = simple_skills.get(intent_category, default_steps)
        return {
            "strategy": "Direct",
            "steps": [{"step_id": f"step_{i+1}", "action": s, "requires_tool": i > 0} for i, s in enumerate(steps)],
            "confidence": 0.6 if intent_category != "UNKNOWN" else 0.3,
            "fallback_strategy": "DivideConquer",
        }

    def get_cognitive_snapshot(self, user_input: str) -> Dict[str, float]:
        """仅获取认知快照（供外部单独调用）。"""
        noise = self.noise_detector.analyze(user_input)
        expectation = self.expectation_inferencer.infer(user_input, noise)
        return self.snapshot_generator.generate(user_input, noise, expectation)


__all__ = [
    "AlgorithmEngine",
    "AlgorithmResult",
    "NoiseDetector",
    "ExpectationInferencer",
    "RuleBasedIntentParser",
    "CognitiveSnapshotGenerator",
]
