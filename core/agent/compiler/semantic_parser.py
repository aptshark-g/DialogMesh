# core/agent/compiler/semantic_parser.py
"""SemanticParser — 完整版语义解析器。

封装三大能力：
1. 开放域实体识别（NER + 词性标注 + BGE 语义过滤）
2. 轻量依存句法分析（主谓宾提取）
3. 指代链构建（用于代词消解）

设计原则：
- 所有模型单例共享（SemanticEncoder 已提供单例）
- 延迟加载，首次调用时初始化
- 结果缓存，避免重复解析
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

logger = logging.getLogger(__name__)

# ── NER 模型加载（可选，使用 ModelScope Pipeline）─────────────────
NER_AVAILABLE = False
_NER_LOAD_ATTEMPTED = False  # 标记是否已尝试过加载（避免重复超时）
_ner_pipeline = None

def _load_ner_pipeline():
    """延迟加载 NER Pipeline（DAMO 模型，使用 ModelScope 接口）。

    注意：首次加载失败后标记 _NER_LOAD_ATTEMPTED=True，后续调用直接跳过，
    避免重复超时导致的性能退化。
    """
    global NER_AVAILABLE, _NER_LOAD_ATTEMPTED, _ner_pipeline
    if NER_AVAILABLE or _NER_LOAD_ATTEMPTED:
        return
    _NER_LOAD_ATTEMPTED = True

    # 从配置读取模型 ID（默认 DAMO）
    config = get_discourse_config() if get_discourse_config else None
    model_id = config.model_download.ner_model_id if config else "damo/nlp_raner_named-entity-recognition_chinese-base-news"

    try:
        from modelscope.pipelines import pipeline
        from modelscope.utils.constant import Tasks
        _ner_pipeline = pipeline(
            Tasks.named_entity_recognition,
            model=model_id,
            model_revision="v1.0.0",
        )
        NER_AVAILABLE = True
        logger.info(f"NER pipeline loaded: {model_id}")
    except Exception as e:
        NER_AVAILABLE = False
        logger.warning(f"NER pipeline load failed ({model_id}): {e}")


# ── jieba 词性标注（可选）────────────────────────────────────
JIEBA_AVAILABLE = False

try:
    import jieba.posseg as pseg
    JIEBA_AVAILABLE = True
except ImportError:
    pseg = None  # type: ignore


# ── 数据类 ───────────────────────────────────────────────────
@dataclass
class ParsedEntity:
    """解析出的实体。"""
    text: str
    start: int
    end: int
    entity_type: str  # PER/LOC/ORG/TECH/NOUN/VERB/...
    confidence: float = 1.0


@dataclass
class ParsedRelation:
    """解析出的关系（主谓宾）。"""
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    subject_entities: List[str] = field(default_factory=list)
    object_entities: List[str] = field(default_factory=list)


@dataclass
class ParseResult:
    """单句解析结果。"""
    raw_text: str
    entities: List[ParsedEntity] = field(default_factory=list)
    relation: Optional[ParsedRelation] = None
    tokens: List[Tuple[str, str]] = field(default_factory=list)  # (word, pos)


@dataclass
class Mention:
    """指代提及（用于指代链）。"""
    text: str
    position: int  # 在文本中的位置
    entity_type: str
    is_pronoun: bool = False


@dataclass
class CoreferenceChain:
    """指代链：一个实体在不同位置的提及。"""
    entity_id: str
    mentions: List[Mention] = field(default_factory=list)
    representative: str = ""  # 代表词（通常是首次出现的完整实体）


# ── SemanticParser 主类 ──────────────────────────────────────
class SemanticParser:
    """完整版语义解析器。

    提供：
    - extract_entities(text): 开放域实体识别
    - extract_relation(text): 主谓宾提取
    - build_coreference_chains(texts): 跨句指代链构建
    """

    # 词性 → 实体类型映射
    POS_ENTITY_MAP = {
        "nr": "PER",    # 人名
        "ns": "LOC",    # 地名
        "nt": "ORG",    # 机构名
        "nw": "TECH",   # 作品名/技术名
        "n": "NOUN",    # 普通名词
        "nz": "NOUN",   # 其他专有名词
        "vn": "NOUN",   # 名动词
        "an": "NOUN",   # 名形词
        "j": "NOUN",    # 简称
    }

    # 动词词性
    VERB_POS = {"v", "vd", "vg", "vi", "vl", "vq"}

    # 代词词性
    PRONOUN_POS = {"r", "rr", "rz", "ry", "rg"}

    # 中文代词列表
    PRONOUNS = {
        "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们",
        "这", "那", "这个", "那个", "这里", "那里", "这些", "那些",
        "自己", "本人", "此人", "该人",
    }

    def __init__(self, use_ner: bool = True, use_bge_filter: bool = True):
        # 从配置读取默认值
        config = get_discourse_config() if get_discourse_config else None
        parser_cfg = config.parser if config else None

        self.use_ner = use_ner if (parser_cfg is None) else parser_cfg.ner_enabled
        self.use_bge_filter = use_bge_filter if (parser_cfg is None) else parser_cfg.bge_filter_enabled
        self._bge_filter_threshold = parser_cfg.bge_filter_threshold if parser_cfg else 0.5

        # NER 模型（延迟加载）
        self._ner_tokenizer = None
        self._ner_model = None
        self._ner_loaded = False

        # BGE 编码器（单例共享）
        self._encoder = None

        # 缓存
        self._parse_cache: Dict[str, ParseResult] = {}
        self._entity_cache: Dict[str, List[ParsedEntity]] = {}

        logger.debug(f"SemanticParser initialized (ner={self.use_ner}, bge_filter={self.use_bge_filter})")

    def _init_ner(self):
        """初始化 NER Pipeline。"""
        if self._ner_loaded or not self.use_ner:
            return
        _load_ner_pipeline()
        if NER_AVAILABLE:
            self._ner_loaded = True

    def _init_encoder(self):
        """初始化 BGE 编码器。"""
        if self._encoder is not None:
            return
        try:
            from core.agent.compiler.semantic_encoder import get_encoder
            self._encoder = get_encoder()
        except Exception:
            self._encoder = None

    # ── 实体识别 ─────────────────────────────────────────────

    def extract_entities(self, text: str, use_cache: bool = True) -> List[ParsedEntity]:
        """开放域实体识别：NER + 词性标注 + BGE 过滤。

        返回排序后的实体列表（按置信度降序）。
        """
        if not text or not text.strip():
            return []

        if use_cache and text in self._entity_cache:
            return self._entity_cache[text]

        entities: List[ParsedEntity] = []

        # 1. NER 模型识别（PER/LOC/ORG）
        ner_entities = self._extract_ner_entities(text)
        entities.extend(ner_entities)

        # 2. jieba 词性标注识别（所有名词/技术名）
        if JIEBA_AVAILABLE:
            pos_entities = self._extract_pos_entities(text)
            # 去重：NER 已识别的不再添加
            ner_spans = {(e.start, e.end) for e in ner_entities}
            for e in pos_entities:
                if (e.start, e.end) not in ner_spans:
                    entities.append(e)

        # 3. BGE 语义过滤（去除低语义重要性词）
        if self.use_bge_filter and self._encoder is None:
            self._init_encoder()
        if self.use_bge_filter and self._encoder:
            entities = self._bge_filter_entities(text, entities)

        # 4. 排序：NER 实体优先，然后按长度降序
        def sort_key(e: ParsedEntity) -> Tuple[int, int]:
            is_ner = 1 if e.entity_type in ("PER", "LOC", "ORG") else 0
            return (is_ner, len(e.text))
        entities.sort(key=sort_key, reverse=True)

        # 去重（按文本）
        seen: Set[str] = set()
        deduped: List[ParsedEntity] = []
        for e in entities:
            key = e.text.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(e)

        if use_cache:
            self._entity_cache[text] = deduped
        return deduped

    def _extract_ner_entities(self, text: str) -> List[ParsedEntity]:
        """使用 ModelScope NER Pipeline 提取实体（PER/LOC/ORG）。"""
        self._init_ner()
        if not self._ner_loaded or _ner_pipeline is None:
            return []

        try:
            result = _ner_pipeline(text)
            entities = []
            if result and isinstance(result, dict) and "output" in result:
                for item in result["output"]:
                    # DAMO pipeline 输出格式: {"type": "PER", "start": 0, "end": 2, "span": "张三"}
                    entity_type = item.get("type", "UNKNOWN")
                    start = item.get("start", 0)
                    end = item.get("end", 0)
                    span = item.get("span", "")
                    if span:
                        entities.append(ParsedEntity(
                            text=span,
                            start=start,
                            end=end,
                            entity_type=entity_type,
                            confidence=0.95,
                        ))
            return entities
        except Exception:
            return []

    def _decode_ner_tags(
        self,
        text: str,
        tokens: List[str],
        predictions: np.ndarray,
    ) -> List[ParsedEntity]:
        """将 BIO 标签解码为实体列表。"""
        # NER 标签映射（DAMO 模型）
        # 0:O, 1:B-LOC, 2:S-LOC, 3:B-ORG, 4:S-ORG, 5:B-PER, 6:S-PER
        # 7:I-LOC, 8:E-LOC, 9:I-ORG, 10:E-ORG, 11:I-PER, 12:E-PER
        label_map = {
            0: "O", 1: "B-LOC", 2: "S-LOC", 3: "B-ORG", 4: "S-ORG",
            5: "B-PER", 6: "S-PER", 7: "I-LOC", 8: "E-LOC",
            9: "I-ORG", 10: "E-ORG", 11: "I-PER", 12: "E-PER",
        }

        entities = []
        current_entity = None
        current_start = 0
        char_idx = 0

        # 跳过 [CLS]
        for i in range(1, len(tokens) - 1):  # 跳过 [CLS] 和 [SEP]
            token = tokens[i]
            label = label_map.get(int(predictions[i]), "O")

            # 处理 ## 子词（BertTokenizer 的 WordPiece）
            if token.startswith("##"):
                token = token[2:]
            elif token in ("[CLS]", "[SEP]", "[PAD]"):
                continue

            if label.startswith("B-") or label.startswith("S-"):
                # 保存上一个实体
                if current_entity is not None:
                    entity_text = text[current_start:char_idx]
                    if entity_text:
                        entities.append(ParsedEntity(
                            text=entity_text,
                            start=current_start,
                            end=char_idx,
                            entity_type=current_entity,
                            confidence=0.95,
                        ))
                # 开始新实体
                entity_type = label.split("-")[1]
                current_entity = entity_type
                current_start = char_idx
                char_idx += len(token)
            elif label.startswith("I-") or label.startswith("E-"):
                # 继续当前实体
                char_idx += len(token)
            else:  # O
                if current_entity is not None:
                    entity_text = text[current_start:char_idx]
                    if entity_text:
                        entities.append(ParsedEntity(
                            text=entity_text,
                            start=current_start,
                            end=char_idx,
                            entity_type=current_entity,
                            confidence=0.95,
                        ))
                    current_entity = None
                char_idx += len(token)

        # 处理最后一个实体
        if current_entity is not None:
            entity_text = text[current_start:char_idx]
            if entity_text:
                entities.append(ParsedEntity(
                    text=entity_text,
                    start=current_start,
                    end=char_idx,
                    entity_type=current_entity,
                    confidence=0.95,
                ))

        return entities

    def _extract_pos_entities(self, text: str) -> List[ParsedEntity]:
        """使用 jieba 词性标注提取候选实体。"""
        if not JIEBA_AVAILABLE or pseg is None:
            return []

        entities = []
        pos = 0
        for word, flag in pseg.cut(text):
            entity_type = self.POS_ENTITY_MAP.get(flag)
            if entity_type and len(word) >= 2:  # 至少2个字符
                entities.append(ParsedEntity(
                    text=word,
                    start=pos,
                    end=pos + len(word),
                    entity_type=entity_type,
                    confidence=0.7,
                ))
            pos += len(word)
        return entities

    def _bge_filter_entities(
        self,
        text: str,
        entities: List[ParsedEntity],
    ) -> List[ParsedEntity]:
        """使用 BGE 语义向量过滤低重要性实体。"""
        if not entities or self._encoder is None:
            return entities

        # 计算文本整体的语义方向
        try:
            text_vec = self._encoder.encode(text)
        except Exception:
            return entities

        filtered = []
        for e in entities:
            try:
                entity_vec = self._encoder.encode(e.text)
                similarity = float(np.dot(text_vec, entity_vec.T)[0][0])
                # 如果实体与整体文本语义相关性 > 阈值则保留
                if similarity > self._bge_filter_threshold:
                    e.confidence = max(e.confidence, similarity)
                    filtered.append(e)
                else:
                    # 但如果是 NER 识别的高置信实体（PER/LOC/ORG），始终保留
                    if e.entity_type in ("PER", "LOC", "ORG"):
                        filtered.append(e)
            except Exception:
                filtered.append(e)

        return filtered

    # ── 关系提取（主谓宾）────────────────────────────────────

    def extract_relation(self, text: str) -> Optional[ParsedRelation]:
        """提取主谓宾关系。

        策略：
        1. jieba 分词获取词性
        2. 找第一个名词作为主语候选
        3. 找第一个动词作为谓语候选
        4. 动词后的名词作为宾语候选
        5. 用实体识别结果精化主语/宾语
        """
        if not JIEBA_AVAILABLE or pseg is None:
            return None

        words_pos = list(pseg.cut(text))
        entities = self.extract_entities(text)

        # 找主语：第一个名词（或代词）
        subject = None
        subject_entities = []
        for word, flag in words_pos:
            if flag in self.POS_ENTITY_MAP or flag in self.PRONOUN_POS:
                subject = word
                break

        # 找谓语：第一个动词
        predicate = None
        for word, flag in words_pos:
            if flag in self.VERB_POS:
                predicate = word
                break

        # 找宾语：谓语后的第一个名词
        obj = None
        object_entities = []
        found_predicate = False
        for word, flag in words_pos:
            if found_predicate and flag in self.POS_ENTITY_MAP:
                obj = word
                break
            if word == predicate:
                found_predicate = True

        # 用实体结果精化
        for e in entities:
            if subject and e.text in subject:
                subject_entities.append(e.text)
            if obj and e.text in obj:
                object_entities.append(e.text)

        # 如果没有找到主语/谓语，尝试简单规则
        if not subject:
            # 尝试提取句首的名词
            for word, flag in words_pos:
                if len(word) >= 2:
                    subject = word
                    break

        if not predicate:
            # 常见动词匹配
            common_verbs = ["是", "有", "用", "做", "写", "学习", "分析", "推荐",
                           "喜欢", "想", "帮", "给", "看", "用", "做"]
            for v in common_verbs:
                if v in text:
                    predicate = v
                    break

        return ParsedRelation(
            subject=subject,
            predicate=predicate,
            object=obj,
            subject_entities=subject_entities,
            object_entities=object_entities,
        )

    # ── 指代链构建 ───────────────────────────────────────────

    def build_coreference_chains(
        self,
        texts: List[str],
    ) -> List[CoreferenceChain]:
        """构建跨句指代链。

        输入多句文本，输出指代链列表。
        每个指代链包含一个实体的所有提及（包括代词）。
        """
        if not texts:
            return []

        # 收集所有实体和代词
        all_mentions: List[Tuple[str, int, Mention]] = []  # (text, sentence_idx, Mention)
        for i, text in enumerate(texts):
            entities = self.extract_entities(text)
            for e in entities:
                all_mentions.append((text, i, Mention(
                    text=e.text,
                    position=e.start,
                    entity_type=e.entity_type,
                    is_pronoun=False,
                )))
            # 检测代词
            for pronoun in self.PRONOUNS:
                pos = text.find(pronoun)
                while pos != -1:
                    all_mentions.append((text, i, Mention(
                        text=pronoun,
                        position=pos,
                        entity_type="PRONOUN",
                        is_pronoun=True,
                    )))
                    pos = text.find(pronoun, pos + 1)

        # 按句子索引和位置排序
        all_mentions.sort(key=lambda x: (x[1], x[2].position))

        # 构建指代链：
        # 1. 非代词实体各自形成链
        # 2. 代词通过语义相似度关联到最近的相关实体链
        chains: List[CoreferenceChain] = []
        entity_chains: Dict[str, CoreferenceChain] = {}  # 实体文本 → 链

        # 先为每个非代词实体创建链
        for text, sent_idx, mention in all_mentions:
            if not mention.is_pronoun:
                key = mention.text.lower()
                if key not in entity_chains:
                    chain = CoreferenceChain(
                        entity_id=f"ent_{len(chains)}",
                        mentions=[mention],
                        representative=mention.text,
                    )
                    chains.append(chain)
                    entity_chains[key] = chain
                else:
                    entity_chains[key].mentions.append(mention)

        # 然后为代词找最佳关联链
        if self._encoder is None:
            self._init_encoder()

        for text, sent_idx, mention in all_mentions:
            if mention.is_pronoun:
                # 找最近的前置实体链
                best_chain = None
                best_score = -1.0

                # 策略1：同句内找最近实体
                for _, other_sent, other in all_mentions:
                    if other_sent == sent_idx and not other.is_pronoun:
                        if other.position < mention.position:
                            # 距离越近越好
                            distance = mention.position - other.position
                            score = 1.0 / (1.0 + distance)
                            if score > best_score:
                                best_score = score
                                best_chain = entity_chains.get(other.text.lower())

                # 策略2：语义相似度（如果 encoder 可用）
                if self._encoder and best_chain is None:
                    mention_vec = self._encoder.encode(mention.text)
                    for chain in chains:
                        if chain.mentions and not chain.mentions[0].is_pronoun:
                            rep_vec = self._encoder.encode(chain.representative)
                            sim = float(np.dot(mention_vec, rep_vec.T)[0][0])
                            if sim > best_score and sim > 0.6:
                                best_score = sim
                                best_chain = chain

                if best_chain:
                    best_chain.mentions.append(mention)

        return chains

    # ── 辅助方法 ───────────────────────────────────────────

    def clear_cache(self):
        """清空缓存。"""
        self._parse_cache.clear()
        self._entity_cache.clear()
