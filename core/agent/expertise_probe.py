# -*- coding: utf-8 -*-
"""
core/agent/expertise_probe.py
────────────────────────────
Cold-start expertise probe (Architecture Gap #8).

Purpose:
  Quantify whether a fresh user input signals an *expert-level* intent that
  bypasses the normal clarification FSM. If the probe scores above a
  configurable threshold, the LLM is invoked to produce a one-shot cognitive
  profile; otherwise the standard rule-based cold-start path is used.

5-dimensional scoring:
  1. Terminology density    – ratio of domain-specific terms to total tokens.
  2. Parameter precision    – presence of exact addresses, types, or values.
  3. Query complexity       – syntactic depth, condition count, length.
  4. Language style       – imperative vs exploratory, mixed-language ratio.
  5. Historical behaviour  – consistency with previous turns in the session.

Valve mechanism:
  • Default : 3 clarification rounds trigger *degradation* (fallback to
    conservative rules-only mode).
  • User-adjustable via YAML (see config/expertise_lexicon.yaml).
  • LLM may override the threshold, but MUST describe the reason in the
    `meta.reason` field of the generated profile.

Hybrid tokenisation:
  • English technical terms are matched by a curated regex lexicon.
  • Chinese text is segmented by jieba (if installed) or by a 2-gram heuristic.

Integration:
  • Called by IntentParser._cold_start() when no prior cognitive profile exists.
  • Returns a tuple (CognitiveProfile, is_llm_generated, meta_dict).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

from core.agent.models import CognitiveProfile, IntentContext

logger = logging.getLogger("expertise_probe")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    ))
    logger.addHandler(_handler)

# ──────────────────────────────────────────────────────────────────────────────
# Optional jieba
# ──────────────────────────────────────────────────────────────────────────────
try:
    import jieba
    _JIEBA_AVAILABLE = True
except ImportError:
    jieba = None  # type: ignore
    _JIEBA_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────────────────
# Default YAML path
# ──────────────────────────────────────────────────────────────────────────────
_LEXICON_PATH = Path(__file__).parent.parent.parent / "config" / "expertise_lexicon.yaml"


# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class ExpertiseScore:
    """Score vector for the 5 dimensions."""
    terminology_density: float = 0.0     # 0–1
    parameter_precision: float = 0.0     # 0–1
    query_complexity: float = 0.0      # 0–1
    language_style: float = 0.0        # 0–1 (high = expert imperative)
    historical_behaviour: float = 0.0  # 0–1

    def weighted_total(self, weights: Dict[str, float]) -> float:
        w = weights
        total = (
            self.terminology_density * w.get("terminology_density", 0.25)
            + self.parameter_precision * w.get("parameter_precision", 0.25)
            + self.query_complexity * w.get("query_complexity", 0.15)
            + self.language_style * w.get("language_style", 0.20)
            + self.historical_behaviour * w.get("historical_behaviour", 0.15)
        )
        return min(1.0, max(0.0, total))

    def to_dict(self) -> Dict[str, float]:
        return {
            "terminology_density": self.terminology_density,
            "parameter_precision": self.parameter_precision,
            "query_complexity": self.query_complexity,
            "language_style": self.language_style,
            "historical_behaviour": self.historical_behaviour,
        }


@dataclass(frozen=False)
class ProbeResult:
    """Output of the expertise probe."""
    profile: CognitiveProfile
    is_llm_generated: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)
    score: ExpertiseScore = field(default_factory=ExpertiseScore)
    raw_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "is_llm_generated": self.is_llm_generated,
            "meta": self.meta,
            "score": self.score.to_dict(),
            "raw_score": self.raw_score,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Lexicon loader
# ═══════════════════════════════════════════════════════════════════════════════

class LexiconLoader:
    """Load and cache the expertise lexicon from YAML."""

    _instance: Optional["LexiconLoader"] = None
    _cache: Optional[Dict[str, Any]] = None
    _cache_mtime: float = 0.0

    def __new__(cls) -> "LexiconLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, path: Optional[Path] = None) -> Dict[str, Any]:
        p = path or _LEXICON_PATH
        if not p.exists():
            logger.warning("Lexicon not found at %s; using built-in defaults.", p)
            return self._builtin_lexicon()

        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML unavailable; using built-in lexicon.")
            return self._builtin_lexicon()

        mtime = p.stat().st_mtime
        if self._cache is not None and mtime == self._cache_mtime:
            return self._cache

        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self._cache = data
        self._cache_mtime = mtime
        return data

    def _builtin_lexicon(self) -> Dict[str, Any]:
        """Minimal built-in lexicon for environments without YAML."""
        return {
            "domains": {
                "memory_hacking": {
                    "english_terms": [
                        "scan", "pointer scan", "AOB", "byte array", "pointer map",
                        "address", "offset", "base address", "static address",
                        "memory region", "heap", "stack", "virtual address",
                        "read process memory", "write process memory",
                        "little-endian", "big-endian", "float", "double", "int64",
                        "instruction pointer", "RIP", "EIP", "ESP", "EBP",
                        "breakpoint", "hardware breakpoint", "software breakpoint",
                        "page guard", "VMT", "virtual method table", "vtable",
                    ],
                    "chinese_terms": [
                        "扫描", "指针扫描", "字节数组", "指针地图", "地址",
                        "偏移", "基址", "静态地址", "内存区域", "堆", "栈",
                        "读写内存", "小端", "大端", "浮点", "双精度", "整型",
                        "指令指针", "断点", "硬件断点", "软件断点", "页保护",
                        "虚表", "虚函数表",
                    ],
                },
                "reverse_engineering": {
                    "english_terms": [
                        "disassemble", "decompile", "IDA", "Ghidra", "x64dbg",
                        "OllyDbg", "Cheat Engine", "ReClass", "ReClass.NET",
                        "OEP", "original entry point", "IAT", "import table",
                        "export table", "PE header", "DOS header", "section header",
                        "TLS callback", "anti-debug", "anti-dump", "packer", "unpacker",
                        "VMProtect", "Themida", "Enigma", "Armadillo", " Themida",
                        "control flow flattening", "opaque predicate", "junk code",
                        "string encryption", "resource encryption", "API hooking",
                        "inline hook", "IAT hook", "detour", "trampoline",
                    ],
                    "chinese_terms": [
                        "反汇编", "反编译", "原始入口点", "导入表", "导出表",
                        "PE头", "DOS头", "节表", "TLS回调", "反调试", "反转储",
                        "加壳", "脱壳", "控制流平坦化", "不透明谓词", "花指令",
                        "字符串加密", "资源加密", "API钩子", "内联钩子", "跳转",
                    ],
                },
                "embedded_systems": {
                    "english_terms": [
                        "FPGA", "Verilog", "VHDL", "HDL", "synthesis",
                        "P&R", "place and route", "bitstream", "JTAG", "UART",
                        "SPI", "I2C", "CAN bus", "PWM", "ADC", "DAC",
                        "RTOS", "FreeRTOS", "Zephyr", "interrupt", "ISR",
                        "DMA", "memory-mapped I/O", "MMIO", "register map",
                        "clock domain crossing", "CDC", "metastability",
                        "FxLMS", "LMS filter", "adaptive filter", "DSP",
                    ],
                    "chinese_terms": [
                        "现场可编程门阵列", "综合", "布局布线", "比特流",
                        "中断", "中断服务程序", "直接内存访问", "寄存器映射",
                        "时钟域交叉", "亚稳态", "自适应滤波", "数字信号处理",
                    ],
                },
            },
            "weights": {
                "terminology_density": 0.25,
                "parameter_precision": 0.25,
                "query_complexity": 0.15,
                "language_style": 0.20,
                "historical_behaviour": 0.15,
            },
            "thresholds": {
                "llm_invocation": 0.72,
                "expert_bypass": 0.85,
                "clarification_degrade": 0.30,
            },
            "valves": {
                "max_clarification_rounds": 3,
                "degrade_to_conservative": True,
                "llm_override_requires_reason": True,
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# ExpertiseProbe
# ═══════════════════════════════════════════════════════════════════════════════

class ExpertiseProbe:
    """
    Cold-start expertise probe.

    Usage:
        probe = ExpertiseProbe()
        result = probe.probe(
            query="scan 0x00401000 for float 3.14159",
            history=[HistoryEntry(...)],
            llm_provider=my_llm,   # optional
        )
        if result.is_llm_generated:
            # LLM produced the profile; meta contains its reasoning
            pass
        else:
            # Rule-based fast path
            pass
    """

    def __init__(self, lexicon_path: Optional[Path] = None):
        self._lexicon = LexiconLoader().load(lexicon_path)
        self._weights: Dict[str, float] = self._lexicon.get("weights", {})
        self._thresholds: Dict[str, float] = self._lexicon.get("thresholds", {})
        self._valves: Dict[str, Any] = self._lexicon.get("valves", {})
        self._domains: Dict[str, Dict[str, List[str]]] = self._lexicon.get("domains", {})

        # Pre-compile English term regexes (case-insensitive, word boundary)
        self._en_patterns: Dict[str, List[re.Pattern]] = {}
        for domain, terms in self._domains.items():
            en_terms = terms.get("english_terms", [])
            self._en_patterns[domain] = [
                re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE)
                for t in en_terms
            ]

        # Chinese terms as a set for fast lookup (jieba or 2-gram fallback)
        self._cn_sets: Dict[str, Set[str]] = {}
        for domain, terms in self._domains.items():
            self._cn_sets[domain] = set(terms.get("chinese_terms", []))

        # Counters for clarification rounds (per-session, managed externally)
        self._clarification_counters: Dict[str, int] = {}

    # ── Public API ──────────────────────────────────────────────────────────

    def probe(
        self,
        query: str,
        history: List[Any],
        session_id: str = "",
        llm_provider: Optional[Any] = None,
    ) -> ProbeResult:
        """
        Main entry: evaluate a fresh query and decide whether to invoke LLM.

        Returns ProbeResult with CognitiveProfile + metadata.
        """
        # Step 1: compute 5-dimensional score
        score = self._score(query, history, session_id)
        raw_score = score.weighted_total(self._weights)

        # Step 2: valve check — too many clarifications?
        degrade = self._check_valve(session_id, history)
        if degrade:
            logger.info("Valve triggered for session %s: degradation mode.", session_id)
            return ProbeResult(
                profile=self._degraded_profile(),
                is_llm_generated=False,
                meta={
                    "reason": "valve_degradation",
                    "clarification_rounds": self._clarification_count(session_id),
                    "score": score.to_dict(),
                    "raw_score": raw_score,
                },
                score=score,
                raw_score=raw_score,
            )

        # Step 3: threshold routing
        llm_threshold = self._thresholds.get("llm_invocation", 0.72)
        expert_bypass = self._thresholds.get("expert_bypass", 0.85)

        if raw_score >= expert_bypass:
            # Expert bypass: skip LLM, use deterministic profile
            profile = self._expert_profile(score)
            return ProbeResult(
                profile=profile,
                is_llm_generated=False,
                meta={
                    "reason": "expert_bypass",
                    "score": score.to_dict(),
                    "raw_score": raw_score,
                },
                score=score,
                raw_score=raw_score,
            )

        if raw_score >= llm_threshold and llm_provider is not None:
            # LLM invocation
            profile, meta = self._llm_profile(query, history, score, llm_provider)
            return ProbeResult(
                profile=profile,
                is_llm_generated=True,
                meta=meta,
                score=score,
                raw_score=raw_score,
            )

        # Standard rule-based cold-start
        profile = self._rule_based_profile(score)
        return ProbeResult(
            profile=profile,
            is_llm_generated=False,
            meta={
                "reason": "rule_based_cold_start",
                "score": score.to_dict(),
                "raw_score": raw_score,
            },
            score=score,
            raw_score=raw_score,
        )

    # ── 5-dimensional scoring ─────────────────────────────────────────────────

    def _score(self, query: str, history: List[Any], session_id: str) -> ExpertiseScore:
        return ExpertiseScore(
            terminology_density=self._score_terminology(query),
            parameter_precision=self._score_parameters(query),
            query_complexity=self._score_complexity(query),
            language_style=self._score_style(query),
            historical_behaviour=self._score_history(history),
        )

    def _score_terminology(self, query: str) -> float:
        """Ratio of domain-specific terms to total tokens."""
        if not query.strip():
            return 0.0

        # Tokenise
        en_tokens = self._tokenise_english(query)
        cn_tokens = self._tokenise_chinese(query)
        total_tokens = max(1, len(en_tokens) + len(cn_tokens))

        # Match English terms
        en_matches = 0
        for patterns in self._en_patterns.values():
            for pat in patterns:
                en_matches += len(pat.findall(query))

        # Match Chinese terms
        cn_matches = 0
        for token in cn_tokens:
            for s in self._cn_sets.values():
                if token in s:
                    cn_matches += 1
                    break

        # Density with diminishing returns (log scaling)
        raw = (en_matches + cn_matches) / total_tokens
        return min(1.0, math.log1p(raw * 5) / math.log1p(5))

    def _score_parameters(self, query: str) -> float:
        """Precision: exact hex addresses, numeric values, byte patterns, types."""
        scores = []
        # Hex addresses
        hex_addrs = re.findall(r"\b0x[0-9A-Fa-f]{4,}\b", query)
        scores.append(min(1.0, len(hex_addrs) * 0.30))
        # Numeric values (decimal / float, not just single digits)
        nums = re.findall(r"\b\d{2,}(?:\.\d+)?\b", query)
        scores.append(min(1.0, len(nums) * 0.15))
        # Byte patterns (AOB)
        aobs = re.findall(r"(?:[0-9A-Fa-f]{2}\s+){2,}[0-9A-Fa-f]{2}(?:\s+\?\?)*", query)
        scores.append(0.6 if aobs else 0.0)
        # Type annotations
        types = re.findall(r"\b(?:float|double|int|int64|byte|word|dword|qword|string|unicode)\b", query, re.IGNORECASE)
        scores.append(min(1.0, len(types) * 0.20))
        # Range / condition
        conds = re.findall(r"\b(?:between|from|to|>|>=|<|<=|==|!=|±|~|approximately)\b", query, re.IGNORECASE)
        scores.append(min(1.0, len(conds) * 0.15))

        return sum(scores) / len(scores) if scores else 0.0

    def _score_complexity(self, query: str) -> float:
        """Syntactic complexity: length, condition count, nesting depth."""
        length_score = min(1.0, len(query) / 200.0)
        # Condition words (if, when, unless, 如果, 当, 除非)
        conds = re.findall(r"\b(?:if|when|unless|while|after|before|and|or)\b", query, re.IGNORECASE)
        cn_conds = re.findall(r"(?:如果|当|除非|并且|或者|同时|然后|接着|之后|之前)", query)
        cond_score = min(1.0, (len(conds) + len(cn_conds)) * 0.15)
        # Punctuation depth (parentheses, brackets)
        nesting = max(query.count("("), query.count("["), query.count("{"))
        nest_score = min(1.0, nesting * 0.20)
        # Sentence count (rough)
        sentences = re.split(r"[。\.\?\!？！；;]", query)
        sent_score = min(1.0, len([s for s in sentences if s.strip()]) / 5.0)
        return (length_score * 0.30 + cond_score * 0.30 + nest_score * 0.20 + sent_score * 0.20)

    def _score_style(self, query: str) -> float:
        """
        High score = expert imperative style (low divergence, low metacognition).
        Low score = exploratory / companion style.
        """
        text_lower = query.lower()
        # Imperative markers (command-like)
        imperative = [
            "scan", "read", "write", "patch", "hook", "break", "dump",
            "set", "change", "find", "search", "attach", "detach", "trace",
            "扫描", "读取", "写入", "修改", "设置", "查找", "搜索", "附加", "分离", "追踪",
        ]
        imp_count = sum(1 for w in imperative if w in text_lower)
        imp_score = min(1.0, imp_count * 0.25)

        # Mixed language ratio (technical English + Chinese)
        en_chars = len(re.findall(r"[a-zA-Z]", query))
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", query))
        total_chars = max(1, len(query))
        mixed_ratio = (en_chars + cn_chars) / total_chars
        mixed_score = min(1.0, mixed_ratio)

        # Question markers (reduces expert score)
        q_marks = query.count("?") + query.count("？")
        q_score = max(0.0, 1.0 - q_marks * 0.20)

        # Hedging / exploratory words
        hedge = ["maybe", "perhaps", "大概", "可能", "试试", "看看", "摸索", "不确定"]
        hedge_count = sum(1 for w in hedge if w in text_lower)
        hedge_score = max(0.0, 1.0 - hedge_count * 0.15)

        return (imp_score * 0.35 + mixed_score * 0.25 + q_score * 0.20 + hedge_score * 0.20)

    def _score_history(self, history: List[Any]) -> float:
        """Consistency with previous turns."""
        if not history or len(history) < 2:
            return 0.0

        # Look at last 3 user turns
        user_turns = [h for h in history if getattr(h, "role", "") == "user"][-3:]
        if not user_turns:
            return 0.0

        # If previous turns were all TOOL-like, increase score
        exp_map = {
            "TOOL": 1.0,
            "ADVISOR": 0.6,
            "COMPANION": 0.2,
            "UNKNOWN": 0.0,
        }
        scores = []
        for turn in user_turns:
            exp = getattr(turn, "expectation", "UNKNOWN")
            scores.append(exp_map.get(exp, 0.0))

        # EMA decay
        ema = 0.0
        for i, s in enumerate(scores):
            ema = ema * 0.5 + s * 0.5
        return ema

    # ── Tokenisation helpers ────────────────────────────────────────────────

    def _tokenise_english(self, text: str) -> List[str]:
        return re.findall(r"[a-zA-Z]+", text)

    def _tokenise_chinese(self, text: str) -> List[str]:
        if _JIEBA_AVAILABLE and jieba is not None:
            return list(jieba.cut(text.strip()))
        # Fallback: 2-gram sliding window + single characters
        chars = re.findall(r"[\u4e00-\u9fff]", text)
        tokens = chars[:]
        for i in range(len(chars) - 1):
            tokens.append(chars[i] + chars[i + 1])
        return tokens

    # ── Valve logic ─────────────────────────────────────────────────────────

    def _check_valve(self, session_id: str, history: List[Any]) -> bool:
        """Return True if clarification rounds exceed the valve limit."""
        max_rounds = self._valves.get("max_clarification_rounds", 3)
        count = self._clarification_count(session_id, history)
        return count >= max_rounds

    def _clarification_count(self, session_id: str, history: List[Any] = None) -> int:
        """Count how many clarification rounds occurred in this session."""
        if session_id and session_id in self._clarification_counters:
            return self._clarification_counters[session_id]
        if history is None:
            return 0
        # Infer from history: count assistant turns asking for clarification
        count = 0
        for entry in history:
            if getattr(entry, "role", "") == "assistant":
                content = getattr(entry, "content", "")
                if any(kw in content.lower() for kw in (
                    " clarification ", " clarify ", " ambiguous ", " unclear ",
                    " 澄清 ", " 不明确 ", " 请提供 ", " 请说明 ", " 请补充 ",
                    " more info", " more detail", " specify", "请指定",
                )):
                    count += 1
        return count

    def record_clarification(self, session_id: str) -> None:
        """External API: increment the clarification counter for a session."""
        if session_id:
            self._clarification_counters[session_id] = self._clarification_counters.get(session_id, 0) + 1

    def reset_valve(self, session_id: str) -> None:
        """Reset the valve counter (e.g. after a successful resolution)."""
        self._clarification_counters.pop(session_id, None)

    # ── Profile generators ──────────────────────────────────────────────────

    def _expert_profile(self, score: ExpertiseScore) -> CognitiveProfile:
        """High-score deterministic profile (expert bypass)."""
        return CognitiveProfile(
            metacognition=0.3,      # low: expert knows what they want
            divergence=0.2,           # low: convergent, imperative
            tracking_depth=0.8,     # high: sustained technical focus
            stability=0.9,          # high: consistent style
            confidence=0.95,        # high: strong signal
        )

    def _rule_based_profile(self, score: ExpertiseScore) -> CognitiveProfile:
        """Standard rule-based cold-start profile."""
        return CognitiveProfile(
            metacognition=0.5,
            divergence=0.5,
            tracking_depth=0.5,
            stability=0.5,
            confidence=0.4,
        )

    def _degraded_profile(self) -> CognitiveProfile:
        """Valve-triggered degradation: conservative, minimal assumptions."""
        return CognitiveProfile(
            metacognition=0.8,      # high: acknowledge uncertainty
            divergence=0.7,         # high: exploratory mode
            tracking_depth=0.3,
            stability=0.3,
            confidence=0.2,
        )

    def _llm_profile(
        self,
        query: str,
        history: List[Any],
        score: ExpertiseScore,
        llm_provider: Any,
    ) -> Tuple[CognitiveProfile, Dict[str, Any]]:
        """
        Invoke LLM to generate a cognitive profile.

        The LLM MUST describe any threshold override in meta['reason'].
        """
        prompt = self._build_llm_prompt(query, history, score)
        try:
            response = llm_provider.generate(prompt)
            content = response.text if hasattr(response, "text") else str(response)
            parsed = self._parse_llm_response(content)

            profile = CognitiveProfile(
                metacognition=parsed.get("metacognition", 0.5),
                divergence=parsed.get("divergence", 0.5),
                tracking_depth=parsed.get("tracking_depth", 0.5),
                stability=parsed.get("stability", 0.5),
                confidence=parsed.get("confidence", 0.6),
            )

            meta = {
                "reason": parsed.get("reason", "llm_default"),
                "raw_response": content[:500],
                "score": score.to_dict(),
            }
            return profile, meta
        except Exception as e:
            logger.error("LLM profile generation failed: %s", e)
            # Fallback to rule-based
            return self._rule_based_profile(score), {
                "reason": "llm_error_fallback",
                "error": str(e),
            }

    def _build_llm_prompt(self, query: str, history: List[Any], score: ExpertiseScore) -> str:
        hist_summary = ""
        if history:
            recent = history[-3:]
            hist_summary = "\n".join(
                f"- {getattr(h, 'role', '?')}: {getattr(h, 'content', '')[:80]}"
                for h in recent
            )

        return (
            "You are a cognitive profiler for a reverse-engineering assistant.\n"
            "Given a user query and its expertise scores, produce a JSON object\n"
            "with exactly these keys: metacognition, divergence, tracking_depth,\n"
            "stability, confidence, reason.\n\n"
            "Rules:\n"
            "1. All values are floats in [0.0, 1.0].\n"
            "2. 'reason' must explain WHY you chose these values.\n"
            "3. If the user is clearly an expert (high precision, imperative style),\n"
            "   set low metacognition, low divergence, high confidence.\n"
            "4. If the user is exploratory or vague, set high metacognition,\n"
            "   high divergence, low confidence.\n"
            "5. Output ONLY the JSON object, no markdown fences.\n\n"
            f"Query: {query}\n\n"
            f"Expertise scores:\n{json.dumps(score.to_dict(), indent=2, ensure_ascii=False)}\n\n"
            f"Recent history:\n{hist_summary}\n\n"
            "JSON:"
        )

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """Extract JSON from LLM response, robust to markdown fences."""
        content = content.strip()
        # Strip markdown fences
        if content.startswith("```"):
            content = content.strip("`\n")
            if content.startswith("json"):
                content = content[4:].strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to find the first {...} block
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
            logger.warning("Failed to parse LLM response as JSON: %s", content[:200])
            return {}

    # ── Utility ─────────────────────────────────────────────────────────────

    def get_thresholds(self) -> Dict[str, float]:
        return dict(self._thresholds)

    def set_threshold(self, key: str, value: float, reason: str = "") -> None:
        """
        Adjust a threshold. If changed by LLM, reason MUST be non-empty.
        """
        if key not in self._thresholds:
            raise KeyError(f"Unknown threshold: {key}. Valid: {list(self._thresholds)}")
        old = self._thresholds[key]
        self._thresholds[key] = value
        logger.info(
            "Threshold '%s' changed: %.3f -> %.3f (reason: %s)",
            key, old, value, reason or "manual",
        )

    def reload_lexicon(self, path: Optional[Path] = None) -> None:
        """Hot-reload the lexicon from disk."""
        self._lexicon = LexiconLoader().load(path)
        self._weights = self._lexicon.get("weights", {})
        self._thresholds = self._lexicon.get("thresholds", {})
        self._valves = self._lexicon.get("valves", {})
        self._domains = self._lexicon.get("domains", {})
