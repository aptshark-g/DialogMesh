# core/agent/compiler/header_injector.py
"""Stage 1: HeaderInjector — 完整版头文件引入器。

类比 C 语言预处理器：#include <context.h> —— 将当前会话的实体缓存、
历史话题摘要、领域知识库作为"头文件"引入，补全自然语言中省略的主语/宾语。

完整版改进：
- 使用 SemanticParser 做开放域实体识别（替代硬编码词典）
- 使用 SemanticParser 的指代链做跨句代词消解
- 保留规则知识库作为兜底和补充
- 会话级指代链缓存（跨轮次维护）

设计约束:
- 零 LLM 依赖
- 语义解析器优先，规则兜底
- 可热加载 YAML/JSON 知识库
- 歧义时保留最高置信度候选，标记来源
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

try:
    import jieba
except ImportError:
    jieba = None  # type: ignore

logger = logging.getLogger(__name__)

# ── 默认知识库（fallback） ─────────────────────────────────────────
_DEFAULT_KB: Dict[str, Any] = {
    "default": {
        "causal_kb": {
            "很呛": ["汽水", "碳酸饮料", "辣椒", "烟雾"],
            "很甜": ["汽水", "糖果", "蜂蜜", "巧克力"],
            "很苦": ["咖啡", "茶", "药", "苦瓜"],
            "很烫": ["CPU", "显卡", "电源", "热水"],
            "很慢": ["硬盘", "网络", "查询", "加载"],
            "卡顿": ["游戏", "程序", "动画", "视频"],
            "崩溃": ["程序", "APP", "游戏", "进程"],
            "闪退": ["APP", "游戏", "程序", "浏览器"],
            "蓝屏": ["驱动", "内核", "内存", "IRQ"],
            "死机": ["内核", "驱动", "硬件", "中断"],
            "不安全": ["API", "函数", "调用", "链接"],
            "只读": ["内存页", "寄存器", "文件", "数据库"],
        },
        "default_object_kb": {
            "scan": ["内存", "地址空间", "进程"],
            "patch": ["数值", "地址", "代码"],
            "hook": ["函数", "API", "消息", "系统调用"],
            "read": ["内存", "寄存器", "文件", "配置"],
            "write": ["内存", "寄存器", "文件", "数据"],
            "分析": ["数据", "日志", "性能", "代码"],
            "扫描": ["内存", "端口", "漏洞", "文件"],
            "修改": ["数值", "配置", "代码", "参数"],
            "查找": ["地址", "函数", "变量", "文件"],
            "推荐": ["工具", "方案", "模型", "库"],
            "写": ["代码", "文档", "函数", "脚本"],
            "做": ["项目", "任务", "实验", "分析"],
            "看": ["结果", "日志", "输出", "代码"],
            "查": ["文档", "资料", "错误", "状态"],
        },
    },
}


# ── 数据类 ──────────────────────────────────────────────────────
@dataclass
class EntityCandidate:
    """隐含实体候选。"""
    entity: str
    source: str          # "context" / "kb" / "inference" / "default_object" / "coreference_chain"
    confidence: float      # 0.0 ~ 1.0
    reason: str          # 推断原因描述


@dataclass
class InjectionResult:
    """头文件引入结果。"""
    text: str                      # 补全后的文本
    replacements: List[Tuple[str, str, EntityCandidate]] = field(default_factory=list)
    unresolved_pronouns: List[str] = field(default_factory=list)


# ── 主类 ──────────────────────────────────────────────────────────
class HeaderInjector:
    """完整版头文件引入器：补全隐含实体（主语/宾语省略）。"""

    # 代词/省略词词典（中文 + 英文）
    PRONOUNS = [
        "这个", "那个", "它", "他", "她", "这", "那", "其", "之",
        "this", "that", "it", "they", "them", "these", "those",
    ]

    # 需要补全的省略模式（宾语省略）
    OMITTED_PATTERNS = [
        (re.compile(r"(?:帮我|给我|请)\s*([a-zA-Z]+|[^\s]{1,4})\s*$"), "verb_no_object"),
    ]

    def __init__(
        self,
        context_window_size: int = 5,
        kb_path: Optional[str] = None,
        domain: str = "default",
        use_semantic_parser: bool = True,
    ):
        # 从配置读取默认值
        config = get_discourse_config() if get_discourse_config else None
        inj_cfg = config.injector if config else None

        self.context_window_size = context_window_size if (inj_cfg is None) else inj_cfg.context_window_size
        self.domain = domain if (inj_cfg is None) else inj_cfg.domain
        self.kb_path = Path(
            kb_path
            or (inj_cfg.kb_path if inj_cfg else None)
            or os.path.expanduser("~/.memorygraph/kb/header_kb.json")
        )

        # 加载知识库
        self._causal_kb: Dict[str, List[str]] = {}
        self._default_object_kb: Dict[str, List[str]] = {}
        self._load_kb()

        # 语义解析器（完整版核心）
        self._parser = None
        if use_semantic_parser if (inj_cfg is None) else inj_cfg.semantic_parser_enabled:
            try:
                from core.agent.compiler.semantic_parser import SemanticParser
                self._parser = SemanticParser(use_ner=True, use_bge_filter=True)
            except Exception as e:
                logger.warning(f"SemanticParser init failed in HeaderInjector: {e}")
                self._parser = None

        # 语义编码器（用于语义相似度）
        self._encoder = None
        try:
            from core.agent.compiler.semantic_encoder import get_encoder
            self._encoder = get_encoder()
        except Exception as e:
            logger.warning(f"Encoder init failed in HeaderInjector: {e}")
            self._encoder = None

        logger.debug(f"HeaderInjector initialized (domain={self.domain}, window={self.context_window_size})")

        # 会话级缓存
        self._session_entity_cache: Dict[str, List[str]] = {}
        self._session_last_entity: Dict[str, Optional[str]] = {}
        self._turn_entity_cache: Dict[str, List[str]] = {}
        # 指代链缓存（完整版新增）
        self._coreference_chains: Dict[str, List[Any]] = {}  # session_id -> chains

    # ── 公共接口 ──────────────────────────────────────────────────

    def inject(
        self,
        raw_text: str,
        session_id: str,
        session_history: Optional[List[Dict[str, Any]]] = None,
        turn_index: int = 0,
    ) -> InjectionResult:
        """主入口：补全隐含实体，返回补全后的文本 + 替换记录。

        完整版流程：
        1. 更新上下文缓存（SemanticParser 提取实体 + 指代链）
        2. 构建/更新指代链（跨句实体关联）
        3. 检测并替换代词/省略
        """
        # 1. 更新上下文缓存（从最近 N 轮历史提取实体）
        if session_history:
            self._update_context_cache(session_id, session_history)
            # 完整版：构建跨句指代链
            self._update_coreference_chains(session_id, session_history)

        # 2. 重置同轮缓存
        self._turn_entity_cache[session_id] = []

        # 3. 提取当前文本中的实体
        current_entities = self._extract_entities(raw_text)
        self._turn_entity_cache[session_id] = current_entities

        # 4. 检测并替换代词/省略
        result = InjectionResult(text=raw_text)
        text = raw_text

        # 4.1 代词解析（完整版：指代链优先）
        text = self._resolve_pronouns(text, session_id, result)

        # 4.2 宾语省略补全
        text = self._resolve_omitted_objects(text, session_id, result)

        result.text = text
        return result

    def reset_session(self, session_id: str):
        """重置会话缓存。"""
        self._session_entity_cache.pop(session_id, None)
        self._session_last_entity.pop(session_id, None)
        self._turn_entity_cache.pop(session_id, None)
        self._coreference_chains.pop(session_id, None)

    # ── 实体提取（完整版：SemanticParser）────────────────────────

    def _extract_entities(self, text: str) -> List[str]:
        """开放域实体提取：SemanticParser 优先，规则兜底。"""
        if self._parser:
            try:
                parsed_entities = self._parser.extract_entities(text)
                return [e.text for e in parsed_entities]
            except Exception as e:
                logger.warning(f"SemanticParser entity extraction failed: {e}")
        return self._extract_entities_fallback(text)

    def _extract_entities_fallback(self, text: str) -> List[str]:
        """规则提取实体（兜底）。"""
        entities = []
        entities.extend(re.findall(r"0x[0-9a-fA-F]+", text))
        entities.extend(re.findall(r"\b\d+\b", text))
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
        if jieba:
            words = jieba.lcut(text)
            for word in words:
                if len(word) >= 2 and not word.isdigit():
                    if word not in {"什么", "怎么", "为什么", "多少", "哪里", "谁", "哪个"}:
                        entities.append(word)
        return entities

    # ── 指代链构建（完整版新增）────────────────────────────────────

    def _update_coreference_chains(
        self,
        session_id: str,
        history: List[Dict[str, Any]],
    ):
        """使用 SemanticParser 构建跨句指代链。"""
        if not self._parser:
            return

        try:
            # 提取最近 N 轮的用户消息文本
            recent = history[-self.context_window_size:] if len(history) > self.context_window_size else history
            texts = [entry.get("content", "") for entry in recent if entry.get("role") == "user"]
            if len(texts) >= 2:
                chains = self._parser.build_coreference_chains(texts)
                self._coreference_chains[session_id] = chains
        except Exception as e:
            logger.warning(f"Coreference chain building failed: {e}")

    # ── 代词解析（完整版：指代链优先）────────────────────────────

    def _resolve_pronouns(
        self,
        text: str,
        session_id: str,
        result: InjectionResult,
    ) -> str:
        """解析文本中的代词并替换。完整版：指代链优先，规则兜底。"""
        for pronoun in self.PRONOUNS:
            if pronoun in text:
                candidate = self._resolve_single_pronoun(pronoun, text, session_id)
                if candidate:
                    text = text.replace(pronoun, candidate.entity, 1)
                    result.replacements.append((pronoun, candidate.entity, candidate))
                else:
                    result.unresolved_pronouns.append(pronoun)
                break
        return text

    def _resolve_single_pronoun(
        self,
        pronoun: str,
        text: str,
        session_id: str,
    ) -> Optional[EntityCandidate]:
        """按优先级解析单个代词。完整版：指代链 > 同轮 > 上下文 > 知识库 > 语义相似度。"""
        pos = text.find(pronoun)
        before_text = text[:pos] if pos > 0 else ""
        after_text = text[pos + len(pronoun):] if pos >= 0 else ""

        # 策略 1: 指代链解析（完整版核心）
        chains = self._coreference_chains.get(session_id, [])
        if chains:
            for chain in chains:
                # 检查链中是否有代词提及
                has_pronoun = any(m.is_pronoun for m in chain.mentions)
                if has_pronoun:
                    # 返回该链的代表实体
                    rep = chain.representative
                    if rep and rep != pronoun:
                        return EntityCandidate(
                            entity=rep,
                            source="coreference_chain",
                            confidence=0.92,
                            reason=f"指代链关联：代词'{pronoun}'指向实体'{rep}'",
                        )

        # 策略 2: 同轮显性指代
        same_turn_entities = self._turn_entity_cache.get(session_id, [])
        if same_turn_entities:
            for entity in reversed(same_turn_entities):
                if entity in before_text:
                    return EntityCandidate(
                        entity=entity,
                        source="inference",
                        confidence=0.95,
                        reason=f"同轮显性指代：代词前已出现'{entity}'",
                    )

        # 策略 3: 上下文最近实体
        last_entity = self._session_last_entity.get(session_id)
        if last_entity:
            return EntityCandidate(
                entity=last_entity,
                source="context",
                confidence=0.85,
                reason="继承上下文最近实体",
            )

        # 策略 4: 因果知识库推断
        for attr, candidates in self._causal_kb.items():
            if attr in after_text or attr in before_text:
                context_entities = self._session_entity_cache.get(session_id, [])
                for c in candidates:
                    if c in context_entities:
                        return EntityCandidate(
                            entity=c,
                            source="kb",
                            confidence=0.70,
                            reason=f"属性'{attr}'的因果关联 → 上下文实体'{c}'",
                        )
                return EntityCandidate(
                    entity=candidates[0],
                    source="kb",
                    confidence=0.60,
                    reason=f"属性'{attr}'的因果关联 → 默认候选'{candidates[0]}'",
                )

        # 策略 5: 会话历史实体池
        context_entities = self._session_entity_cache.get(session_id, [])
        if context_entities:
            return EntityCandidate(
                entity=context_entities[-1],
                source="context",
                confidence=0.60,
                reason="继承会话历史最近实体",
            )

        # 策略 6: 语义相似度匹配
        if self._encoder and context_entities:
            try:
                import numpy as np
                context_vec = self._encoder.encode(text)
                candidate_vecs = self._encoder.encode(context_entities)
                similarities = np.dot(context_vec, candidate_vecs.T)[0]
                best_idx = int(np.argmax(similarities))
                best_score = float(similarities[best_idx])
                if best_score > 0.65:
                    return EntityCandidate(
                        entity=context_entities[best_idx],
                        source="semantic",
                        confidence=best_score,
                        reason=f"语义相似度匹配 (score={best_score:.3f})",
                    )
            except Exception as e:
                logger.warning(f"Semantic similarity resolution failed: {e}")

        return None

    # ── 宾语省略补全 ──────────────────────────────────────────────

    def _resolve_omitted_objects(
        self,
        text: str,
        session_id: str,
        result: InjectionResult,
    ) -> str:
        """补全动词后的省略宾语。"""
        text_lower = text.lower()
        for verb in sorted(self._default_object_kb.keys(), key=len, reverse=True):
            if text_lower.endswith(verb.lower()):
                default_objs = self._default_object_kb[verb]
                context_entities = self._session_entity_cache.get(session_id, [])
                for obj in default_objs:
                    if obj in context_entities:
                        text = text + obj
                        result.replacements.append(
                            ("", obj, EntityCandidate(
                                entity=obj,
                                source="default_object",
                                confidence=0.50,
                                reason=f"谓语'{verb}'的默认宾语（上下文匹配）",
                            ))
                        )
                        return text
                text = text + default_objs[0]
                result.replacements.append(
                    ("", default_objs[0], EntityCandidate(
                        entity=default_objs[0],
                        source="default_object",
                        confidence=0.45,
                        reason=f"谓语'{verb}'的默认宾语",
                    ))
                )
                return text
        return text

    # ── 缓存更新 ───────────────────────────────────────────────────

    def _update_context_cache(
        self,
        session_id: str,
        history: List[Dict[str, Any]],
    ):
        """从最近 N 轮历史提取实体，更新缓存。"""
        recent = history[-self.context_window_size:] if len(history) > self.context_window_size else history

        all_entities = []
        for entry in recent:
            content = entry.get("content", "")
            entities = self._extract_entities(content)
            all_entities.extend(entities)

        seen = set()
        deduped = []
        for e in all_entities:
            key = e.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(e)

        self._session_entity_cache[session_id] = deduped

        # 更新最近实体
        for entry in reversed(recent):
            if entry.get("role") == "user":
                entities = self._extract_entities(entry.get("content", ""))
                if entities:
                    self._session_last_entity[session_id] = entities[-1]
                break

    # ── 知识库加载 ──────────────────────────────────────────────────

    def _load_kb(self):
        """加载知识库（JSON/YAML）。支持热加载。"""
        if not self.kb_path.exists():
            self._create_default_kb()

        suffix = self.kb_path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            try:
                import yaml
                with open(self.kb_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except ImportError:
                json_path = self.kb_path.with_suffix(".json")
                if json_path.exists():
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    data = _DEFAULT_KB
        else:
            with open(self.kb_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        domain_data = data.get(self.domain, data.get("default", _DEFAULT_KB["default"]))
        self._causal_kb = domain_data.get("causal_kb", {})
        self._default_object_kb = domain_data.get("default_object_kb", {})

    def _create_default_kb(self):
        """创建默认知识库文件。"""
        self.kb_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.kb_path, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_KB, f, ensure_ascii=False, indent=2)

    def reload_kb(self):
        """热加载知识库（运行时调用）。"""
        self._load_kb()
