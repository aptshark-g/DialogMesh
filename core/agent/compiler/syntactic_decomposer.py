# core/agent/compiler/syntactic_decomposer.py
"""Stage 2: SyntacticDecomposer — 完整版语法分解器。

将自然语言按边界标记切分为子句（EDU 候选），并提取每个子句的主谓宾骨架 + 修饰属性。

完整版改进：
- 使用 SemanticParser 做开放域实体识别（NER + 词性标注 + BGE 语义过滤）
- 使用 SemanticParser 做关系提取（主谓宾）
- 保留规则作为兜底和补充（否定/疑问/祈使检测）
- 支持 Hybrid Path：复杂句标记 parse_failed=True

设计原则:
- 主语/宾语是认知核心 —— 决定话题归属
- 谓语是意图核心 —— 决定路由方向
- 修饰语（否定、形容词、副词）是属性标签 —— 不能丢弃
- 语义解析器优先，规则兜底
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

logger = logging.getLogger(__name__)

# ── 数据类 ──────────────────────────────────────────────────────
@dataclass
class ParsedClause:
    """语法分解后的子句结构。"""
    raw_text: str                    # 原始子句文本

    # 核心成分
    subject: Optional[str] = None      # 主语（可能为空，待头文件引入）
    subject_attrs: List[str] = field(default_factory=list)   # 主语修饰语
    predicate: Optional[str] = None  # 谓语/动词
    predicate_attrs: List[str] = field(default_factory=list)  # 谓语修饰（副词）
    object: Optional[str] = None     # 宾语
    object_attrs: List[str] = field(default_factory=list)    # 宾语修饰语

    # 语义属性
    negation: bool = False           # 是否含否定词
    uncertainty: bool = False      # 是否含不确定（可能/也许/大概）
    imperative: bool = False         # 是否祈使句（命令语气）
    question: bool = False           # 是否疑问句

    # 提取的实体（原始提取，未经过头文件补全）
    raw_entities: List[str] = field(default_factory=list)

    # 解析状态
    parse_failed: bool = False
    parse_failed_reason: str = ""      # "complex_input" | "multiple_subjects" | ...

    def to_entity_signature(self) -> str:
        """生成包含属性的实体签名，用于下游索引和匹配。"""
        parts = []
        if self.negation:
            parts.append("NOT")
        if self.uncertainty:
            parts.append("MAYBE")
        parts.extend(self.subject_attrs)
        if self.subject:
            parts.append(self.subject)
        parts.append(self.predicate or "")
        parts.extend(self.object_attrs)
        if self.object:
            parts.append(self.object)
        return " ".join(filter(None, parts))

    def to_compact(self) -> str:
        """压缩表示，用于调试日志。"""
        attrs = f"[{'NOT ' if self.negation else ''}{','.join(self.subject_attrs)}]" if self.subject_attrs else ""
        return f"({attrs}{self.subject}) {self.predicate} ({self.object})"


# ── 主类 ──────────────────────────────────────────────────────────
class SyntacticDecomposer:
    """完整版语法分解器。使用 SemanticParser 做开放域实体识别，规则做补充。"""

    # 歧义连词（多主语/嵌套从句信号）
    AMBIGUOUS_CONJUNCTIONS = {
        "和", "与", "或", "但", "如果", "虽然", "因为", "但是", "不过", "然而",
        "and", "or", "but", "if", "although", "because", "however", "though",
    }

    # 否定词词典
    NEGATION_MARKERS = {
        "不", "没", "无", "非", "别", "不要", "不会", "不能", "不要", "不",
        "not", "no", "don't", "won't", "can't", "never", "isn't", "aren't",
        "doesn't", "didn't", "wouldn't", "shouldn't",
    }

    # 不确定词词典
    UNCERTAINTY_MARKERS = {
        "可能", "也许", "大概", "应该", "或许", "估计", "也许",
        "maybe", "perhaps", "probably", "might", "could", "likely", "possibly",
    }

    # 祈使词（命令语气）
    IMPERATIVE_MARKERS = {
        "请", "给我", "帮我", "给我",
        "scan", "patch", "hook", "read", "write", "find", "analyze", "check",
        "分析", "扫描", "修改", "读取", "写入", "查找", "检查", "确认", "执行", "调用",
        "看看", "查一下", "帮我看看", "帮我查一下", "帮我写", "帮我做",
    }

    # 疑问词（疑问句检测）
    QUESTION_MARKERS = {"吗", "么", "呢", "吧", "什么", "怎么", "为什么", "多少", "哪里", "谁", "哪个",
                        "what", "how", "why", "where", "when", "which", "who", "whom"}

    # 形容词/修饰词（常见属性）
    ADJECTIVE_MARKERS = {
        "安全的", "不安全的", "稳定的", "异常的", "正常的", "轻量的", "重的",
        "大端", "小端", "只读", "可写", "静态", "动态", "同步", "异步",
        "safe", "unsafe", "stable", "abnormal", "normal", "lightweight", "heavy",
        "big-endian", "little-endian", "readonly", "writable", "static", "dynamic",
        "synchronous", "asynchronous",
    }

    # 谓语/动词词典（规则兜底）
    PREDICATE_DICT = {
        "技术": ["scan", "patch", "hook", "read", "write", "find", "analyze", "check",
                "分析", "扫描", "修改", "读取", "写入", "查找", "检查", "确认", "执行", "调用"],
        "通用": ["写", "做", "看", "查", "推荐", "讨论", "问", "说", "想", "知道",
                "了解", "学习", "研究", "设计", "开发", "测试", "部署", "优化", "修复",
                "喜欢", "是", "有", "觉得", "认为", "需要", "想要", "使用", "用",
                "write", "make", "do", "see", "check", "recommend", "discuss", "ask",
                "say", "think", "know", "learn", "study", "design", "develop", "test",
                "deploy", "optimize", "fix", "like", "is", "have", "feel", "need", "want", "use"],
    }

    def __init__(self, enable_hybrid_path: bool = True, use_semantic_parser: bool = True):
        # 从配置读取阈值
        config = get_discourse_config() if get_discourse_config else None
        dec_cfg = config.decomposer if config else None

        self.COMPLEX_CLAUSE_LENGTH = dec_cfg.complex_clause_length if dec_cfg else 30
        self.MAX_CLAUSES_PER_INPUT = dec_cfg.max_clauses_per_input if dec_cfg else 5
        self.enable_hybrid_path = enable_hybrid_path if (dec_cfg is None) else dec_cfg.hybrid_path_enabled
        self._use_semantic_parser = use_semantic_parser if (dec_cfg is None) else dec_cfg.semantic_parser_enabled

        # 语义解析器（完整版核心）
        self._parser = None
        if self._use_semantic_parser:
            try:
                from core.agent.compiler.semantic_parser import SemanticParser
                self._parser = SemanticParser(use_ner=True, use_bge_filter=True)
            except Exception as e:
                logger.warning(f"SemanticParser init failed in SyntacticDecomposer: {e}")
                self._parser = None

        # 编码器（用于语义相似度，可选）
        self._encoder = None
        try:
            from core.agent.compiler.semantic_encoder import get_encoder
            self._encoder = get_encoder()
        except Exception as e:
            logger.warning(f"Encoder init failed in SyntacticDecomposer: {e}")
            self._encoder = None

        logger.debug(
            f"SyntacticDecomposer initialized (complex_len={self.COMPLEX_CLAUSE_LENGTH}, "
            f"max_clauses={self.MAX_CLAUSES_PER_INPUT}, hybrid={self.enable_hybrid_path})"
        )

    # ── 公共接口 ──────────────────────────────────────────────────

    def decompose(self, text: str) -> List[ParsedClause]:
        """分解输入文本为多个 ParsedClause。

        步骤:
        1. 按标点切分子句
        2. 检测歧义：如果输入过于复杂，标记 parse_failed
        3. 对每个子句提取成分（语义解析器优先）
        4. 返回列表（每个子句一个 ParsedClause）
        """
        clauses = self._split_clauses(text)

        # 歧义检测：输入过于复杂 → 标记但不抛异常
        if self.enable_hybrid_path and self._is_complex_input(clauses):
            return [ParsedClause(
                raw_text=text,
                parse_failed=True,
                parse_failed_reason="complex_input",
            )]

        parsed = []
        for clause_text in clauses:
            if clause_text.strip():
                parsed_clause = self._parse_clause(clause_text)
                parsed.append(parsed_clause)

        return parsed

    # ── 子句切分 ────────────────────────────────────────────────────

    def _split_clauses(self, text: str) -> List[str]:
        """按中文/英文标点切分句子。

        支持：。！？；, . ! ? ;
        保留：、（顿号，作为列表内部分隔，不切分）
        """
        segments = re.split(r'[。！？；\.,\!\?\;]+', text)
        return [s.strip() for s in segments if s.strip()]

    # ── 复杂度检测 ──────────────────────────────────────────────────

    def _is_complex_input(self, clauses: List[str]) -> bool:
        """检测输入是否过于复杂（正则无法可靠解析）。

        触发条件:
        1. 子句数量过多
        2. 存在歧义连词（嵌套从句信号）
        3. 单个子句过长且不含明确实体
        """
        # 1. 子句数量过多
        if len(clauses) > self.MAX_CLAUSES_PER_INPUT:
            return True

        # 2. 存在歧义连词（2+ 个连词视为复杂）
        full_text = "".join(clauses)
        conj_count = sum(1 for c in self.AMBIGUOUS_CONJUNCTIONS if c in full_text)
        if conj_count >= 2:
            return True

        # 3. 单个子句过长且不含明确实体
        for c in clauses:
            if len(c) > self.COMPLEX_CLAUSE_LENGTH:
                has_entity = bool(re.findall(r'0x[0-9a-fA-F]+|\b\d+\b|[A-Z][a-z]+[A-Z]', c))
                if not has_entity:
                    return True

        return False

    # ── 单个子句解析 ─────────────────────────────────────────────

    def _parse_clause(self, text: str) -> ParsedClause:
        """解析单个子句。完整版：SemanticParser 优先，规则兜底。"""
        clause = ParsedClause(raw_text=text)

        # 1. 检测语义属性（否定/不确定/祈使/疑问）
        clause.negation = any(m in text for m in self.NEGATION_MARKERS)
        clause.uncertainty = any(m in text for m in self.UNCERTAINTY_MARKERS)
        clause.imperative = any(m in text for m in self.IMPERATIVE_MARKERS)
        clause.question = any(m in text for m in self.QUESTION_MARKERS) or text.endswith("?") or text.endswith("？")

        # 2. 实体识别（SemanticParser 开放域识别）
        if self._parser:
            try:
                parsed_entities = self._parser.extract_entities(text)
                clause.raw_entities = [e.text for e in parsed_entities]
            except Exception:
                clause.raw_entities = self._extract_entities_fallback(text)
        else:
            clause.raw_entities = self._extract_entities_fallback(text)

        # 3. 子句内部歧义检测
        if self._has_multiple_subjects(text):
            clause.parse_failed = True
            clause.parse_failed_reason = "multiple_subjects"
            return clause

        # 4. 主谓宾提取（SemanticParser 优先）
        if self._parser:
            try:
                relation = self._parser.extract_relation(text)
                if relation:
                    clause.subject = relation.subject
                    clause.predicate = relation.predicate
                    clause.object = relation.object
                    clause.subject_entities = relation.subject_entities
                    clause.object_entities = relation.object_entities
            except Exception as e:
                logger.warning(f"SemanticParser relation extraction failed: {e}")

        # 5. 如果 SemanticParser 没提取到谓语，用规则兜底
        if not clause.predicate:
            clause.predicate = self._extract_predicate_fallback(text)

        # 6. 如果 SemanticParser 没提取到主语/宾语，用规则兜底
        if not clause.subject:
            clause.subject = self._extract_subject_fallback(text)
        if not clause.object:
            clause.object = self._extract_object_fallback(text, clause.predicate)

        # 7. 提取修饰语
        clause.subject_attrs = self._extract_modifiers(text, clause.subject)
        clause.object_attrs = self._extract_modifiers(text, clause.object)

        return clause

    # ── 实体识别（规则兜底）──────────────────────────────────────

    def _extract_entities_fallback(self, text: str) -> List[str]:
        """规则提取实体（当 SemanticParser 不可用时兜底）。"""
        entities = []
        # 1. 规则提取（地址、数值）
        entities.extend(re.findall(r"0x[0-9a-fA-F]+", text))
        entities.extend(re.findall(r"\b\d+\b", text))

        # 2. 硬编码技术实体（兜底补充）
        tool_names = [
            "Python", "Java", "C++", "TensorFlow", "PyTorch", "BERT", "GPT",
            "OpenCV", "Redis", "MongoDB", "Docker", "Kubernetes", "React",
            "Vue", "Angular", "Node.js", "Flask", "Django", "FastAPI",
            "MySQL", "PostgreSQL", "Elasticsearch", "Kafka", "Spark",
            "Hadoop", "Flink", "CUDA", "OpenCL", "Vulkan", "DirectX",
        ]
        text_lower = text.lower()
        for name in tool_names:
            if name.lower() in text_lower:
                entities.append(name)

        # 3. 去重
        seen = set()
        deduped = []
        for e in entities:
            key = e.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        return deduped

    # ── 主谓宾提取（规则兜底）────────────────────────────────────

    def _extract_subject_fallback(self, text: str) -> Optional[str]:
        """规则提取主语（兜底）。"""
        # 代词优先
        pronouns = ["这个", "那个", "它", "他", "她", "这", "那",
                    "this", "that", "it", "he", "she", "they"]
        for p in pronouns:
            if p in text:
                return p
        # 否则取第一个实体
        entities = self._extract_entities_fallback(text)
        return entities[0] if entities else None

    def _extract_predicate_fallback(self, text: str) -> Optional[str]:
        """规则提取谓语（兜底）。"""
        text_lower = text.lower()
        for category, verbs in self.PREDICATE_DICT.items():
            for verb in verbs:
                if verb.lower() in text_lower:
                    return verb
        return None

    def _extract_object_fallback(self, text: str, predicate: Optional[str]) -> Optional[str]:
        """规则提取宾语（兜底）。"""
        if not predicate:
            return None
        pred_pos = text.lower().find(predicate.lower())
        if pred_pos >= 0:
            after = text[pred_pos + len(predicate):]
            entities = self._extract_entities_fallback(after)
            return entities[0] if entities else after.strip()[:20]
        return None

    # ── 歧义检测 ─────────────────────────────────────────────────

    def _has_multiple_subjects(self, text: str) -> bool:
        """检测子句是否包含多个主语（歧义信号）。"""
        # 代词计数（多个代词 = 可能指代不同对象）
        pronouns = ["这个", "那个", "它", "他", "这", "那",
                    "this", "that", "it", "the", "they"]
        pronoun_count = sum(1 for p in pronouns if p in text)
        if pronoun_count >= 2:
            return True

        # 实体计数（3+ 个不同实体，可能多主语）
        if self._parser:
            try:
                entities = self._parser.extract_entities(text)
                if len(entities) >= 3:
                    return True
            except Exception as e:
                logger.warning(f"SemanticParser entity extraction for complexity check failed: {e}")
        else:
            entities = self._extract_entities_fallback(text)
            if len(entities) >= 3:
                return True

        return False

    # ── 修饰语提取 ───────────────────────────────────────────────

    def _extract_modifiers(self, text: str, target: Optional[str]) -> List[str]:
        """提取目标词前的修饰语（形容词/否定词）。"""
        if not target:
            return []
        pos = text.find(target)
        if pos < 0:
            return []
        before = text[:pos]
        modifiers = []
        # 形容词
        for adj in self.ADJECTIVE_MARKERS:
            if adj in before:
                modifiers.append(adj)
        # 否定词也作为修饰
        if any(m in before for m in self.NEGATION_MARKERS):
            modifiers.append("NEG")
        return modifiers
