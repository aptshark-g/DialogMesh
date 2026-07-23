"""ObservationExtractor: DocumentNode → List[DocumentObservation].

提取策略（按 observation_type）：
- definition: 含 "是..."、"定义为..."、"指..."
- constraint: 含 "必须..."、"不能..."、"限制..."
- procedure: 含 "步骤..."、"流程..."、"首先...然后..."
- example:   含 "例如..."、"示例..."、"比如..."
- relation:  含 "依赖..."、"基于..."、"导致..."
- parameter: 含 "参数..."、"阈值..."、"默认值..."
"""
from __future__ import annotations
import hashlib
import logging
import re
from typing import Iterator, List

from .tree import DocumentNode, Relation
from .observation import DocumentObservation

logger = logging.getLogger(__name__)


class ObservationExtractor:
    """Extract structured observations from DocumentNode.

    NOT a simple chunker. It interprets document content into
    cognitive primitives: concepts, relations, constraints, procedures.
    """

    # (pattern, observation_type, confidence_boost)
    # Regex relaxed: most Chinese tech/prose sentences match without requiring colons
    _RULES: List[tuple] = [
        (r"(?:是|定义为|指|表示|即|指的是|是指|称为|叫做|称作)\s*[:：]?", "definition", 0.7),
        (r"(?:必须|不能|不得|限制|约束|要求|应该|应当|需要)\s*[:：]?", "constraint", 0.6),
        (r"(?:步骤|流程|首先|然后|接着|最后|Step|step|先|再|之后|接下来)\s*[:：\d]?", "procedure", 0.5),
        (r"(?:例如|示例|比如|e\.g\.|eg\.|Example|譬如|举例|比方说)\s*[:：]?", "example", 0.5),
        (r"(?:依赖|基于|导致|引起|造成|结果|result|depend|引用|关联|触发|影响)\s*[:：]?", "relation", 0.5),
        (r"(?:参数|阈值|默认值|配置|设置|parameter|threshold|default|属性|字段|配置项)\s*[:：=]?", "parameter", 0.5),
    ]

    def extract(self, node: DocumentNode, event_id: str) -> List[DocumentObservation]:
        """Return observations that can enter the cognitive chain."""
        observations: List[DocumentObservation] = []
        if not node.raw_text.strip():
            return observations

        # 对 heading 节点，提取标题本身作为潜在概念
        if node.node_type == "heading":
            concepts = self._extract_concepts(node.raw_text)
            obs = DocumentObservation(
                observation_id=self._make_obs_id(node.node_id, "heading"),
                source_path=node.source_path,
                node_id=node.node_id,
                event_id=event_id,
                observation_type="definition",
                raw_text=node.raw_text,
                concepts=concepts,
                confidence=0.5,
                heading_path=node.heading_path,
            )
            observations.append(obs)

        # 对段落/代码块/列表，按规则匹配；未匹配的作为通用内容提取
        if node.node_type in ("paragraph", "code", "list"):
            matched_type, confidence = self._match_type(node.raw_text)
            if matched_type:
                concepts = self._extract_concepts(node.raw_text)
                relations = self._extract_relations(node.raw_text) if matched_type == "relation" else []
                constraints = self._extract_constraints(node.raw_text) if matched_type == "constraint" else []

                obs = DocumentObservation(
                    observation_id=self._make_obs_id(node.node_id, matched_type),
                    source_path=node.source_path,
                    node_id=node.node_id,
                    event_id=event_id,
                    observation_type=matched_type,
                    raw_text=node.raw_text,
                    concepts=concepts,
                    relations=relations,
                    constraints=constraints,
                    confidence=confidence,
                    heading_path=node.heading_path,
                )
                observations.append(obs)
            else:
                # Fallback: extract unmatched paragraphs as generic "content" observations
                # so ALL document text enters the cognitive chain, not just rule-matched text
                concepts = self._extract_concepts(node.raw_text)
                obs = DocumentObservation(
                    observation_id=self._make_obs_id(node.node_id, "content"),
                    source_path=node.source_path,
                    node_id=node.node_id,
                    event_id=event_id,
                    observation_type="content",
                    raw_text=node.raw_text,
                    concepts=concepts,
                    confidence=0.3,
                    heading_path=node.heading_path,
                )
                observations.append(obs)

        # 递归处理子节点
        for child in node.children:
            observations.extend(self.extract(child, event_id))

        return observations

    def extract_flat(self, root: DocumentNode, event_id: str) -> List[DocumentObservation]:
        """Flatten-extract all observations from the entire tree."""
        return self.extract(root, event_id)

    # ---- internal ----

    def _match_type(self, text: str) -> tuple:
        """Return (observation_type, confidence) or ('', 0.0)."""
        best_type, best_conf = "", 0.0
        for pattern, obs_type, boost in self._RULES:
            if re.search(pattern, text):
                if boost > best_conf:
                    best_type = obs_type
                    best_conf = boost
        return best_type, best_conf

    @staticmethod
    def _extract_concepts(text: str) -> List[str]:
        """Extract concepts: CamelCase, backtick-quoted terms, markdown links, Chinese tech terms."""
        concepts: List[str] = []
        # CamelCase / PascalCase (e.g. CrossDomainContextIR, BudgetAllocator)
        for m in re.finditer(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text):
            concepts.append(m.group(0))
        # Backtick-quoted inline code (e.g. `ContextCompiler`, `to_prompt()`)
        for m in re.finditer(r'`([^`]+)`', text):
            concepts.append(m.group(1).strip())
        # Markdown links: [display](url) — capture display text
        for m in re.finditer(r'\[([^\]]+)\]\([^)]+\)', text):
            concepts.append(m.group(1).strip())
        # Bold/italic in markdown: **term** or *term*
        for m in re.finditer(r'\*\*([^*]+)\*\*', text):
            c = m.group(1).strip()
            if len(c) > 3:  # skip short bold text
                concepts.append(c)
        # Double-quoted phrases
        for m in re.finditer(r'"([^"]+)"', text):
            c = m.group(1).strip()
            if len(c) > 2:
                concepts.append(c)
        # Deduplicate while preserving order, cap at 10
        seen = set()
        result = []
        for c in concepts:
            c = c.strip()
            if c and len(c) >= 2 and c not in seen:
                seen.add(c)
                result.append(c)
        return result[:10]

    @staticmethod
    def _extract_relations(text: str) -> List[Relation]:
        """Extract typed dependency relations from text.

        Matches: depends_on, leads_to, calls, extends, implements,
        references, triggers, constrains, creates, updates — with
        Chinese and English patterns.
        """
        relations: List[Relation] = []
        patterns = [
            # (regex, relation_type) — ordered by specificity
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:依赖于|依赖|depends?\s*on|基于|based\s*on)\s*([A-Za-z\u4e00-\u9fff]+)', "depends_on"),
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:导致|leads?\s*to|causes?|引起)\s*([A-Za-z\u4e00-\u9fff]+)', "leads_to"),
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:调用|calls?|invokes?)\s*([A-Za-z\u4e00-\u9fff]+)', "calls"),
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:继承|扩展|extends?|inherits?\s*from)\s*([A-Za-z\u4e00-\u9fff]+)', "extends"),
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:实现|implements?)\s*([A-Za-z\u4e00-\u9fff]+)', "implements"),
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:引用|references?|refers?\s*to)\s*([A-Za-z\u4e00-\u9fff]+)', "references"),
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:触发|triggers?|activates?)\s*([A-Za-z\u4e00-\u9fff]+)', "triggers"),
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:约束|限制|constrains?|restricts?)\s*([A-Za-z\u4e00-\u9fff]+)', "constrains"),
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:创建|生成|creates?|generates?)\s*([A-Za-z\u4e00-\u9fff]+)', "creates"),
            (r'([A-Za-z\u4e00-\u9fff]+)\s*(?:更新|修改|updates?|modifies?)\s*([A-Za-z\u4e00-\u9fff]+)', "updates"),
        ]
        for pattern, rel_type in patterns:
            for m in re.finditer(pattern, text):
                relations.append(Relation(
                    source=m.group(1).strip(),
                    target=m.group(2).strip(),
                    relation_type=rel_type,
                    confidence=0.5,
                ))
        return relations

    @staticmethod
    def _extract_constraints(text: str) -> List[str]:
        """Extract constraint sentences."""
        constraints: List[str] = []
        for sent in re.split(r'[。；\n]', text):
            sent = sent.strip()
            if sent and re.search(r'(?:必须|不能|不得|限制|约束|要求)', sent):
                constraints.append(sent)
        return constraints

    @staticmethod
    def _make_obs_id(node_id: str, obs_type: str) -> str:
        key = f"{node_id}::{obs_type}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
