# -*- coding: utf-8 -*-
"""
core/agent/intent_parser.py
─────────────────────────────
Industrial-grade Layer 1: Intent Parser.

Pipeline:
    Raw Input → Preprocessor → Entity Extractor → Rule Classifier →
    Ambiguity Detector → Multi-Intent Splitter → Context Merger →
    TaskGraph Builder → ParseResult

Design principles:
  1. Deterministic first (rules + regex), LLM fallback only when needed.
  2. Every stage is traceable (trace_log).
  3. Ambiguity is a first-class citizen, not an afterthought.
  4. Multi-turn context inheritance is explicit and typed.
  5. Extensible: new intent categories / entity types are single-registry additions.
"""

from __future__ import annotations

import re
import time
import json
import threading
import logging
from typing import Dict, List, Any, Optional, Tuple, Set, Callable, Pattern
from collections import defaultdict
from dataclasses import dataclass, field

from core.agent.models import (
    Intent, IntentCategory, Entity, EntityType, Ambiguity, AmbiguityType,
    TaskNode, TaskGraph, TaskEdge, TaskStatus, DependencyType,
    ParseResult, ParseContext, ParserConfig, ConfidenceLevel,
    UserExpectation, IntentContext, CognitiveProfile,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════════

logger = logging.getLogger("intent_parser")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    ))
    logger.addHandler(_handler)


# ═══════════════════════════════════════════════════════════════════════════════
# Registry & Configuration
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class IntentRule:
    """A rule for classifying user input into an IntentCategory."""
    category: IntentCategory
    # Trigger patterns (case-insensitive regex)
    patterns: List[Pattern] = field(default_factory=list)
    # Required entity types for this rule to fire (AND logic)
    required_entities: List[EntityType] = field(default_factory=list)
    # Optional entity types that boost confidence
    optional_entities: List[EntityType] = field(default_factory=list)
    # Minimum confidence threshold for this rule
    min_confidence: float = 0.5
    # Priority (higher = evaluated first)
    priority: int = 0
    # Is this a compound / high-level intent that should be decomposed?
    is_compound: bool = False
    # Compound-specific: expected sub-intent categories after decomposition
    decomposition_hints: List[IntentCategory] = field(default_factory=list)
    # Rule name for reference in conflict declarations
    name: str = ""
    # Names of other rules this rule conflicts with
    conflicts_with: List[str] = field(default_factory=list)
    # Domain for grouping rules (e.g., "memory", "code", "dynamic")
    domain: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=False)
class EntityExtractorRule:
    """A rule for extracting a specific EntityType from text."""
    entity_type: EntityType
    # Regex patterns with named groups: the group named 'value' is extracted
    patterns: List[Pattern] = field(default_factory=list)
    # Post-processing function: raw_str → Any (or None to drop)
    normalizer: Optional[Callable[[str], Any]] = None
    # Confidence boost for this extractor
    base_confidence: float = 0.8
    # Priority (higher = evaluated first, can override lower-confidence matches)
    priority: int = 0


# ── Intent Rule Registry ──────────────────────────────────────────────────────

from core.agent.intent_rule_registry import IntentRuleRegistry, ConflictReport, IntentRule as _RegistryIntentRule
from core.agent.intent_rule_registry import register_intent_rule as _registry_register, check_rule_conflicts

# 创建全局单例，与旧代码共享
_rule_registry = IntentRuleRegistry()

# 旧全局变量保留（向后兼容，现有代码依赖）
_RULES: List[IntentRule] = []
_ENTITY_RULES: List[EntityExtractorRule] = []
_RULES_LOCK = threading.Lock()


def register_intent_rule(rule: IntentRule) -> None:
    """向后兼容：注册意图规则到全局 Registry（P1 修复）。"""
    # 将旧 IntentRule 转换为 registry 的 IntentRule 格式
    reg_rule = _RegistryIntentRule(
        category=rule.category.value if hasattr(rule.category, 'value') else str(rule.category),
        patterns=rule.patterns,
        required_entities=[e.value if hasattr(e, 'value') else str(e) for e in rule.required_entities],
        optional_entities=[e.value if hasattr(e, 'value') else str(e) for e in rule.optional_entities],
        min_confidence=rule.min_confidence,
        priority=rule.priority,
        is_compound=rule.is_compound,
        decomposition_hints=[c.value if hasattr(c, 'value') else str(c) for c in rule.decomposition_hints],
        name=rule.name,
        domain=rule.domain,
        conflicts_with=rule.conflicts_with,
        metadata=rule.metadata,
    )
    _rule_registry.register(reg_rule)
    # 同时保留旧列表，确保现有代码不破坏
    with _RULES_LOCK:
        _RULES.append(rule)
        _RULES.sort(key=lambda r: -r.priority)


def register_entity_rule(rule: EntityExtractorRule) -> None:
    with _RULES_LOCK:
        _ENTITY_RULES.append(rule)
        _ENTITY_RULES.sort(key=lambda r: -r.priority)


def _compile(patterns: List[str]) -> List[Pattern]:
    """Compile a list of regex strings (case-insensitive, Unicode)."""
    compiled: List[Pattern] = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.IGNORECASE | re.UNICODE))
        except re.error as e:
            logger.error(f"Invalid regex pattern '{p}': {e}")
    return compiled


# ═══════════════════════════════════════════════════════════════════════════════
# Built-in Intent Rules (Deterministic Classification)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Memory: Scan ────────────────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.SCAN_MEMORY,
    patterns=_compile([
        r"(?:scan|扫描|搜索|查找|寻找|search|find|look for)\s+(?:memory|内存|值|value|地址|address)",
        r"(?:first\s*scan|初次扫描|第一次扫描|初始扫描)",
        r"(?:next\s*scan|再次扫描|继续扫描|下一步扫描|next scan)",
        r"(?:scan\s*for|搜索)\s*(?:value|数值|值|血量|金币|分数|生命值|金钱)",
        r"(?:找到|定位|搜索|查找)\s*(?:the\s+)?(?:value|数值|地址|血量|金币|分数)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.NUMERIC_VALUE, EntityType.DATA_TYPE, EntityType.SCAN_TYPE],
    min_confidence=0.6,
    priority=100,
    is_compound=False,
    name="scan_memory",
    domain="memory",
))

