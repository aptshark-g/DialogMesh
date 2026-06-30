# -*- coding: utf-8 -*-
"""
core/agent/pcr/rule_based.py
─────────────────────────
RuleBasedPCR implementation.

A zero-dependency (beyond stdlib + PyYAML) PCR implementation that uses
regex rules, statistical heuristics, and sliding-window EMA for cognitive
profiling. LLM fallback is optional and only triggered for <10% of inputs.

Components:
  1. ExpectationIdentifier: 3-tier cascade (rules → history → LLM fallback)
  2. NoiseEstimator: 4-dimensional rule-based noise scoring
  3. ComplexityEstimator: YAML-configured complexity map + heuristic rules
  4. CognitiveProfiler: EMA-based 4-dimension profile with Jaccard similarity
  5. RuleBasedPCR: assembles above into IPCRRouter interface
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field

from core.agent.pcr.datacontract import (
    PCRInput_v1,
    PCROutput_v1,
    CognitiveProfile_v1,
    HistoryEntry,
)
from core.agent.pcr.interface import IPCRRouter, PCRHealthStatus
from core.agent.pcr.telemetry import TelemetryCollector

logger = logging.getLogger("pcr.rule_based")

# Try to import optional YAML
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
# Expectation Identifier
# ═══════════════════════════════════════════════════════════════════════════════

class ExpectationIdentifier:
    """3-tier expectation identification: rules → history → LLM fallback."""

    # Learning / tutorial keywords (high priority for COMPANION)
    _LEARNING_KEYWORDS: Set[str] = {
        "学习", "教程", "怎么", "如何", "教教我", "新手", "入门", "指导",
        "教一下", "怎么学", "怎么操作", "怎么使用", "怎么弄", "怎么做",
        "learn", "tutorial", "how to", "beginner", "guide me", "teach me",
        "step by step", "walk me through", "i want to learn", "show me how",
    }

    # Tool keywords (English + Chinese)
    _TOOL_KEYWORDS: Set[str] = {
        "scan", "disassemble", "disasm", "read", "write", "patch",
        "break", "bp", "dump", "hook", "trace", "attach", "detach",
        "扫描", "反汇编", "读取", "写入", "修改", "打断点", "下断点",
        "脱壳", "hook", "追踪", "附加", "分离", "patch", "patch", "nop",
        "find", "search", "locate", "查找", "搜索", "定位", "找到",
        "change", "set", "lock", "freeze", "改", "设置", "锁定", "冻结",
    }

    # Advisor keywords (analytical, judgmental)
    _ADVISOR_KEYWORDS: Set[str] = {
        "怎么", "为什么", "怎么看", "是不是", "对吗", "确认",
        "分析", "判断", "识别", "可疑", "加密", "混淆", "保护",
        "how", "why", "what about", "is this", "does this look",
        "analyze", "assess", "judge", "identify", "suspicious",
        "evaluate", "determine", "explain why", "what do you think",
    }

    # Companion keywords (exploratory, narrative, self-referential, conversational)
    _COMPANION_KEYWORDS: Set[str] = {
        "我在", "我想", "帮我", "告诉我", "解释", "详细",
        "慢慢", "一步一步", "新手", "刚开始", "不太懂",
        "i'm trying", "i want", "help me", "explain", "step by step",
        "beginner", "new to", "guide me", "walk me through",
        # 对话/问候/身份询问 (新增)
        "你好", "您好", "嗨", "hello", "hi", "hey",
        "你是什么", "你是谁", "你叫", "介绍一下", "能做什么",
        "你是干什么的", "你干啥的", "你的功能", "你的作用",
        "what are you", "who are you", "what can you do",
        "your name", "introduce yourself", "what do you do",
        # 元对话/状态询问 (新增)
        "怎么回事", "什么情况", "为什么没", "怎么没",
        "没反应", "没回复", "没输出", "没结果",
        "what happened", "why no", "no response", "no output",
        "怎么了", "发生什么", "出什么问题",
    }

    # Vague / ambiguous words (noise indicators)
    _VAGUE_WORDS: Set[str] = {
        "那个", "这个", "东西", "搞", "弄", "整", "一下",
        "something", "thing", "stuff", "whatever", "somehow",
        "随便", "看看", "搞一下", "弄一下", "整一下",
    }

    # Metacognitive markers (high metacognition)
    _META_MARKERS: Set[str] = {
        "我理解对吗", "是不是这样", "对吗", "确认一下", "我的理解",
        "我这样想对吗", "对不对", "这样对吗", "理解正确吗",
        "am i right", "do i understand", "is my understanding",
        "correct me if", "confirm", "verify my",
    }

    # Follow-up markers (indicates continuation of previous mode)
    _FOLLOW_MARKERS: Set[str] = {
        "继续", "下一步", "再", "然后", "接着", "接下来",
        "continue", "next", "then", "go on", "proceed", "after that",
    }

    # Open-ended question markers (high divergence)
    _OPEN_MARKERS: Set[str] = {
        "为什么", "怎么", "什么", "哪里", "如何", "如果", "假如", "会怎样",
        "why", "how", "what", "where", "if", "would", "could", "might",
        "explain", "tell me about", "what do you think", "how about",
    }

    def __init__(self, llm_provider=None):
        self._llm_provider = llm_provider
        self._cache: Dict[str, Tuple[str, float]] = {}
        self._cache_ttl_sec = 300

    def identify(self, query: str, history: List[HistoryEntry]) -> Tuple[str, float]:
        """
        3-tier cascade identification.
        Returns (expectation, confidence).
        """
        # Tier 1: Rule-based fast path (0-2ms)
        result = self._rule_based(query)
        if result[1] >= 0.85:
            return result

        # Tier 2: History inference (0-1ms)
        if len(history) >= 2:
            result = self._history_inference(query, history, result)
            if result[1] >= 0.75:
                return result

        # Tier 3: LLM few-shot fallback (100-200ms, only if provider available)
        if self._llm_provider and result[1] < 0.5:
            return self._llm_fallback(query)

        return result

    def _rule_based(self, query: str) -> Tuple[str, float]:
        """Fast path: keyword and pattern matching."""
        text_lower = query.lower().strip()
        if not text_lower:
            return ("UNKNOWN", 1.0)

        # Check custom rules first (highest priority)
        if hasattr(self, '_custom_rules') and self._custom_rules:
            for exp, rule in sorted(self._custom_rules.items(), key=lambda x: -len(x[1].get('phrases', []))):
                for phrase in rule.get('phrases', []):
                    if phrase in text_lower:
                        return (exp, 0.95)
                for kw in rule.get('keywords', []):
                    if kw in text_lower:
                        return (exp, 0.85)

        # Check for LEARNING indicators (high priority, override TOOL if no explicit operand)
        has_learning_kw = any(kw in text_lower for kw in self._LEARNING_KEYWORDS)
        has_operand = bool(re.search(r'0x[0-9a-f]+|\d+|\bpatch\b|\bscan\b', text_lower))
        if has_learning_kw and not has_operand:
            return ("COMPANION", 0.90)

        # Check for TOOL indicators
        has_tool_kw = any(kw in text_lower for kw in self._TOOL_KEYWORDS)
        if has_tool_kw and has_operand:
            return ("TOOL", 0.95)
        if has_tool_kw and len(query) < 40 and not has_learning_kw:
            return ("TOOL", 0.85)

        # Check for ADVISOR indicators
        has_advisor_kw = any(kw in text_lower for kw in self._ADVISOR_KEYWORDS)
        has_question = '?' in query or '？' in query or any(q in text_lower for q in ['怎么', '为什么', '怎么看'])
        if has_advisor_kw and has_question and not has_tool_kw:
            return ("ADVISOR", 0.90)
        if has_advisor_kw and not has_tool_kw:
            return ("ADVISOR", 0.75)

        # Check for COMPANION indicators (expanded with conversational fallbacks)
        has_companion_kw = any(kw in text_lower for kw in self._COMPANION_KEYWORDS)
        if has_companion_kw and not has_tool_kw:
            return ("COMPANION", 0.90)
        # Check for UNKNOWN (extremely vague)
        vague_count = sum(1 for w in self._VAGUE_WORDS if w in text_lower)
        if vague_count >= 2 or len(query) < 5:
            return ("UNKNOWN", 0.80)
        if vague_count >= 1 and not any(kw in text_lower for kw in self._TOOL_KEYWORDS | self._ADVISOR_KEYWORDS | self._COMPANION_KEYWORDS):
            return ("UNKNOWN", 0.65)
        # Fallback: short natural-language questions without tool keywords → COMPANION (conversational)
        if ("?" in query or "？" in query) and not has_tool_kw and not has_advisor_kw and len(query) < 60:
            return ("COMPANION", 0.60)
        return ("UNKNOWN", 0.30)

    def _history_inference(self, query: str, history: List[HistoryEntry],
                         current: Tuple[str, float]) -> Tuple[str, float]:
        """Infer from conversation history."""
        text_lower = query.lower()
        last_exp = history[-2].expectation or "UNKNOWN"

        # Follow-up markers → continue previous mode
        if any(m in text_lower for m in self._FOLLOW_MARKERS):
            return (last_exp, 0.90)

        # Short operand-only input after TOOL → continue TOOL
        if last_exp == "TOOL" and len(query) < 20 and bool(re.search(r'0x[0-9a-f]+|\d+', query)):
            return ("TOOL", 0.85)

        # Question after COMPANION → continue COMPANION
        if last_exp == "COMPANION" and ('?' in query or '？' in query):
            return ("COMPANION", 0.80)

        return current

    def _llm_fallback(self, query: str) -> Tuple[str, float]:
        """LLM few-shot fallback for ambiguous inputs."""
        # Simple cache
        cache_key = query[:100]
        if cache_key in self._cache:
            cached_result, cached_time = self._cache[cache_key]
            if time.time() - cached_time < self._cache_ttl_sec:
                return (cached_result, 0.70)  # Lower confidence for cached LLM results

        if not self._llm_provider:
            return ("UNKNOWN", 0.30)

        prompt = self._build_llm_prompt(query)
        try:
            raw_response = self._llm_provider.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            expectation = self._parse_llm_response(raw_response)
            self._cache[cache_key] = (expectation, time.time())
            return (expectation, 0.65)
        except Exception as e:
            logger.warning(f"LLM fallback failed: {e}")
            return ("UNKNOWN", 0.25)

    def add_rule(self, expectation: str, keywords: List[str], phrases: Optional[List[str]] = None):
        """Add a custom rule for expectation identification."""
        if not hasattr(self, '_custom_rules'):
            self._custom_rules = {}
        self._custom_rules[expectation.upper()] = {
            "keywords": set(k.lower() for k in keywords),
            "phrases": set(p.lower() for p in (phrases or [])),
        }

    def remove_rule(self, expectation: str) -> None:
        """Remove a custom rule."""
        if hasattr(self, '_custom_rules'):
            self._custom_rules.pop(expectation.upper(), None)

    def _build_llm_prompt(self, query: str) -> str:
        """Build few-shot prompt for expectation classification."""
        return (
            "Classify user expectation into one of: TOOL, ADVISOR, COMPANION, UNKNOWN.\n\n"
            "Definitions:\n"
            "- TOOL: User wants direct execution (scan, disassemble, read, write, patch).\n"
            "- ADVISOR: User wants analysis or judgment (how, why, is this suspicious).\n"
            "- COMPANION: User wants exploratory dialogue or explanation.\n"
            "- UNKNOWN: Cannot determine from input alone.\n\n"
            "Examples:\n"
            '1. "scan 4 bytes for 100" -> TOOL\n'
            '2. "does this function look encrypted?" -> ADVISOR\n'
            '3. "I\'m reversing a game, where should I start?" -> COMPANION\n'
            '4. "patch 0x401000 to NOP" -> TOOL\n'
            '5. "what do you think about this packer?" -> ADVISOR\n'
            '6. "that thing, fix it" -> UNKNOWN\n\n'
            f'Input: "{query[:200]}"\n'
            "Output only the label (TOOL/ADVISOR/COMPANION/UNKNOWN):"
        )

    def _parse_llm_response(self, raw: str) -> str:
        """Extract label from LLM response."""
        raw_upper = raw.strip().upper()
        for label in ("TOOL", "ADVISOR", "COMPANION", "UNKNOWN"):
            if label in raw_upper:
                return label
        return "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════════════
# Noise Estimator
# ═══════════════════════════════════════════════════════════════════════════════

class NoiseEstimator:
    """Rule-based noise level estimation (0-1)."""

    _VAGUE_WORDS = {
        "那个", "这个", "东西", "搞", "弄", "整", "一下",
        "something", "thing", "stuff", "whatever", "somehow",
        "随便", "看看", "搞一下", "弄一下", "整一下",
    }

    def estimate(self, query: str, history: List[HistoryEntry], current_time: Optional[float] = None) -> float:
        """Estimate noise level with 3D cognitive refresh awareness."""
        if not query or not query.strip():
            return 0.0

        noise = 0.0
        text_lower = query.lower().strip()

        # 1. Structural noise (0-0.25): no verb or garbled
        if len(text_lower) < 3:
            noise += 0.25
        elif not self._has_verb(text_lower):
            noise += 0.20
        if self._has_garbled(text_lower):
            noise += 0.15

        # 2. Lexical noise (0-0.30): vague word density
        vague_count = sum(1 for w in self._VAGUE_WORDS if w in text_lower)
        noise += min(0.30, vague_count * 0.08)

        # 3. Gibberish words (random-looking strings)
        gibberish_count = self._count_gibberish_words(text_lower)
        noise += min(0.25, gibberish_count * 0.10)

        # 4. Context break (0.0–0.20): 3D joint evaluation (temporal / referential / discursive)
        #    Old design: simple entity overlap → misjudged topic shifts as noise
        #    New design: cognitive refresh awareness via 3D model
        if history and len(history) >= 1:
            last_entry = history[-1]

            # Dimension 1: Temporal gap factor (τ)
            temporal_factor = self._temporal_gap_factor(
                current_time if current_time is not None else 0.0,
                getattr(last_entry, 'timestamp', None)
            )
            # Time gap weights:
            #   <30s     → 1.0 (working memory active, no overlap is anomaly)
            #   30s-5min  → 0.5 (may be checking docs or brief switch)
            #   5-30min   → 0.2 (working memory refreshed, new task normal)
            #   >30min    → 0.0 (synaptic augmentation gone, equivalent to new session)

            # Dimension 2: Referential dissonance
            # Distinguish "topic shift" (user actively switches, no referential words)
            # from "context break" (user tries to maintain topic but system cannot link)
            referential_dissonance = self._referential_dissonance(text_lower, history)
            # Strong referential + no entity match → 0.85 (true break)
            # No referential intent → 0.0 (normal new task / topic shift)

            # Dimension 3: Discursive shift (memory chunk refresh)
            discursive_shift = self._discursive_shift_score(text_lower, history)
            # High domain concentration + low structural similarity → 0.0 (normal cognitive refresh)
            # Low domain concentration + multi-domain scatter → 0.7 (chaotic break)

            # 3D joint scoring
            context_break_score = temporal_factor * (
                0.4 * referential_dissonance + 0.6 * discursive_shift
            )

            # Topic shift exemption: explicit shift signals
            topic_shift_signals = {
                "换个话题", "另外", "换个问题", "new task", "different thing",
                "说说别的", "by the way", "speaking of", "another question",
            }
            if any(s in text_lower for s in topic_shift_signals):
                context_break_score *= 0.1

            # New task exemption: new-task phrasing + no referential intent
            new_task_signals = {
                "我想", "能不能", "能不能帮我", "可以帮我", "能不能问一下",
                "i want", "can you", "could you", "i'd like", "help me",
            }
            if any(s in text_lower for s in new_task_signals) and not referential_dissonance:
                context_break_score *= 0.2

            noise += min(0.20, context_break_score)

        # 5. Information density (0-0.20)
        if len(query) < 5:
            noise += 0.20
        elif len(query) > 500:
            noise += 0.10

        # 6. Special / Unicode noise (non-alphanumeric, non-CJK, non-space chars)
        special_count = sum(1 for c in text_lower if not c.isalnum() and not c.isspace() and not self._is_cjk(c))
        noise += min(0.15, special_count * 0.02)

        return min(1.0, noise)

    # ── 3D Context Break Detection Methods ───────────────────────────────────

    def _temporal_gap_factor(self, current_time: float, last_time: Optional[float]) -> float:
        """
        Temporal gap factor (τ) based on TBRS model (Puma et al., 2018).
        
        Weight map:
            <30s     → 1.0 (working memory active)
            30s-5min  → 0.5 (decay starting)
            5-30min   → 0.2 (mostly refreshed)
            >30min    → 0.0 (equivalent to new session)
        """
        if last_time is None or current_time <= 0.0:
            return 0.0
        gap_seconds = current_time - last_time
        if gap_seconds < 0:
            # Clock skew or stale data — treat as unknown gap
            return 0.5
        if gap_seconds < 30:
            return 1.0
        elif gap_seconds < 300:
            return 0.5
        elif gap_seconds < 1800:
            return 0.2
        else:
            return 0.0

    def _referential_dissonance(self, query_lower: str, history: List[HistoryEntry]) -> float:
        """
        Referential dissonance: distinguish topic shift from context break.
        
        Based on Anaphora Resolution & Matsumoto et al. (2022) speech intention theory.
        
        Returns:
            0.85 — strong referential + no entity overlap (true break)
            0.0  — no referential intent (normal new task / topic shift)
        """
        strong_referential = {
            "这个", "那个", "它", "刚才", "之前", "上面", "前面",
            "this one", "that", "it", "the previous", "the one above",
        }
        weak_referential = {
            "这里", "那边", "上面", "下面", "here", "there", "above", "below",
        }
        has_strong_ref = any(m in query_lower for m in strong_referential)
        has_weak_ref = any(m in query_lower for m in weak_referential)
        if not has_strong_ref and not has_weak_ref:
            return 0.0  # No referential intent — normal new task or topic shift
        # Check entity overlap with last turn
        if history:
            last_query = history[-1].content.lower()
            has_overlap = self._has_overlap(query_lower, last_query)
            if has_strong_ref and not has_overlap:
                return 0.85  # User clearly wants to refer to old topic but system can't link
        return 0.0

    def _discursive_shift_score(self, query_lower: str, history: List[HistoryEntry]) -> float:
        """
        Discursive shift / memory chunk refresh score.
        
        Based on Nature 2018 (chunking cost) and arXiv:2408.07637 (synaptic augmentation).
        
        High domain concentration + low structural similarity → 0.0 (normal refresh)
        Low domain concentration + multi-domain scatter → 0.7 (chaotic break)
        """
        domain_concentration = self._compute_domain_concentration(query_lower)
        if domain_concentration >= 0.7:
            return 0.0  # Normal chunk switch or discursive variation
        elif domain_concentration < 0.3:
            return 0.7  # Chaotic break
        return 0.2

    def _compute_domain_concentration(self, query_lower: str) -> float:
        """
        Compute semantic domain concentration of the query.
        
        Returns 0.0–1.0:
            1.0 — all matched keywords fall in a single domain (highly focused)
            0.0 — scattered across many domains or no domain match
        """
        domains = {
            "memory": ["scan", "read", "write", "address", "pointer", "value", "data", "bytes", "length",
                       "内存", "地址", "指针", "数值", "数据", "字节", "长度"],
            "static": ["disassemble", "decompile", "ghidra", "ida", "function", "instruction", "opcode",
                       "反汇编", "反编译", "函数", "指令", "操作码"],
            "dynamic": ["debug", "trace", "breakpoint", "hook", "run", "execute", "step", "continue",
                        "调试", "断点", "追踪", "挂钩", "运行", "执行", "单步"],
            "crypto": ["unpack", "decrypt", "obfuscate", "protection", "packer", "vm", "virtualize",
                       "脱壳", "解密", "混淆", "保护", "虚拟机"],
            "symbolic": ["angr", "z3", "symbolic", "constraint", "solver", "satisfiability", "theorem",
                         "符号执行", "约束", "求解器", "可满足性"],
            "network": ["socket", "packet", "protocol", "tcp", "udp", "http", "dns", "connection",
                        "套接字", "数据包", "协议", "连接"],
        }
        matched_counts: Dict[str, int] = {}
        total_matches = 0
        for domain, keywords in domains.items():
            count = sum(1 for k in keywords if k in query_lower)
            if count > 0:
                matched_counts[domain] = count
                total_matches += count
        if not matched_counts:
            return 0.5  # Neutral — no domain-specific keywords detected
        # Concentration = max domain share / total matches
        max_share = max(matched_counts.values()) / total_matches
        return max_share

    def _has_verb(self, text: str) -> bool:
        """Simple heuristic: check for action verbs."""
        verbs = [
            "scan", "read", "write", "patch", "find", "change", "set", "lock",
            "分析", "扫描", "读取", "写入", "修改", "查找", "改变", "设置", "锁定",
            "disassemble", "debug", "trace", "hook", "dump",
            "反汇编", "调试", "追踪", "脱壳",
        ]
        return any(v in text for v in verbs)

    def _has_garbled(self, text: str) -> bool:
        """Check for garbled text (excessive special chars, invisible chars)."""
        if not text:
            return False
        special_ratio = sum(1 for c in text if ord(c) < 32 or (ord(c) > 126 and not self._is_cjk(c))) / len(text)
        return special_ratio > 0.3

    def _count_gibberish_words(self, text: str) -> int:
        """Count words that look like random/gibberish strings."""
        words = text.split()
        count = 0
        for word in words:
            clean = re.sub(r'[^a-z]', '', word.lower())
            if len(clean) >= 6:
                # Long runs of consonants without vowels
                consonant_runs = re.findall(r'[^aeiouy]{4,}', clean)
                if consonant_runs:
                    vowels = sum(1 for c in clean if c in 'aeiouy')
                    if vowels / len(clean) < 0.2:
                        count += 1
        return count

    def _is_cjk(self, c: str) -> bool:
        """Check if character is CJK."""
        o = ord(c)
        return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or
                0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF)

    def _has_overlap(self, a: str, b: str) -> bool:
        """Check if two texts share significant vocabulary or technical keywords."""
        stop_words = {
            "the", "a", "an", "to", "of", "in", "on", "at", "for", "with", "this", "that",
            "is", "are", "be", "been", "and", "or", "but", "if", "then", "else", "as", "by", "from",
            "up", "down", "out", "over", "under", "again", "further", "here", "there", "when", "where",
            "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
            "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "can", "will",
            "should", "now", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
            "my", "your", "his", "its", "our", "their", "mine", "yours", "hers", "ours", "theirs",
        }
        words_a = set(a.split()) - stop_words
        words_b = set(b.split()) - stop_words
        if not words_a or not words_b:
            return False
        # Direct meaningful word overlap
        if words_a & words_b:
            return True
        # Shared technical keywords (must be the SAME keyword)
        tech_keywords = {
            "scan", "disassemble", "memory", "breakpoint", "hook", "patch", "read", "write", "trace",
            "dump", "attach", "detach", "find", "search", "locate", "change", "set", "lock", "freeze",
            "扫描", "反汇编", "内存", "断点", "追踪", "修改", "读取", "写入", "查找", "搜索", "定位",
        }
        tech_a = words_a & tech_keywords
        tech_b = words_b & tech_keywords
        return bool(tech_a & tech_b)


# ═══════════════════════════════════════════════════════════════════════════════
# Complexity Estimator
# ═══════════════════════════════════════════════════════════════════════════════

class ComplexityEstimator:
    """Rule-based complexity estimation with YAML config support."""

    def __init__(self, config_path: Optional[str] = None):
        self._rules: List[Dict[str, Any]] = []
        self._complexity_map: Dict[str, float] = {}
        if config_path and os.path.exists(config_path):
            self._load_config(config_path)
        self._default_rules()

    def _load_config(self, path: str) -> None:
        """Load complexity rules from YAML file."""
        if yaml is None:
            logger.warning("PyYAML not available, skipping YAML config load")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and isinstance(data, dict):
                self._rules = data.get("complexity_rules", [])
                self._complexity_map = data.get("complexity_map", {})
        except Exception as e:
            logger.warning(f"Failed to load complexity config from {path}: {e}")

    def _default_rules(self) -> None:
        """Built-in default rules if no config file."""
        if not self._rules:
            self._rules = [
                {"pattern": r"first.*then|first.*and.*then", "base": 0.3},
                {"pattern": r"first.*then.*finally", "base": 0.3},
                {"pattern": r"if.*then.*otherwise", "base": 0.4},
                {"pattern": r"反汇编.*0x[0-9a-f]+", "base": 0.2},
                {"pattern": r"扫描.*然后.*修改", "base": 0.7},
                {"pattern": r"扫描.*修改", "base": 0.6},
                {"pattern": r"找到.*然后.*", "base": 0.5},
                {"pattern": r"脱壳.*反混淆.*反调试", "base": 0.9},
                {"pattern": r"分析.*保护", "base": 0.5},
                {"pattern": r"基址.*指针链", "base": 0.8},
                {"pattern": r"批量.*修改", "base": 0.7},
                {"pattern": r"angr.*z3", "base": 0.85},
                {"pattern": r"frida.*hook.*同时.*scan", "base": 0.9},
            ]

    def estimate(self, query: str, expectation: str) -> float:
        """Estimate complexity level."""
        # 0. Check complexity map override first
        if expectation in self._complexity_map:
            return self._complexity_map[expectation]

        complexity = 0.0
        text_lower = query.lower()

        # 1. Base complexity from length
        complexity += min(0.1, len(query) / 500.0)

        # 2. Base complexity from rules
        for rule in self._rules:
            try:
                if re.search(rule["pattern"], text_lower, re.IGNORECASE):
                    complexity += rule.get("base", 0.0)
            except re.error:
                continue

        # 3. Step count: conjunctions imply multi-step
        step_markers = ["然后", "接着", "再", "之后", "and then", "then", "after", "next", "finally"]
        step_count = sum(1 for m in step_markers if m in text_lower)
        complexity += min(0.3, step_count * 0.10)

        # 4. Domain span: cross-domain increases complexity
        domains = {
            "memory": ["scan", "read", "write", "address", "pointer", "内存", "地址", "指针"],
            "static": ["disassemble", "decompile", "ghidra", "反汇编", "反编译"],
            "dynamic": ["debug", "trace", "breakpoint", "hook", "调试", "断点", "追踪"],
            "crypto": ["unpack", "decrypt", "obfuscate", "protection", "脱壳", "解密", "混淆"],
            "symbolic": ["angr", "z3", "symbolic", "constraint", "符号执行", "约束求解"],
        }
        matched = sum(1 for kws in domains.values() if any(k in text_lower for k in kws))
        if matched > 1:
            complexity += (matched - 1) * 0.15

        # 5. Expectation adjustment
        if expectation == "TOOL":
            complexity *= 0.8
        elif expectation == "COMPANION":
            complexity *= 1.2

        return min(1.0, max(0.0, complexity))


# ═══════════════════════════════════════════════════════════════════════════════
# Cognitive Profiler
# ═══════════════════════════════════════════════════════════════════════════════

class CognitiveProfiler:
    """
    EMA-based cognitive profiling with 4 dimensions.
    
    Maintains per-session state (last_topic, last_text) and updates
    dimensions via exponential moving average.
    """

    _META_MARKERS = {
        "我理解对吗", "是不是这样", "对吗", "确认一下", "我的理解",
        "我这样想对吗", "对不对", "这样对吗", "理解正确吗",
        "am i right", "do i understand", "is my understanding",
        "correct me if", "confirm", "verify my",
    }

    _OPEN_MARKERS = {
        "为什么", "怎么", "什么", "哪里", "如何", "如果", "假如", "会怎样",
        "why", "how", "what", "where", "if", "would", "could", "might",
        "explain", "tell me about", "what do you think", "how about",
    }

    _TECH_TOPICS = {
        "scan", "disassemble", "memory", "breakpoint", "hook", "dump",
        "read", "write", "patch", "trace", "unpack", "obfuscate",
        "扫描", "反汇编", "内存", "断点", "追踪", "读取", "写入",
        "修改", "脱壳", "混淆", "指针", "地址", "hook",
    }

    def __init__(self, user_type_hint: Optional[str] = None):
        """
        P1 修复：显式冷启动策略。
        
        user_type_hint: "expert" | "novice" | None（未知，需探测）
        """
        self.user_type_hint = user_type_hint
        self.turn_count = 0
        self.last_topic: Optional[str] = None
        self.last_text = ""
        
        if user_type_hint == "expert":
            # 专家预设：高元认知，低发散（目标明确），高稳定性
            self.metacognition = 0.8
            self.divergence = 0.2
            self.stability = 0.9
            self.confidence = 0.5
            self.tracking_depth = 0.0
        elif user_type_hint == "novice":
            # 新手预设：低元认知，高发散（可能探索性提问），低稳定性
            self.metacognition = 0.1
            self.divergence = 0.8
            self.stability = 0.3
            self.confidence = 0.2
            self.tracking_depth = 0.0
        else:
            # 未知：使用中性值，但通过首轮输入快速探测
            self.metacognition = 0.5  # 中性，不偏不倚
            self.divergence = 0.5
            self.stability = 0.5
            self.confidence = 0.3
            self.tracking_depth = 0.0

    def first_turn_probe(self, query: str) -> None:
        """
        P1 修复：首轮探测。
        
        根据输入特征快速调整初始画像：
        - 多个技术术语 + 精确参数 → 可能是专家
        - 模糊输入（"帮我看一下"）+ 无参数 → 可能是新手
        """
        if self.user_type_hint is not None:
            return  # 已有预设，跳过探测
        
        technical_terms = {
            "基址", "偏移", "oep", "iat", "eat", "rva", "va", "pe", "elf", 
            "hook", "patch", "dump", "脱壳", "混淆", "反汇编", "断点",
            "寄存器", "eax", "ebx", "ecx", "esp", "ebp", "栈", "堆",
        }
        has_precise_params = bool(re.search(r'0x[0-9a-fA-F]+|\d+\.exe|PID\s*\d+', query))
        term_count = sum(1 for t in technical_terms if t in query.lower())
        
        if term_count >= 2 and has_precise_params:
            # 专家信号强烈 → 提升元认知和稳定性
            self.metacognition = 0.8
            self.stability = 0.9
            self.divergence = 0.2
            self.confidence = 0.6
        elif term_count == 0 and not has_precise_params:
            # 新手信号 → 降低元认知，提高发散性
            self.metacognition = 0.1
            self.divergence = 0.8
            self.stability = 0.3
            self.confidence = 0.2
        # 否则保持中性，让后续轮次自然收敛

    def update(self, query: str, expectation: str) -> CognitiveProfile_v1:
        """Update cognitive profile with a new turn."""
        self.turn_count += 1
        text_lower = query.lower().strip()

        # P1 修复：首轮探测（仅在第一次 update 时调用）
        if self.turn_count == 1 and self.user_type_hint is None:
            self.first_turn_probe(query)

        # 1. Metacognition (EMA alpha=0.25)
        has_meta = any(m in text_lower for m in self._META_MARKERS)
        # Analytical queries also indicate metacognitive awareness
        if expectation in ("ADVISOR", "ANALYZE"):
            has_meta = True
        self.metacognition = self._ema(self.metacognition, 1.0 if has_meta else 0.0, alpha=0.25)

        # 2. Divergence (EMA alpha=0.20)
        is_open = any(text_lower.startswith(m) for m in self._OPEN_MARKERS) or \
                  any(m in text_lower for m in self._OPEN_MARKERS)
        self.divergence = self._ema(self.divergence, 1.0 if is_open else 0.0, alpha=0.20)

        # 3. Tracking depth (topic continuity counter)
        current_topic = self._extract_topic(text_lower)
        if current_topic and current_topic == self.last_topic:
            self.tracking_depth += 1.0
        else:
            if current_topic:
                self.tracking_depth = 1.0
            else:
                self.tracking_depth = max(0.0, self.tracking_depth * 0.75)
        self.last_topic = current_topic

        # 4. Stability (Jaccard similarity with previous turn)
        # v2.3.1 fix: first-turn stability is no longer fixed at 1.0.
        # Instead, estimate noise from input quality so vague/opening turns
        # start with low stability and converge faster (within 2 turns).
        if self.last_text:
            self.stability = self._jaccard_similarity(text_lower, self.last_text)
        else:
            first_turn_noise = self._estimate_first_turn_noise(text_lower)
            self.stability = 1.0 - first_turn_noise
        self.last_text = text_lower

        # 5. Confidence (based on turn count and stability)
        self.confidence = min(1.0, self.turn_count * 0.05 + self.stability * 0.3)

        return self.get_profile()

    def get_profile(self) -> CognitiveProfile_v1:
        """Return current cognitive profile."""
        return CognitiveProfile_v1(
            metacognition=self.metacognition,
            divergence=self.divergence,
            tracking_depth=self.tracking_depth,
            stability=self.stability,
            confidence=self.confidence,
        )

    def reset(self) -> None:
        """Reset all state to initial values."""
        self.metacognition = 0.0
        self.divergence = 0.0
        self.tracking_depth = 0.0
        self.stability = 0.0
        self.confidence = 0.0
        self.last_topic = None
        self.last_text = ""
        self.turn_count = 0

    @staticmethod
    def _ema(prev: float, current: float, alpha: float) -> float:
        """Exponential moving average."""
        return alpha * current + (1.0 - alpha) * prev

    @staticmethod
    def _jaccard_similarity(a: str, b: str) -> float:
        """Jaccard similarity between two texts."""
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return 0.0
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return intersection / union if union > 0 else 0.0

    def _extract_topic(self, text: str) -> Optional[str]:
        """Extract dominant technical topic."""
        for topic in self._TECH_TOPICS:
            if topic in text:
                return topic
        return None

    def _estimate_first_turn_noise(self, text: str) -> float:
        """
        Estimate input-quality noise for the first turn.
        
        High noise → low initial stability, so EMA converges to the true
        user profile within 2 turns instead of being locked to 1.0.
        
        Heuristic thresholds (YAML-configurable in production):
          - Vague words ("那个", "这个", "东西", "搞", "弄"): +0.15 each, cap 0.60
          - Very short input (<10 chars): +0.20
          - No action verbs: +0.10
        """
        noise = 0.0
        vague_words = {
            "那个", "这个", "东西", "搞", "弄", "整", "一下",
            "那个啥", "这个啥", "啥", "啥子", "咋", "咋弄",
        }
        vague_count = sum(1 for w in vague_words if w in text)
        noise += min(0.60, vague_count * 0.15)

        if len(text) < 10:
            noise += 0.20

        action_verbs = [
            "scan", "read", "write", "patch", "dump", "trace",
            "分析", "扫描", "读取", "写入", "修改", "追踪",
            "查看", "检查", "搜索", "查找", "定位", "设置",
        ]
        if not any(v in text for v in action_verbs):
            noise += 0.10

        return min(1.0, noise)


# ═══════════════════════════════════════════════════════════════════════════════
# RuleBasedPCR (Main Implementation)
# ═══════════════════════════════════════════════════════════════════════════════

class RuleBasedPCR(IPCRRouter):
    """
    Zero-dependency rule-based PCR implementation.
    
    Latency: < 10ms for rule path, < 250ms if LLM fallback triggered.
    """

    def __init__(self):
        self._identifier = ExpectationIdentifier()
        self._noise_estimator = NoiseEstimator()
        self._complexity_estimator = ComplexityEstimator()
        self._profiler = CognitiveProfiler()
        self._telemetry = TelemetryCollector()
        self._config: Dict[str, Any] = {}
        self._health = PCRHealthStatus.WARMING

    @property
    def name(self) -> str:
        return "rule_based"

    @property
    def version(self) -> str:
        return "1.0.0"

    def warm_up(self, config: Dict[str, Any]) -> None:
        """Warm up: load config, compile regexes, init complexity estimator."""
        self._config = config
        complexity_map = config.get("complexity_map")
        if complexity_map:
            self._complexity_estimator = ComplexityEstimator(complexity_map)
        else:
            self._complexity_estimator = ComplexityEstimator()
        self._health = PCRHealthStatus.HEALTHY
        logger.info(f"{self.name} warmed up with config: {config}")

    def shutdown(self) -> None:
        """Graceful shutdown. Idempotent."""
        self._health = PCRHealthStatus.UNHEALTHY
        logger.info(f"{self.name} shut down")

    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """
        Evaluate user input and return cognitive state packet.
        
        P1 修复：支持从 metadata 传入 user_type_hint 用于冷启动。
        
        Pipeline:
          1. Expectation identification (rules → history → LLM fallback)
          2. Noise estimation
          3. Complexity estimation
          4. Cognitive profiling update
          5. Assemble PCROutput_v1 with derived strategies
        """
        start = time.time()
        query = input_data.query
        history = input_data.session_history

        # P1 修复：从 metadata 读取 user_type_hint
        user_type_hint = input_data.metadata.get("user_type_hint")
        if user_type_hint and self._profiler.user_type_hint != user_type_hint:
            # 如果 hint 改变，重置 profiler 以应用新的初始值
            self._profiler = CognitiveProfiler(user_type_hint=user_type_hint)

        # 1. Expectation identification
        expectation, exp_confidence = self._identifier.identify(query, history)

        # 2. Noise estimation (with 3D cognitive refresh awareness)
        noise = self._noise_estimator.estimate(query, history, input_data.timestamp)

        # 3. Complexity estimation
        complexity = self._complexity_estimator.estimate(query, expectation)

        # 4. Cognitive profiling
        cog_profile = self._profiler.update(query, expectation)

        # 5. Derive execution strategies
        execution_mode = self._derive_execution_mode(expectation, noise, complexity)
        prompt_style = self._derive_prompt_style(expectation, cog_profile)
        ambiguity_strategy = self._derive_ambiguity_strategy(noise, expectation)
        noise_source = self._detect_noise_source(query, history, noise, input_data.timestamp)
        parser_overrides = self._derive_parser_overrides(noise, complexity, cog_profile, noise_source)

        # 6. Suggestions and hints
        suggestions = self._derive_suggestions(expectation, input_data)
        should_attach = self._should_attach_process(input_data)
        should_refresh = self._should_refresh_analysis(input_data)

        # 7. Build trace log
        trace = [
            f"[RuleBasedPCR] expectation={expectation} (conf={exp_confidence:.2f})",
            f"[RuleBasedPCR] noise={noise:.2f} complexity={complexity:.2f}",
            f"[RuleBasedPCR] cognitive={cog_profile.to_dict()}",
            f"[RuleBasedPCR] execution_mode={execution_mode} prompt_style={prompt_style}",
        ]

        latency = (time.time() - start) * 1000.0

        # Record telemetry
        self._telemetry.record(latency_ms=latency, error=False, cache_hit=False)

        return PCROutput_v1(
            expectation=expectation,
            noise_level=noise,
            complexity_level=complexity,
            cognitive_profile=cog_profile,
            execution_mode=execution_mode,
            parser_config_overrides=parser_overrides,
            prompt_style=prompt_style,
            ambiguity_strategy=ambiguity_strategy,
            suggested_next_actions=suggestions,
            should_attach_process=should_attach,
            should_refresh_analysis=should_refresh,
            trace_log=trace,
            latency_ms=latency,
            implementation=self.name,
        )

    def get_health(self) -> PCRHealthStatus:
        return self._health

    def get_telemetry(self) -> Dict[str, Any]:
        return self._telemetry.get_stats()

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supported_expectations": ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"],
            "has_cognitive_profile": True,
            "has_noise_estimation": True,
            "has_complexity_estimation": True,
            "requires_llm": False,  # Optional fallback only
            "latency_range_ms": [0, 10],
            "supports_hot_reload": True,
            "supports_rules": True,
            "config_schema": self.get_schema(),
        }

    def get_schema(self) -> Dict[str, Any]:
        return {
            "version": "v1",
            "type": "rule_based",
            "properties": {
                "complexity_map": {
                    "type": "string",
                    "description": "Path to YAML complexity rules file",
                },
                "llm_fallback": {
                    "type": "boolean",
                    "description": "Enable LLM fallback for ambiguous inputs",
                    "default": False,
                },
                "cache_ttl_sec": {
                    "type": "number",
                    "description": "LLM fallback cache TTL in seconds",
                    "default": 300,
                },
            },
        }

    def reload_config(self, config: Dict[str, Any]) -> bool:
        """Hot reload: update complexity estimator config."""
        try:
            self._config.update(config)
            complexity_map = config.get("complexity_map")
            if complexity_map:
                self._complexity_estimator = ComplexityEstimator(complexity_map)
            return True
        except Exception as e:
            logger.error(f"Hot reload failed: {e}")
            return False

    # ── Strategy derivation helpers ─────────────────────────────────────────

    def _derive_execution_mode(self, expectation: str, noise: float, complexity: float) -> str:
        if expectation == "UNKNOWN" or noise > 0.8:
            return "CONSERVATIVE"
        if expectation == "TOOL" and noise < 0.3 and complexity < 0.5:
            return "AGGRESSIVE"
        if expectation == "ADVISOR" and complexity > 0.7:
            return "BALANCED"
        if expectation == "COMPANION":
            return "BALANCED"
        return "BALANCED"

    def _derive_prompt_style(self, expectation: str, cog: CognitiveProfile_v1) -> str:
        if expectation == "UNKNOWN":
            return "CONSERVATIVE"
        if expectation == "COMPANION":
            return "CONSERVATIVE"
        if expectation == "ADVISOR":
            return "BALANCED"
        return "AGGRESSIVE"

    def _derive_ambiguity_strategy(self, noise: float, expectation: str) -> str:
        if noise > 0.7 and expectation == "TOOL":
            return "CONSERVATIVE_ASK"
        if noise < 0.3 and expectation == "ADVISOR":
            return "AGGRESSIVE_AUTO"
        return "BALANCED"

    def _derive_parser_overrides(self, noise: float, complexity: float,
                                 cog: CognitiveProfile_v1, noise_source: Optional[str] = None) -> Dict[str, Any]:
        overrides = {}
        if noise < 0.4:
            overrides["auto_resolve_threshold"] = 0.7
            overrides["max_ambiguities_before_ask"] = 5
        elif noise < 0.7:
            overrides["auto_resolve_threshold"] = 0.5
            overrides["max_ambiguities_before_ask"] = 3
        else:
            overrides["auto_resolve_threshold"] = 0.3
            overrides["max_ambiguities_before_ask"] = 1

        if cog.confidence > 0.7:
            overrides["min_confidence_threshold"] = 0.6
        elif cog.confidence > 0.3:
            overrides["min_confidence_threshold"] = 0.4
        else:
            overrides["min_confidence_threshold"] = 0.25

        if complexity > 0.8:
            overrides["max_sub_intents"] = 10
        elif complexity > 0.5:
            overrides["max_sub_intents"] = 5
        else:
            overrides["max_sub_intents"] = 3

        # v2.2: noise source awareness for downstream ParserConfig tuning
        if noise_source:
            overrides["noise_source"] = noise_source

        return overrides

    def _detect_noise_source(self, query: str, history: List[HistoryEntry],
                             noise: float, current_time: float) -> Optional[str]:
        """
        Detect the dominant noise source for downstream ParserConfig tuning.

        Returns 'referential_dissonance' when:
            - noise is high (>0.5)
            - query contains strong referential words but no overlap with history
            - short temporal gap (working memory active, so disconnection is abnormal)
        """
        if noise < 0.5 or not history or not query:
            return None
        text_lower = query.lower().strip()
        strong_referential = {
            "这个", "那个", "它", "刚才", "之前", "上面", "前面",
            "this one", "that", "it", "the previous", "the one above",
        }
        has_strong_ref = any(m in text_lower for m in strong_referential)
        if not has_strong_ref:
            return None
        # Check temporal gap: if gap is long, it's a normal refresh, not dissonance
        last_time = getattr(history[-1], 'timestamp', None)
        temporal_factor = self._noise_estimator._temporal_gap_factor(
            current_time if current_time else 0.0, last_time
        )
        if temporal_factor < 0.5:
            # Long gap: user may have forgotten, not true dissonance
            return None
        # Check entity overlap
        last_query = history[-1].content.lower()
        has_overlap = self._noise_estimator._has_overlap(text_lower, last_query)
        if has_strong_ref and not has_overlap:
            return "referential_dissonance"
        return None

    def _derive_suggestions(self, expectation: str, input_data: PCRInput_v1) -> List[str]:
        if expectation == "UNKNOWN":
            return ["反汇编入口点", "扫描内存数值", "分析程序保护"]
        if expectation == "COMPANION":
            return ["反汇编入口点", "扫描内存数值", "分析程序保护"]
        return []

    def _should_attach_process(self, input_data: PCRInput_v1) -> bool:
        """Check if user needs to attach a process."""
        pc = input_data.process_context
        if not pc:
            return True
        pid = pc.get("pid")
        return pid is None or pid == 0

    def _should_refresh_analysis(self, input_data: PCRInput_v1) -> bool:
        """Check if process analysis should be refreshed."""
        pc = input_data.process_context
        if not pc:
            return False
        # Refresh if process switched or analysis is stale
        return pc.get("stale", False) or pc.get("process_switched", False)


# ═══════════════════════════════════════════════════════════════════════════════
# Registration (auto-register on import)
# ═══════════════════════════════════════════════════════════════════════════════

from core.agent.pcr.registry import register_pcr
register_pcr("rule_based", RuleBasedPCR)
