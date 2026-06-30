# -*- coding: utf-8 -*-
"""
core/agent/cognitive_compiler/injector.py
────────────────────────────────────────
Header injector with YAML/JSON hot-loadable knowledge base.

设计要点（修正坑2）：
  - CAUSAL_KB 从硬编码改为 YAML/JSON 热加载
  - 支持多领域（default/kernel_reverse/game_reverse）
  - 自动创建默认 KB 文件
  - reload_kb() 支持运行时热加载
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent.cognitive_compiler.decomposer import ParsedClause
from core.agent.cognitive_compiler.entity_cache import EntityCache

# yaml 为可选依赖（某些环境可能未安装）
try:
    import yaml
    _HAS_YAML = True
except ImportError:
    yaml = None
    _HAS_YAML = False


class HeaderInjector:
    """
    头文件注入器（隐式实体补全）。
    通过知识库查找省略的实体，并补全到子句中。
    新增：代词消解（历史实体回溯） + 话题切换检测。
    """

    # 话题切换短语（触发 EntityCache 清空）
    TOPIC_SWITCH_PHRASES = {
        "不说这个了", "换个话题", "回到", "先不讨论", "回到刚才",
        "别谈这个了", "不说这个", "换一个", "换个方向",
        "let's move on", "change topic", "back to", "not this",
    }

    # 代词集合
    PRONOUNS = {"它", "这个", "那个", "this", "that", "it", "the"}

    # 类型锚点映射（从自然语言到 entity_type）
    ANCHOR_TYPE_MAP = {
        "地址": "memory_address",
        "数值": "numeric_value",
        "值": "numeric_value",
        "指针": "pointer_chain",
        "进程": "process_name",
        "模块": "module_name",
        "函数": "function_name",
        "api": "function_name",
        "api函数": "function_name",
        "数据": "numeric_value",
        "字节": "byte_pattern",
        "断点": "breakpoint_address",
    }

    # 默认知识库路径
    DEFAULT_KB_DIR = Path("~/.memorygraph/kb").expanduser()
    DEFAULT_KB_FILE = DEFAULT_KB_DIR / "causal_kb.yaml"

    # 回退默认知识库（仅在文件不存在时使用）
    _DEFAULT_KB_CONTENT = {
        "version": "1.0",
        "domains": {
            "default": {
                "汽水": {"type": "product", "properties": {"drinkable": True, "carbonated": True}},
                "碳酸饮料": {"type": "product", "properties": {"drinkable": True, "carbonated": True}},
                "牛奶": {"type": "product", "properties": {"drinkable": True, "nutritious": True}},
            },
            "kernel_reverse": {
                "地址": {"type": "memory_address", "properties": {"readable": True, "writable": True}},
                "指针": {"type": "pointer_chain", "properties": {"dereferenceable": True}},
                "API": {"type": "function", "properties": {"callable": True, "needs_validation": True}},
            },
            "game_reverse": {
                "血量": {"type": "numeric_value", "properties": {"modifiable": True}},
                "金币": {"type": "numeric_value", "properties": {"modifiable": True}},
                "坐标": {"type": "memory_address", "properties": {"readable": True, "3d": True}},
            },
        },
    }

    def __init__(
        self,
        kb_path: Optional[str] = None,
        domain: str = "default",
    ):
        self._kb_path = Path(kb_path) if kb_path else self.DEFAULT_KB_FILE
        self._domain = domain
        self._kb: Dict[str, Any] = {}
        self._load_kb()

    # ── 知识库加载 ───────────────────────────────────────────

    def _load_kb(self) -> None:
        """加载知识库文件。"""
        if self._kb_path.exists():
            self._kb = self._load_from_file(self._kb_path)
        else:
            # 创建默认 KB
            self._create_default_kb()
            self._kb = dict(self._DEFAULT_KB_CONTENT)

    def _load_from_file(self, path: Path) -> Dict[str, Any]:
        """从文件加载 KB（支持 .yaml/.json/.yml，无 yaml 时回退 json）。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                if path.suffix in (".yaml", ".yml"):
                    if _HAS_YAML and yaml:
                        return yaml.safe_load(f) or {}
                    else:
                        # 无 yaml 时尝试 json 解析（YAML 是 JSON 超集，简单结构可兼容）
                        return json.load(f)
                elif path.suffix == ".json":
                    return json.load(f)
                else:
                    # 尝试 YAML 回退
                    if _HAS_YAML and yaml:
                        return yaml.safe_load(f) or {}
                    return json.load(f)
        except Exception as e:
            print(f"[HeaderInjector] KB load failed: {e}, using default")
            return dict(self._DEFAULT_KB_CONTENT)

    def _create_default_kb(self) -> None:
        """创建默认 KB 文件。"""
        try:
            self.DEFAULT_KB_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.DEFAULT_KB_FILE, "w", encoding="utf-8") as f:
                if _HAS_YAML and yaml:
                    yaml.dump(self._DEFAULT_KB_CONTENT, f, allow_unicode=True, sort_keys=False)
                else:
                    json.dump(self._DEFAULT_KB_CONTENT, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[HeaderInjector] create default KB failed: {e}")

    def reload_kb(self, kb_path: Optional[str] = None) -> bool:
        """运行时热加载知识库。"""
        if kb_path:
            self._kb_path = Path(kb_path)
        self._kb = self._load_from_file(self._kb_path)
        return bool(self._kb)

    def set_domain(self, domain: str) -> None:
        """切换领域。"""
        self._domain = domain

    # ── 注入 API ───────────────────────────────────────────

    def inject(
        self,
        clauses: List[ParsedClause],
        session_history: Optional[List[Dict[str, Any]]] = None,
        entity_cache: Optional[EntityCache] = None,
    ) -> Tuple[List[ParsedClause], Dict[str, Any]]:
        """
        对子句列表执行头文件注入 + 代词消解。
        返回 (补全后的子句, 注入日志)。
        """
        session_history = session_history or []
        injected_clauses = []
        headers_log: Dict[str, Any] = {"matched": [], "missed": [], "backfilled": [], "domain": self._domain}

        # 检测话题切换
        if any(self._detect_topic_switch(c.raw_text) for c in clauses):
            if entity_cache is not None:
                entity_cache.clear()
                headers_log["topic_switch_cleared"] = True

        domain_kb = self._kb.get("domains", {}).get(self._domain, {})

        for clause in clauses:
            if clause.parse_failed:
                injected_clauses.append(clause)
                continue

            # 1. 代词消解（历史实体回溯）— 优先级高于 KB
            if entity_cache is not None and self._is_pronoun_or_empty(clause.subject):
                backfilled, source = self._backfill_pronoun(clause, entity_cache)
                if backfilled:
                    headers_log["backfilled"].append({
                        "term": clause.subject,
                        "value": clause.subject,
                        "source": source,
                        "type": "pronoun",
                    })
                    injected_clauses.append(clause)
                    continue

            # 2. 知识库补全主语
            if clause.subject:
                matched = self._lookup_kb(clause.subject, domain_kb)
                if matched:
                    clause.subject = f"{clause.subject}({matched['type']})"
                    headers_log["matched"].append({
                        "term": clause.subject,
                        "kb_entry": matched,
                        "type": "subject",
                    })
                else:
                    headers_log["missed"].append({"term": clause.subject, "type": "subject"})

            # 3. 知识库补全宾语
            if clause.object:
                matched = self._lookup_kb(clause.object, domain_kb)
                if matched:
                    clause.object = f"{clause.object}({matched['type']})"
                    headers_log["matched"].append({
                        "term": clause.object,
                        "kb_entry": matched,
                        "type": "object",
                    })
                else:
                    headers_log["missed"].append({"term": clause.object, "type": "object"})

            injected_clauses.append(clause)

        return injected_clauses, headers_log

    # ── 代词消解 ───────────────────────────────────────────

    def _is_pronoun_or_empty(self, text: str) -> bool:
        """判断是否为代词或空，或包含代词（如"这个地址"中的"这个"）。"""
        if not text:
            return True
        text_lower = text.lower().strip()
        # 精确匹配代词
        if text_lower in ("", "它", "这个", "那个", "this", "that", "it", "the"):
            return True
        # 包含代词（如"这个地址"）
        if any(w in text_lower for w in self.PRONOUNS):
            return True
        return False

    def _backfill_pronoun(self, clause: ParsedClause, entity_cache: EntityCache) -> Tuple[bool, str]:
        """
        代词消解回溯。
        返回 (是否成功补全, 来源描述)。
        """
        text = clause.raw_text.lower()

        # 1. 类型锚点匹配（如"那个地址" -> 提取"地址" -> 搜索 memory_address）
        anchor_type = self._extract_anchor_type(clause.raw_text)
        if anchor_type:
            result = entity_cache.search_by_type(anchor_type)
            if result:
                value, entity = result
                clause.subject = value
                clause.backfilled = True
                clause.backfill_source = f"[上下文类型匹配:{anchor_type}]"
                return True, clause.backfill_source

        # 2. 模糊代词兜底（"它"、"那个"、"this"）
        if any(w in text for w in self.PRONOUNS):
            result = entity_cache.search_last()
            if result:
                value, entity = result
                clause.subject = value
                clause.backfilled = True
                clause.backfill_source = "[上下文最近实体]"
                return True, clause.backfill_source

        return False, ""

    def _extract_anchor_type(self, text: str) -> Optional[str]:
        """从文本中提取类型锚点（如"那个地址" -> "memory_address"）。"""
        text = text.lower()
        for keyword, entity_type in self.ANCHOR_TYPE_MAP.items():
            if keyword in text:
                return entity_type
        return None

    def _detect_topic_switch(self, text: str) -> bool:
        """检测话题切换短语。"""
        text_lower = text.lower()
        for phrase in self.TOPIC_SWITCH_PHRASES:
            if phrase in text_lower:
                return True
        return False

    def _lookup_kb(self, term: str, domain_kb: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """在知识库中查找术语。"""
        # 精确匹配
        if term in domain_kb:
            return domain_kb[term]
        # 部分匹配
        for key, value in domain_kb.items():
            if key in term or term in key:
                return value
        return None

    def __repr__(self) -> str:
        return f"HeaderInjector(domain={self._domain}, kb_path={self._kb_path})"