# ── Memory: Read ────────────────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.READ_MEMORY,
    patterns=_compile([
        r"(?:read|读取|查看|看看|显示|dump|查看内存|读内存)\s+(?:memory|内存|地址|address|value|数值)?",
        r"(?:read|读取|查看)\s+(?:at|在|from|从)\s*(?:地址|address)?",
        r"(?:看看|显示|dump|查看)\s*(?:0x[0-9A-Fa-f]+|[\d,]+)\s*(?:处|地址|的|内存)?",
        r"(?:what\s*is|是什么|什么内容|什么值)\s*(?:at|在|地址)?\s*(?:0x[0-9A-Fa-f]+|[\d,]+)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MEMORY_ADDRESS, EntityType.MEMORY_SIZE],
    min_confidence=0.6,
    priority=95,
    name="read_memory",
    domain="memory",
))

# ── Memory: Write ───────────────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.WRITE_MEMORY,
    patterns=_compile([
        r"(?:write|写入|修改|改变|设置|改|改成|改成|设置为|set|change|modify)\s+(?:memory|内存|值|value|地址|address)?",
        r"(?:把|将|让)\s*(?:血量|金币|分数|value|值|数值)\s*(?:变成|改为|设置成|等于|=)\s*(?:\d+|0x[0-9A-Fa-f]+)",
        r"(?:lock|锁定|固定|freeze|冻结)\s*(?:value|值|数值|血量|金币)",
        r"(?:hack|作弊|修改|改)\s*(?:value|值|数值|血量|金币|分数)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MEMORY_ADDRESS, EntityType.NUMERIC_VALUE, EntityType.DATA_TYPE],
    min_confidence=0.7,
    priority=100,
    is_compound=True,
    decomposition_hints=[IntentCategory.SCAN_MEMORY, IntentCategory.READ_MEMORY, IntentCategory.WRITE_MEMORY],
    name="write_memory",
    domain="memory",
))

# ── Code: Disassemble ─────────────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.DISASSEMBLE,
    patterns=_compile([
        r"(?:disassemble|反汇编|反编译|查看代码|看代码|asm|assembly|指令|机器码|opcode)",
        r"(?:disassemble|反汇编|查看)\s*(?:at|在|地址|address|function|函数|region|区域)?",
        r"(?:看看|显示|查看)\s*(?:0x[0-9A-Fa-f]+)\s*(?:处|的|地址)?\s*(?:代码|指令|汇编|反汇编)?",
        r"(?:反汇编|disassemble|show\s*code)\s*(?:0x[0-9A-Fa-f]+|function|函数|region|区域)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MEMORY_ADDRESS, EntityType.MEMORY_SIZE, EntityType.FUNCTION_NAME],
    min_confidence=0.6,
    priority=100,
    name="disassemble",
    domain="code",
))

# ── Code: Decompile ─────────────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.DECOMPILE,
    patterns=_compile([
        r"(?:decompile|伪代码|反编译|反编译成C|反编译成伪代码|ghidra|pseudocode|C\s*code)",
        r"(?:伪代码|decompile|反编译)\s*(?:of|函数|function|at|地址|0x)?",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MEMORY_ADDRESS, EntityType.FUNCTION_NAME, EntityType.SYMBOL_NAME],
    min_confidence=0.6,
    priority=90,
    name="decompile",
    domain="code",
))

# ── Code: Analyze Protection ──────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.ANALYZE_PROTECTION,
    patterns=_compile([
        r"(?:analyze|检测|分析|检查|查看)\s*(?:protection|保护|加壳|壳|packer|pack|anti[-_]?debug|反调试|混淆|obfuscation|entropy|熵)",
        r"(?:packer|加壳|壳|壳分析|检测壳|识别壳|脱壳前检测)",
        r"(?:anti[-_]?debug|反调试|反调试检测|调试器检测|检测调试器)",
        r"(?:obfuscation|混淆|代码混淆|字符串加密|控制流平坦化)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MODULE_NAME, EntityType.MEMORY_ADDRESS],
    min_confidence=0.6,
    priority=85,
    name="analyze_protection",
    domain="code",
))

# ── Code: Deobfuscate ───────────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.DEOBFUSCATE,
    patterns=_compile([
        r"(?:deobfuscate|反混淆|去除花指令|去除混淆|去平坦化|deobfuscate|unflatten|restore|还原|清理|clean)\s*(?:code|代码|函数|function)?",
        r"(?:去除|去掉|删除|移除)\s*(?:junk|花指令|垃圾代码|虚假分支|死代码|obfuscation|混淆)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MEMORY_ADDRESS, EntityType.FUNCTION_NAME, EntityType.MEMORY_SIZE],
    min_confidence=0.6,
    priority=85,
    name="deobfuscate",
    domain="code",
))

# ── Code: Unpack ────────────────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.UNPACK,
    patterns=_compile([
        r"(?:unpack|脱壳|dump|转储|提取|unpacker|oep|入口点|原始入口点)",
        r"(?:脱壳|dump|unpack|提取)\s*(?:模块|module|程序|exe|dll|文件|file|image|镜像)?",
        r"(?:提取|转储|dump)\s*(?:原始|未加壳|unpacked|原始代码|原始数据)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MODULE_NAME, EntityType.MEMORY_ADDRESS],
    min_confidence=0.6,
    priority=85,
    name="unpack",
    domain="code",
))

# ── Dynamic: Breakpoint ───────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.SET_BREAKPOINT,
    patterns=_compile([
        r"(?:set|设置|下|打|添加|place)\s*(?:breakpoint|断点|bp|hook|钩子|拦截点)",
        r"(?:breakpoint|断点|bp)\s*(?:at|在|on|针对|地址|address|function|函数|when|当|if|如果)?",
        r"(?:当|when|if|如果|一旦)\s*(?:写入|读取|执行|访问|修改|write|read|execute|access|modify)\s*(?:时|地址|at|0x)?",
        r"(?:trace|跟踪|tracepoint|追踪点|trace|trace|记录|log)\s*(?:writes|reads|accesses|写入|读取|访问)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MEMORY_ADDRESS, EntityType.BREAKPOINT_TYPE, EntityType.FUNCTION_NAME],
    min_confidence=0.6,
    priority=90,
    name="set_breakpoint",
    domain="dynamic",
))

