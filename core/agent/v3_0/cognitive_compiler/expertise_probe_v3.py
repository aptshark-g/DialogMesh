# -*- coding: utf-8 -*-

import logging, math, re
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ColdStartProbe:
    """
    ColdStartProbe v3.0 -- 通用冷启动专业度探测。

    不依赖任何领域词表，通过通用语言特征推断用户专业度。
    核心假设：专业用户的查询具备更高的信息密度、
    更精确的引用和更结构化的语法。

    评分策略：每个维度取其最强的单一信号（max-based），
    而非对所有子信号做平均。这确保一个突出的专业特征
    （如精确的十六进制地址）不会被多个空信号稀释。
    """

    _WEIGHTS = {"vocab": 0.25, "precision": 0.30, "complexity": 0.25, "style": 0.20}

    # 通用语言模式
    _LONG_WORD = re.compile(r"\b[a-zA-Z]{8,}\b")
    _CAMEL_CASE = re.compile(r"[a-z]+[A-Z][a-z]+")
    _SNAKE_CASE = re.compile(r"[a-z]+_[a-z]+")
    _KEBAB_CASE = re.compile(r"[a-z]+-[a-z]+")
    _ACRONYM = re.compile(r"\b[A-Z]{2,5}\b")
    _ALPHANUM = re.compile(r"\b[a-zA-Z]+\d+[a-zA-Z0-9]*\b|\b\d+[a-zA-Z]+[a-zA-Z0-9]*\b")
    _FILE_PATH = re.compile(r"[\\/][a-zA-Z0-9_.-]+[\\/][a-zA-Z0-9_.-]+")
    _HEX_ADDR = re.compile(r"\b0x[0-9a-fA-F]+\b")
    _VERSION = re.compile(r"\b(?:v|ver\.?)?\d+\.\d+(?:\.\d+)*\b", re.IGNORECASE)
    _UNIT_VAL = re.compile(r"\b\d+(?:\.\d+)?\s*(?:px|ms|KB|MB|GB|TB|MHz|GHz|bps)\b", re.IGNORECASE)
    _RANGE = re.compile(r"\b\d+\s*(?:-|~|to)\s*\d+\b", re.IGNORECASE)
    _CONDITIONAL = re.compile(r"\b(?:if|unless|provided|given|assuming|whenever)\b", re.IGNORECASE)
    _PROCEDURAL = re.compile(r"\b(?:first|then|next|finally|step\s+\d+)\b", re.IGNORECASE)
    _IMPERATIVE = re.compile(r"\b(?:read|write|scan|find|list|show|get|set|create|delete|update|run|execute|compute|calculate|compile|build|deploy|install|configure|start|stop|restart)\b", re.IGNORECASE)
    _EXPLORATORY = re.compile(r"\b(?:what|why|how|can you|could you|maybe|perhaps|wonder|what if)\b", re.IGNORECASE)
    _HEDGING = re.compile(r"\b(?:maybe|perhaps|probably|possibly|i think|i guess|kind of|not sure|might be|could be)\b", re.IGNORECASE)

    def probe(self, query: str) -> Dict[str, Any]:
        """主入口：评估查询专业度，产生认知快照。"""
        vocab = self._score_technical_vocabulary(query)
        prec = self._score_parameter_precision(query)
        comp = self._score_complexity(query)
        style = self._score_language_style(query)

        overall = (
            vocab * self._WEIGHTS["vocab"]
            + prec * self._WEIGHTS["precision"]
            + comp * self._WEIGHTS["complexity"]
            + style * self._WEIGHTS["style"]
        )

        words = query.split() if query.strip() else []
        level = "high" if overall > 0.5 else ("medium" if overall > 0.25 else "low")

        return {
            "overall_expertise": round(overall, 3),
            "dimensions": {
                "technical_vocabulary": round(vocab, 3),
                "parameter_precision": round(prec, 3),
                "query_complexity": round(comp, 3),
                "language_style": round(style, 3),
                "historical_behaviour": 0.5,
            },
            "technical_level": level,
            "cognitive_snapshot": {
                "metacognition": round(0.3 + overall * 0.5, 3),
                "divergence": round(0.6 - overall * 0.4, 3),
                "stability": round(0.4 + overall * 0.5, 3),
            },
        }

    def _score_technical_vocabulary(self, query: str) -> float:
        """
        通用技术词汇密度评分（max-based）。
        检测长词、代码风格记号、缩写、字母数字混合、文件路径。
        返回各子信号中最大的加权值。
        """
        if not query.strip(): return 0.0
        words = query.split()
        total = max(1, len(words))

        # 长词密度
        long_w = len(self._LONG_WORD.findall(query))
        s1 = min(1.0, long_w / total * 4)
        # 代码风格记号
        code = len(self._CAMEL_CASE.findall(query)) + len(self._SNAKE_CASE.findall(query)) + len(self._KEBAB_CASE.findall(query))
        s2 = min(1.0, code * 0.20)
        # 缩写
        acro = len(self._ACRONYM.findall(query))
        s3 = min(1.0, acro * 0.15)
        # 字母数字混合
        an = len(self._ALPHANUM.findall(query))
        s4 = min(1.0, an * 0.15)
        # 文件路径
        path = len(self._FILE_PATH.findall(query))
        s5 = min(1.0, path * 0.20)

        signals = [s1, s2, s3, s4, s5]
        weights = [0.30, 0.25, 0.15, 0.15, 0.15]
        # max-based: 取最强信号
        max_signal = max(s * w for s, w in zip(signals, weights))
        return round(min(1.0, max_signal * 1.5), 3)  # 1.5x boost for single strong signal

    def _score_parameter_precision(self, query: str) -> float:
        """
        通用参数精确度评分（max-based）。
        每一类精确引用独立计分，取最强信号。
        确保一个突出的精确值不会被空类别稀释。
        """
        if not query.strip(): return 0.0

        signals = []
        signals.append(min(1.0, len(self._HEX_ADDR.findall(query)) * 0.35))
        signals.append(min(1.0, len(self._VERSION.findall(query)) * 0.30))
        signals.append(min(1.0, len(self._FILE_PATH.findall(query)) * 0.25))
        signals.append(min(1.0, len(self._UNIT_VAL.findall(query)) * 0.30))
        signals.append(min(1.0, len(self._RANGE.findall(query)) * 0.25))
        signals.append(min(1.0, len(re.findall(r"\b\d{4,}(?:\.\d+)?\b", query)) * 0.10))

        return round(max(signals), 3) if signals else 0.0

    def _score_complexity(self, query: str) -> float:
        """通用语法复杂度评分。"""
        if not query.strip(): return 0.0
        length = min(1.0, len(query) / 150.0)
        cond = min(1.0, len(self._CONDITIONAL.findall(query)) * 0.25)
        proc = min(1.0, len(self._PROCEDURAL.findall(query)) * 0.20)
        nests = max(query.count(chr(40)), query.count(chr(91)), query.count(chr(123)))
        nest = min(1.0, nests * 0.15)
        sents = len([s for s in re.split(r"[.!?;]", query) if s.strip()])
        sent = min(1.0, sents / 4.0)
        signals = [length, cond, proc, nest, sent]
        weights = [0.25, 0.30, 0.20, 0.10, 0.15]
        return round(min(1.0, max(s * w for s, w in zip(signals, weights)) * 2.0), 3)

    def _score_language_style(self, query: str) -> float:
        """语言风格评分。高值=命令式（专家），低值=探索式（新手）。"""
        if not query.strip(): return 0.5
        imp = len(self._IMPERATIVE.findall(query))
        exp = len(self._EXPLORATORY.findall(query))
        hedge = len(self._HEDGING.findall(query))
        questions = query.count(chr(63))
        raw = 0.5 + min(1.0, imp * 0.12) - min(1.0, (exp + questions + hedge * 2) * 0.08)
        return round(max(0.0, min(1.0, raw)), 3)


__all__ = ["ColdStartProbe"]