# ── Dynamic: Get Breakpoint Hits ──────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.GET_BREAKPOINT_HITS,
    patterns=_compile([
        r"(?:get|查看|显示|list|列出|有什么|多少)\s*(?:breakpoint|断点|bp)\s*(?:hits|命中|结果|记录|触发|日志|log|trace|trace)?",
        r"(?:断点|breakpoint|bp)\s*(?:命中|触发|结果|记录|日志|log|trace|trace|记录|history|历史)",
    ]),
    required_entities=[],
    optional_entities=[],
    min_confidence=0.6,
    priority=85,
    name="get_breakpoint_hits",
    domain="dynamic",
))

# ── Pattern: Find Pattern ───────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.FIND_PATTERN,
    patterns=_compile([
        r"(?:find|搜索|查找|寻找|search|scan|匹配|match|pattern|aob|signature|sig|特征码|特征|字节特征|hex|十六进制)",
        r"(?:aob|signature|sig|特征码|特征|字节特征|pattern|模式|模板|hex|十六进制)\s*(?:scan|search|搜索|扫描|查找|匹配|match)?",
        r"(?:查找|搜索|匹配|找|scan|search)\s*(?:signature|特征|特征码|pattern|模式|hex|十六进制|bytes|字节)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.BYTE_PATTERN, EntityType.MEMORY_ADDRESS, EntityType.MEMORY_SIZE],
    min_confidence=0.6,
    priority=85,
    name="find_pattern",
    domain="pattern",
))

# ── Pattern: Pattern Detect (ML) ────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.PATTERN_DETECT,
    patterns=_compile([
        r"(?:pattern|模式|行为|behavior|heuristic|启发式|anomaly|异常|detect|检测|识别|classify|分类|AI|机器学习|ML|model|模型)\s*(?:detect|detection|检测|识别|分析|analysis|识别|classification|分类)",
        r"(?:detect|检测|识别|发现|发现| classify|分类|识别)\s*(?:pattern|模式|行为|behavior|anomaly|异常|signature|特征|heuristic|启发式)",
    ]),
    required_entities=[],
    optional_entities=[],
    min_confidence=0.5,
    priority=80,
    name="pattern_detect",
    domain="pattern",
))

# ── Symbolic: Build CFG ─────────────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.BUILD_CFG,
    patterns=_compile([
        r"(?:build|构建|生成|construct|create|建立)\s*(?:cfg|控制流图|控制流|control\s*flow\s*graph|flow\s*graph|graph|图|angr)",
        r"(?:cfg|控制流图|控制流|flow\s*graph|graph|图)\s*(?:build|构建|生成|analysis|分析|for|of|函数|function|模块|module)?",
        r"(?:angr|符号执行|符号分析|符号)\s*(?:cfg|控制流图|分析|analysis|build|构建)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MODULE_NAME, EntityType.MEMORY_ADDRESS],
    min_confidence=0.6,
    priority=80,
    name="build_cfg",
    domain="symbolic",
))

# ── Symbolic: Symbolic Execute ──────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.SYMBOLIC_EXECUTE,
    patterns=_compile([
        r"(?:symbolic|符号|符号执行|符号分析|符号推理|concolic|混合执行|angr|angr)\s*(?:execute|execution|执行|分析|analysis|explore|探索|run|运行|emulate|模拟)",
        r"(?:angr|angr)\s*(?:explore|探索|run|运行|execute|执行|symbolic|符号|分析|analysis)",
        r"(?:explore|探索|路径|path|constraint|约束|求解|solve|find|寻找)\s*(?:path|路径|paths|execution|执行|execution|execution|trace|trace|trace)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.MEMORY_ADDRESS, EntityType.FUNCTION_NAME],
    min_confidence=0.6,
    priority=80,
    name="symbolic_execute",
    domain="symbolic",
))

# ── Symbolic: Solve Constraints ─────────────────────────────────────────────
register_intent_rule(IntentRule(
    category=IntentCategory.SOLVE_CONSTRAINTS,
    patterns=_compile([
        r"(?:solve|求解|解|sat|satisfiability|可满足性|约束|constraint|z3|定理证明|prove|证明|验证|verify|check|检查|satisfy|满足|satisfiable|unsatisfiable|infeasible|feasible)",
        r"(?:z3|smt|solver|求解器|求解|check|验证|verify|prove|证明|satisfy|satisfiable|unsatisfiable|infeasible|feasible)\s*(?:solve|求解|求解器|check|检查|验证|verify|prove|证明|求解|satisfy|satisfiable)",
    ]),
    required_entities=[],
    optional_entities=[EntityType.CONDITION, EntityType.MEMORY_ADDRESS],
    min_confidence=0.6,
    priority=80,
    name="solve_constraints",
    domain="symbolic",
))


# ═══════════════════════════════════════════════════════════════════════════════
# Intent Parser Main Class (P12: PCR Fusion Integration)
# ═══════════════════════════════════════════════════════════════════════════════

class IntentParser:
    """
    Industrial-grade Layer 1 Intent Parser.
    
    Accepts IntentContext (from PCR Layer 0) as a control signal and
    dynamically tunes every sub-module via ParserConfig.
    
    Pipeline:
      Raw Input → Preprocessor → Entity Extractor → Intent Classifier →
      Multi-Intent Splitter → Ambiguity Detector → Ambiguity Resolver →
      Context Merger → TaskGraph Builder → ParseResult
    """

    def __init__(self, llm_provider=None, adaptive_threshold=None):
        self._llm_provider = llm_provider
        self._adaptive_threshold = adaptive_threshold
        self._step_markers = re.compile(
            r"(?:and\s+then|then|after|next|first|finally|"
            r"然后|接着|再|之后|同时|并且|先|后|最后)",
            re.IGNORECASE,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def parse(self, user_input: str, intent_context: IntentContext,
              parse_context: ParseContext) -> ParseResult:
        """
        Main entry: parse user input under PCR-driven IntentContext.
        
        Args:
            user_input: Raw user input string.
            intent_context: PCR output translated to Layer-1 context.
            parse_context: Mutable session-level parse context.
        
        Returns:
            ParseResult containing intent, task_graph, and clarifications.
        """
        trace: List[str] = []
        trace.append(f"[IntentParser] expectation={intent_context.expectation.value} "
                     f"noise={intent_context.noise_level:.2f} complexity={intent_context.complexity_level:.2f}")

        # 1. Dynamic config from IntentContext (P11)
        config = ParserConfig.from_intent_context(intent_context)
        trace.append(f"[IntentParser] ParserConfig: min_conf={config.min_confidence_threshold:.2f} "
                     f"max_ambiguities={config.max_ambiguities_before_ask} "
                     f"max_sub_intents={config.max_sub_intents}")

        # 2. Preprocessing (stability-aware vocabulary tuning)
        normalized = self._preprocess(user_input, intent_context)
        trace.append(f"[Stage 0] Normalized: '{normalized[:80]}'")

        # 3. Pre-Stage 3.5: Reference resolution (before entity extraction)
        resolved_text, inherited_entities = self._resolve_references(
            normalized, parse_context, config
        )
        if inherited_entities:
            trace.append(f"[Pre-Stage 3.5] Resolved {len(inherited_entities)} references: "
                         f"{[e.type.value for e in inherited_entities]}")

        # 4. Entity extraction (regulated by expectation)
        entities = self._extract_entities(resolved_text, config, intent_context)
        # Prepend inherited entities so classifier sees them
        entities = inherited_entities + entities
        trace.append(f"[Stage 1] Extracted {len(entities)} entities: "
                     f"{[e.type.value for e in entities]}")

        # 5. Intent classification (regulated by expectation + noise)
        intent, candidates = self._classify(resolved_text, entities, intent_context, config)
        trace.append(f"[Stage 2] Classified: {intent.category.value} (conf={intent.confidence:.2f})")

        # ── Gating / Fast Path ─────────────────────────────────────────────────
        # P0-1: Adaptive threshold regulation for Fast Path.
        entity_threshold = config.fast_path_entity_threshold
        intent_threshold = config.fast_path_intent_threshold
        if self._adaptive_threshold is not None:
            try:
                feat = self._adaptive_threshold.extract_features(
                    rule_confidence=intent.confidence,
                    noise_level=intent_context.noise_level,
                    query=resolved_text,
                )
                entity_threshold, intent_threshold = self._adaptive_threshold.suggest_fast_path(feat)
            except Exception:
                pass  # Fallback to config defaults

        all_entities_high_conf = (
            len(entities) > 0 and all(e.confidence >= entity_threshold for e in entities)
        )
        intent_strong_match = intent.confidence >= intent_threshold
        fast_path = all_entities_high_conf and intent_strong_match

        if fast_path:
            trace.append(f"[Gating] Fast path activated: entity>={entity_threshold:.2f}, "
                         f"intent>={intent_threshold:.2f} — "
                         f"skipping Stage 3-5 (split/ambiguity detect/resolution)")
        else:
            # 5. Multi-intent splitting (regulated by complexity)
            sub_intents = self._split_multi_intent(intent, config, intent_context)
            if sub_intents:
                intent.sub_intents = sub_intents
                trace.append(f"[Stage 3] Split into {len(sub_intents)} sub-intents")

            # 6. Ambiguity detection (regulated by noise + expectation, P2-1 unified)
            ambiguities = self._detect_ambiguities(intent, entities, intent_context, candidates)
            intent.ambiguities = ambiguities
            trace.append(f"[Stage 4] Ambiguities: {len(ambiguities)} ({[a.type.value for a in ambiguities]})")

            # 7. Ambiguity resolution (regulated by auto_resolve_threshold)
            if ambiguities and config.auto_resolve_ambiguities:
                intent = self._resolve_ambiguities(intent, config)
                trace.append(f"[Stage 5] Resolved: remaining={len(intent.ambiguities)}")

        # 8. Context merging (regulated by tracking_depth)
        intent = self._merge_context(intent, parse_context, config)
        trace.append(f"[Stage 6] Merged context: {len(intent.entities)} entities")

        # 9. TaskGraph building (regulated by expectation)
        task_graph = self._build_task_graph(intent, intent_context)
        trace.append(f"[Stage 7] TaskGraph: {len(task_graph.nodes)} nodes, {len(task_graph.edges)} edges")

        # 10. Determine actionable
        is_actionable = not intent.is_ambiguous() and len(intent.ambiguities) == 0
        if not is_actionable:
            clarification = self._build_clarification(intent)
            suggestions = self._build_suggestions(intent, intent_context)
        else:
            clarification = None
            suggestions = []

        # Register in parse context
        parse_context.add_intent(intent)

        result = ParseResult(
            intent=intent,
            task_graph=task_graph if is_actionable else None,
            is_actionable=is_actionable,
            clarification_message=clarification,
            suggestions=suggestions,
            trace_log=trace,
        )
        trace.append(f"[ParseResult] actionable={is_actionable}")
        return result

    # ── Pre-Stage 3.5: Reference Resolution ─────────────────────────────────────

    def _resolve_references(self, text: str, parse_context: ParseContext,
                            config: ParserConfig) -> Tuple[str, List[Entity]]:
        """
        Resolve anaphoric / deictic references BEFORE entity extraction.

        v2.2 fix: previously done in Stage 6 (_merge_context), too late —
        by then Stage 2-5 had already failed due to missing entities.

        Scans for pronouns / demonstratives ("这个地址", "那个值", "it", "that"),
        backtracks parse_context.history for the most recent high-confidence
        entity of matching type, and replaces the reference in text.

        Returns:
            (resolved_text, inherited_entities) — inherited_entities are pre-marked
            so Stage 1 (_extract_entities) can skip re-extraction.
        """
        if not config.inherit_entities_from_context or not parse_context.history:
            return text, []

        inherited: List[Entity] = []
        resolved = text

        # Strong referential markers (Chinese + English)
        referential_markers = {
            "这个地址": EntityType.MEMORY_ADDRESS,
            "那个地址": EntityType.MEMORY_ADDRESS,
            "这个值": EntityType.NUMERIC_VALUE,
            "那个值": EntityType.NUMERIC_VALUE,
            "这个数值": EntityType.NUMERIC_VALUE,
            "那个数值": EntityType.NUMERIC_VALUE,
            "这个模块": EntityType.MODULE_NAME,
            "那个模块": EntityType.MODULE_NAME,
            "this address": EntityType.MEMORY_ADDRESS,
            "that address": EntityType.MEMORY_ADDRESS,
            "this value": EntityType.NUMERIC_VALUE,
            "that value": EntityType.NUMERIC_VALUE,
            "this module": EntityType.MODULE_NAME,
            "that module": EntityType.MODULE_NAME,
            "the previous": None,  # generic: resolve by last intent category
            "刚才的": None,
            "之前的": None,
        }

        last_intent = parse_context.get_last_intent()
        if not last_intent:
            return text, []

        for marker, expected_type in referential_markers.items():
            if marker not in resolved:
                continue
            # Find matching entity from last turn
            candidate = None
            if expected_type:
                for e in reversed(last_intent.entities):
                    if e.type == expected_type and e.confidence >= 0.8:
                        candidate = e
                        break
            else:
                # Generic: pick highest-confidence entity from last turn
                for e in sorted(last_intent.entities, key=lambda x: x.confidence, reverse=True):
                    if e.confidence >= 0.8:
                        candidate = e
                        break

            if candidate:
                # Replace marker with actual value in text
                resolved = resolved.replace(marker, str(candidate.value))
                inherited.append(Entity(
                    type=candidate.type,
                    value=candidate.value,
                    raw_text=marker,
                    confidence=candidate.confidence * 0.9,  # Slightly lower due to inheritance
                    start_pos=resolved.find(str(candidate.value)),
                    end_pos=resolved.find(str(candidate.value)) + len(str(candidate.value)),
                ))

        return resolved, inherited

    # ── Stage 0: Preprocessor ─────────────────────────────────────────────────

    def _preprocess(self, text: str, intent_context: IntentContext) -> str:
        """
        Normalize input + stability-aware vocabulary tuning.

        v2.2 fix: direction of synonym expansion was inverted.
        - High stability (>=0.7): user varies vocabulary for same concept →
          rules already cover multi-vocabulary synonyms; no text mutation needed.
          _classify will boost confidence when ParserConfig.enable_synonym_expansion.
        - Low stability (<0.5): user is vague/uncertain → CONTRACT to core keywords
        - Neutral: no vocabulary tuning
        """
        text = text.strip()
        # Collapse multiple whitespace
        text = re.sub(r"\s+", " ", text)
        # Normalize Chinese punctuation to ASCII equivalents
        text = text.replace("，", ",").replace("。", ".").replace("？", "?")
        text = text.replace("！", "!").replace("；", ";").replace("：", ":")

        stability = intent_context.cognitive_profile.stability

        if stability < 0.5:
            # Low stability: contract to core keywords, drop vague words
            text = self._contract_vocabulary(text)
        return text

    @staticmethod
    def _expand_synonyms(text: str) -> str:
        r"""
        Generate a synonym-expanded variant of text for rule matching.
        
        Used in _classify as a FALLBACK when original text yields no match.
        Does NOT mutate the original text (avoids breaking regex \s+ constraints).
        """
        # Work on a copy
        expanded = text
        expansions = {
            "read": "read dump view inspect",
            "dump": "dump read view",
            "scan": "scan search find locate",
            "search": "search scan find",
            "write": "write modify set change",
            "modify": "modify write change",
            "disassemble": "disassemble decompile view code",
        }
        for term, synonyms in expansions.items():
            pattern = r'\b' + re.escape(term) + r'\b'
            expanded = re.sub(pattern, synonyms, expanded, flags=re.IGNORECASE)
        return expanded

    @staticmethod
    def _contract_vocabulary(text: str) -> str:
        """
        Contract vague / filler words when user stability is low.
        Removes vague placeholders that cause false entity matches.
        """
        vague_patterns = [
            # Chinese: no word boundaries, match exact sequences
            r"东西",
            r"那个",
            r"这个",
            r"搞一下",
            r"弄一下",
            r"整一下",
            # English: use word boundaries to avoid partial matches
            r"\bsomething\b",
            r"\bthing\b",
            r"\bstuff\b",
            r"\bwhatever\b",
            r"\bsomehow\b",
        ]
        for pat in vague_patterns:
            text = re.sub(pat, "", text, flags=re.IGNORECASE)
        # Collapse leftover multiple spaces
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ── Stage 1: Entity Extractor ───────────────────────────────────────────────

    def _extract_entities(self, text: str, config: ParserConfig,
                          intent_context: IntentContext) -> List[Entity]:
        """Rule-based entity extraction."""
        entities: List[Entity] = []
        # TOOL mode: aggressively extract addresses/values
        # ADVISOR mode: additionally extract conditions / module names
        # COMPANION mode: minimal extraction (user is exploratory)
        is_tool = intent_context.expectation == UserExpectation.TOOL
        is_advisor = intent_context.expectation == UserExpectation.ADVISOR

        # Memory addresses (hex)
        for m in re.finditer(r"0x[0-9A-Fa-f]+", text):
            entities.append(Entity(
                type=EntityType.MEMORY_ADDRESS,
                value=m.group(0),
                raw_text=m.group(0),
                confidence=1.0,
                start_pos=m.start(),
                end_pos=m.end(),
            ))

        # Numeric values (decimal / float)
        for m in re.finditer(r"(?<![0-9A-Fa-fx])\b\d+(?:\.\d+)?\b", text):
            entities.append(Entity(
                type=EntityType.NUMERIC_VALUE,
                value=m.group(0),
                raw_text=m.group(0),
                confidence=0.9,
                start_pos=m.start(),
                end_pos=m.end(),
            ))

        # Process/module names (e.g., Game.exe, kernel32.dll)
        for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*\.(?:exe|dll|sys|so|dylib))\b", text, re.IGNORECASE):
            entities.append(Entity(
                type=EntityType.MODULE_NAME,
                value=m.group(1),
                raw_text=m.group(1),
                confidence=0.9,
                start_pos=m.start(),
                end_pos=m.end(),
            ))

        # Byte patterns (AOB scan: "48 89 5C 24 ??")
        for m in re.finditer(r"(?:[0-9A-Fa-f]{2}\s+){2,}[0-9A-Fa-f]{2}(?:\s+\?\?)*", text):
            entities.append(Entity(
                type=EntityType.BYTE_PATTERN,
                value=m.group(0),
                raw_text=m.group(0),
                confidence=0.95,
                start_pos=m.start(),
                end_pos=m.end(),
            ))

        # In ADVISOR mode, extract function/condition hints
        if is_advisor:
            for m in re.finditer(r"\b(sub_[0-9A-Fa-f]+|func_[0-9A-Fa-f]+|Create\w+|Read\w+|Write\w+)\b", text):
                entities.append(Entity(
                    type=EntityType.FUNCTION_NAME,
                    value=m.group(0),
                    raw_text=m.group(0),
                    confidence=0.7,
                    start_pos=m.start(),
                    end_pos=m.end(),
                ))

        # Cap entity count
        if len(entities) > config.max_entities:
            entities = sorted(entities, key=lambda e: e.confidence, reverse=True)[:config.max_entities]

        return entities

    # ── Stage 2: Intent Classifier (P2-1: conflict detection extracted) ───────────

    def _detect_rule_conflicts(self, candidates: List[Tuple[IntentCategory, float, IntentRule]],
                                 intent: Intent) -> List[Ambiguity]:
        """P2-1: Unified conflict detection — extracted from _classify for reuse."""
        ambiguities: List[Ambiguity] = []
        if len(candidates) <= 1:
            return ambiguities

        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                cat_i, conf_i, rule_i = candidates[i]
                cat_j, conf_j, rule_j = candidates[j]
                same_domain = (
                    rule_i.domain is not None
                    and rule_j.domain is not None
                    and rule_i.domain == rule_j.domain
                )
                explicit_conflict = (
                    rule_i.name and rule_j.name
                    and (
                        rule_i.name in rule_j.conflicts_with
                        or rule_j.name in rule_i.conflicts_with
                    )
                )
                if same_domain or explicit_conflict:
                    all_cats = list(dict.fromkeys([c[0].value for c in candidates]))
                    ambiguities.append(Ambiguity(
                        type=AmbiguityType.MULTIPLE_INTENTS,
                        description=f"检测到规则冲突：{', '.join(all_cats)}",
                        suggestions=all_cats,
                        auto_resolvable=False,
                    ))
                    return ambiguities  # Return one conflict ambiguity
        return ambiguities

    def _classify_raw(self, text: str, entities: List[Entity],
                      intent_context: IntentContext, config: ParserConfig) -> List[Tuple[IntentCategory, float, IntentRule]]:
        """Core rule-matching engine, extracted for reuse with synonym-expanded text."""
        candidates: List[Tuple[IntentCategory, float, IntentRule]] = []
        text_lower = text.lower()

        with _RULES_LOCK:
            rules = list(_RULES)

        for rule in rules:
            # Pattern matching score
            pattern_score = 0.0
            for p in rule.patterns:
                if p.fullmatch(text):
                    pattern_score = 1.0
                    break
                elif p.search(text):
                    pattern_score = max(pattern_score, 0.8)

            # Entity coverage score
            req_matched = sum(
                1 for e in rule.required_entities
                if any(en.type == e for en in entities)
            )
            req_score = req_matched / max(1, len(rule.required_entities)) * 0.4

            opt_matched = sum(
                1 for e in rule.optional_entities
                if any(en.type == e for en in entities)
            )
            opt_score = opt_matched / max(1, len(rule.optional_entities)) * 0.2

            entity_score = req_score + opt_score

            # Context score (tracking_depth regulation)
            context_score = 0.0
            if intent_context.cognitive_profile.tracking_depth > 0.6:
                # If previous intent was similar, boost
                pass  # ParseContext not directly available here; simplified

            confidence = pattern_score * 0.6 + entity_score * 0.3 + context_score * 0.1

            if confidence >= config.min_confidence_threshold:
                candidates.append((rule.category, confidence, rule))

        # Sort by confidence descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

    def _classify(self, text: str, entities: List[Entity],
                  intent_context: IntentContext, config: ParserConfig) -> Tuple[Intent, List[Tuple[IntentCategory, float, IntentRule]]]:
        """Classify using registered rules + PCR expectation regulation.
        Returns (Intent, candidates) so that conflict detection can be deferred to Stage 4."""
        candidates = self._classify_raw(text, entities, intent_context, config)

        # v2.2: Synonym expansion fallback
        if not candidates and config.enable_synonym_expansion:
            expanded_text = self._expand_synonyms(text)
            candidates = self._classify_raw(expanded_text, entities, intent_context, config)

        if candidates:
            best_category, best_conf, _ = candidates[0]
        else:
            best_category = IntentCategory.UNKNOWN
            best_conf = 0.0

        # Expectation regulation override
        if intent_context.expectation == UserExpectation.TOOL:
            if best_category not in (IntentCategory.SCAN_MEMORY, IntentCategory.READ_MEMORY,
                                      IntentCategory.WRITE_MEMORY, IntentCategory.DISASSEMBLE,
                                      IntentCategory.FIND_PATTERN, IntentCategory.SET_BREAKPOINT):
                for cat, conf, _ in candidates:
                    if cat in (IntentCategory.SCAN_MEMORY, IntentCategory.READ_MEMORY,
                               IntentCategory.WRITE_MEMORY, IntentCategory.DISASSEMBLE):
                        best_category = cat
                        best_conf = max(conf, 0.6)
                        break
        elif intent_context.expectation == UserExpectation.COMPANION:
            best_conf = max(best_conf, 0.3)

        return Intent(
            category=best_category,
            raw_input=text,
            normalized_input=text,
            entities=entities,
            confidence=best_conf,
        ), candidates

    # ── Stage 3: Multi-Intent Splitter ──────────────────────────────────────────

    def _split_multi_intent(self, intent: Intent, config: ParserConfig,
                            intent_context: IntentContext) -> List[Intent]:
        """Split compound intent if conjunction markers detected."""
        if not config.split_on_conjunctions:
            return []

        text = intent.normalized_input
        markers = self._step_markers.findall(text)
        if not markers:
            return []

        # Limit split count by complexity
        max_splits = config.max_sub_intents
        if len(markers) >= max_splits:
            return []

        # Simple split by markers (heuristic)
        segments = re.split(r"(?:and\s+then|then|接着|然后|再|并且|同时)", text, flags=re.IGNORECASE)
        segments = [s.strip() for s in segments if s.strip()]
        if len(segments) <= 1:
            return []

        sub_intents: List[Intent] = []
        for seg in segments:
            # P0-2: Inherit all entities from the parent intent (same context),
            # but mark those not directly present in the segment as inherited.
            sub_entities = []
            for e in intent.entities:
                # Check if entity appears directly in this segment (by raw_text or value)
                direct_match = seg.find(e.raw_text) != -1 or str(e.value) in seg
                if direct_match:
                    sub_entities.append(e)
                else:
                    # Inherited entity — lower confidence slightly
                    sub_entities.append(Entity(
                        type=e.type,
                        value=e.value,
                        raw_text=e.raw_text,
                        confidence=e.confidence * 0.8,
                        start_pos=-1,
                        end_pos=-1,
                        metadata={"inherited_from_split": True},
                    ))
            sub = Intent(
                category=intent.category,
                raw_input=seg,
                normalized_input=seg,
                entities=sub_entities,
                confidence=intent.confidence * 0.9,
            )
            sub_intents.append(sub)

        return sub_intents[:max_splits]

    # ── Stage 4: Ambiguity Detector ─────────────────────────────────────────────

    def _detect_ambiguities(self, intent: Intent, entities: List[Entity],
                            intent_context: IntentContext,
                            candidates: List[Tuple[IntentCategory, float, IntentRule]] = None) -> List[Ambiguity]:
        """Detect ambiguities regulated by noise + expectation. P2-1 unified conflict detection."""
        ambiguities: List[Ambiguity] = list(intent.ambiguities)
        
        # P2-1: Unified conflict detection (from _classify)
        if candidates and len(candidates) > 1:
            conflict_ambs = self._detect_rule_conflicts(candidates, intent)
            ambiguities.extend(conflict_ambs)
        
        noise = intent_context.noise_level
        exp = intent_context.expectation

        # Missing required entities (for high-confidence categories)
        if intent.category in (IntentCategory.SCAN_MEMORY, IntentCategory.WRITE_MEMORY,
                               IntentCategory.READ_MEMORY, IntentCategory.DISASSEMBLE):
            if not any(e.type == EntityType.MEMORY_ADDRESS for e in entities):
                ambiguities.append(Ambiguity(
                    type=AmbiguityType.MISSING_ENTITY,
                    description="缺少地址参数，无法定位内存区域",
                    affected_entities=[EntityType.MEMORY_ADDRESS],
                    suggestions=["请提供十六进制地址，如 0x00401000"],
                    auto_resolvable=noise < 0.5,  # Low noise = more likely auto-resolvable
                ))

        # Vague scope when high noise + TOOL
        if exp == UserExpectation.TOOL and noise > 0.7:
            ambiguities.append(Ambiguity(
                type=AmbiguityType.VAGUE_SCOPE,
                description="输入噪声较高，TOOL 模式需要明确操作对象",
                affected_entities=[],
                suggestions=["请指定具体地址或数值"],
                auto_resolvable=False,
            ))

        # Unknown category with high noise
        if intent.category == IntentCategory.UNKNOWN and noise > 0.5:
            ambiguities.append(Ambiguity(
                type=AmbiguityType.UNSUPPORTED_OPERATION,
                description="无法识别意图，需要澄清",
                affected_entities=[],
                suggestions=["请描述你想扫描内存、反汇编代码，还是分析程序"],
                auto_resolvable=False,
            ))

        # P2-1: Ambiguous entity detection (low confidence + multiple candidates)
        for e in entities:
            if e.confidence < 0.6 and len([en for en in entities if en.type == e.type]) > 1:
                ambiguities.append(Ambiguity(
                    type=AmbiguityType.AMBIGUOUS_ENTITY,
                    description=f"实体 {e.type.value} 存在多个候选，置信度较低",
                    affected_entities=[e.type],
                    suggestions=["请明确指定具体值"],
                    auto_resolvable=False,
                ))
                break  # Only one ambiguity per type

        return ambiguities

    # ── Stage 5: Ambiguity Resolver ─────────────────────────────────────────────

    def _resolve_ambiguities(self, intent: Intent, config: ParserConfig) -> Intent:
        """Auto-resolve ambiguities where confidence allows."""
        resolved: List[Ambiguity] = []
        for amb in intent.ambiguities:
            if amb.auto_resolvable and config.auto_resolve_threshold > 0.5:
                # Auto-resolve: fill with default if possible
                continue
            resolved.append(amb)
        intent.ambiguities = resolved
        return intent

    # ── Stage 6: Context Merger ─────────────────────────────────────────────────

    def _merge_context(self, intent: Intent, parse_context: ParseContext,
                       config: ParserConfig) -> Intent:
        """Inherit high-confidence entities from previous turns."""
        if not config.inherit_entities_from_context:
            return intent

        # Inherit process context
        if parse_context.pid and not any(e.type == EntityType.PID for e in intent.entities):
            intent.entities.append(Entity(
                type=EntityType.PID,
                value=parse_context.pid,
                raw_text=str(parse_context.pid),
                confidence=1.0,
            ))

        if parse_context.process_name and not any(e.type == EntityType.PROCESS_NAME for e in intent.entities):
            intent.entities.append(Entity(
                type=EntityType.PROCESS_NAME,
                value=parse_context.process_name,
                raw_text=parse_context.process_name,
                confidence=1.0,
            ))

        # Inherit from history if topic inheritance is enabled
        if config.enable_topic_inheritance and parse_context.history:
            last = parse_context.get_last_intent()
            if last and last.category == intent.category:
                for e in last.entities:
                    if e.confidence >= 0.8 and not any(ee.type == e.type for ee in intent.entities):
                        if e.type not in (EntityType.NUMERIC_VALUE, EntityType.MEMORY_ADDRESS):
                            intent.entities.append(Entity(
                                type=e.type,
                                value=e.value,
                                raw_text=e.raw_text,
                                confidence=e.confidence * 0.9,
                            ))

        return intent

    # ── Stage 7: TaskGraph Builder ──────────────────────────────────────────────

    def _build_task_graph(self, intent: Intent,
                          intent_context: IntentContext) -> TaskGraph:
        """Build TaskGraph regulated by expectation type."""
        graph = TaskGraph(intent_id=intent.id)
        exp = intent_context.expectation

        if exp == UserExpectation.TOOL:
            # Minimal graph: single node
            node = self._map_atomic_intent(intent)
            graph.add_node(node)
            return graph

        elif exp == UserExpectation.COMPANION:
            # Add conversational node at the end
            nodes = self._decompose_intent(intent)
            for n in nodes:
                graph.add_node(n)
            for i in range(len(nodes) - 1):
                graph.add_dependency(nodes[i].id, nodes[i + 1].id, DependencyType.SEQUENTIAL)
            # Append ask_user node
            ask_node = TaskNode(
                name="保持对话",
                goal="询问用户下一步需求",
                strategy="proactive_ask",
                tool_name="ask_user",
                tool_params={"question": "还有什么想分析的吗？"},
                tags={"companion", "non_destructive"},
            )
            graph.add_node(ask_node)
            if nodes:
                graph.add_dependency(nodes[-1].id, ask_node.id, DependencyType.SEQUENTIAL)
            return graph

        elif exp == UserExpectation.ADVISOR:
            # Full decomposition + explanation nodes + FALLBACK edges (P0-3)
            nodes = self._decompose_intent(intent)
            fallback_nodes = []
            for i, n in enumerate(nodes):
                graph.add_node(n)
                # Add explanation node for each action node
                explain = TaskNode(
                    name=f"解释 {n.name}",
                    goal="向用户解释分析结果",
                    strategy="explain_result",
                    tool_name=None,
                    tags={"advisor", "explanatory"},
                )
                graph.add_node(explain)
                graph.add_dependency(n.id, explain.id, DependencyType.SEQUENTIAL)
                if i > 0:
                    graph.add_dependency(nodes[i - 1].id, n.id, DependencyType.SEQUENTIAL)

                # FALLBACK node: if analysis fails, switch to ask_user
                fallback = TaskNode(
                    name=f"回退 {n.name}",
                    goal="分析失败，回退到询问用户",
                    strategy="fallback_ask",
                    tool_name="ask_user",
                    tool_params={"question": f"无法完成 {n.name}，请提供更多细节"},
                    tags={"advisor", "fallback", "non_destructive"},
                )
                graph.add_node(fallback)
                graph.add_dependency(n.id, fallback.id, DependencyType.FALLBACK)
                fallback_nodes.append(fallback)

            return graph

        # Default: full decomposition
        nodes = self._decompose_intent(intent)
        for n in nodes:
            graph.add_node(n)
        for i in range(len(nodes) - 1):
            graph.add_dependency(nodes[i].id, nodes[i + 1].id, DependencyType.SEQUENTIAL)
        return graph

    # ── Helpers ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _map_atomic_intent(intent: Intent) -> TaskNode:
        """Map a single intent to one TaskNode with fallback chain."""
        category_tool_map = {
            IntentCategory.SCAN_MEMORY: ("first_scan", "exact_scan", ["next_scan", "ask_user"]),
            IntentCategory.READ_MEMORY: ("read_memory", "direct_read", ["ask_user"]),
            IntentCategory.WRITE_MEMORY: ("write_memory", "direct_write", ["ask_user"]),
            IntentCategory.DISASSEMBLE: ("disassemble", "linear_disasm", ["ask_user"]),
            IntentCategory.FIND_PATTERN: ("find_pattern", "aob_scan", ["ask_user"]),
            IntentCategory.SET_BREAKPOINT: ("set_breakpoint", "memory_watch", ["ask_user"]),
            IntentCategory.ANALYZE_PROCESS: ("refresh_analysis", "full_process_analysis", ["ask_user"]),
            IntentCategory.ASK_USER: ("ask_user", "proactive_ask", []),
            IntentCategory.FINISH: ("finish", "session_end", ["ask_user"]),
        }
        tool_name, strategy, fallbacks = category_tool_map.get(
            intent.category, ("ask_user", "unknown", ["ask_user"])
        )
        return TaskNode(
            name=intent.category.value,
            goal=f"Execute {intent.category.value}",
            strategy=strategy,
            tool_name=tool_name,
            tool_params={},
            tags={intent.category.value},
            fallback_nodes=fallbacks,
        )

    def _decompose_intent(self, intent: Intent) -> List[TaskNode]:
        """Decompose a compound intent into multiple nodes."""
        if intent.sub_intents:
            return [self._map_atomic_intent(si) for si in intent.sub_intents]
        return [self._map_atomic_intent(intent)]

    @staticmethod
    def _build_clarification(intent: Intent) -> Optional[str]:
        """Build a human-readable clarification message."""
        if not intent.ambiguities:
            return None
        parts = ["需要更多信息："]
        for amb in intent.ambiguities:
            parts.append(f"- {amb.description}")
        return "\n".join(parts)

    @staticmethod
    def _build_suggestions(intent: Intent, intent_context: IntentContext) -> List[str]:
        """Build quick-reply suggestions."""
        suggestions: List[str] = []
        for amb in intent.ambiguities:
            suggestions.extend(amb.suggestions)
        # Add expectation-based suggestions
        if intent_context.expectation == UserExpectation.UNKNOWN:
            suggestions.extend(["扫描内存", "反汇编代码", "分析程序保护"])
        return suggestions[:5]
