# DialogMesh 上下文管理器 — 工程实现文档

> **文档编号**: ENGINEERING-CONTEXT-MANAGER-008  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 工程待实现（数据模型已定义）  
> **对应设计文档**: `DESIGN_FULL_CONCEPT.md` §5.3（Context Window）  
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`（认知双工架构）  
> **对应数据模型**: `ENGINEERING_DATA_MODEL.md` §7.3（ContextWindow / TurnRecord / TurnSummary / TopicSummary / ColdIndexEntry）  
> **对应持久化**: `ENGINEERING_PERSISTENCE.md` §6-§8（Hot/Warm/Cold 层）  
> **原则**: 上下文管理是认知双工的信息枢纽，所有层通过 ContextManager 交换信息。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览](#4-架构总览)
- [5. 分层上下文管理](#5-分层上下文管理)
- [6. 上下文组装器](#6-上下文组装器)
- [7. 与 Topic Tree 的集成](#7-与-topic-tree-的集成)
- [8. 与 Cognitive Tree 的集成](#8-与-cognitive-tree-的集成)
- [9. 与 Answer-LLM 的集成](#9-与-answer-llm-的集成)
- [10. Token 预算管理](#10-token-预算管理)
- [11. 测试策略](#11-测试策略)
- [12. 附录：简化与待讨论项](#12-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh **Context Manager（上下文管理器）**的完整实现规范。数据模型已在 `ENGINEERING_DATA_MODEL.md` §7.3 中定义，持久化层已在 `ENGINEERING_PERSISTENCE.md` 中定义。本文档定义**操作层**（分层管理、上下文组装、压缩、迁移）和**集成层**（与 Topic Tree、Cognitive Tree、Answer-LLM 的交互）。

### 1.2 范围

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| 分层上下文（Hot/Warm/Cool/Cold） | `DESIGN_FULL_CONCEPT.md` §5.3 | §5 | 4 层工作记忆 |
| 上下文组装 | `DESIGN_FULL_CONCEPT.md` §5.3 | §6 | 为 LLM 生成 Prompt 组装上下文 |
| 与 Topic Tree 集成 | `DESIGN_FULL_CONCEPT.md` §5.3 | §7 | 主题继承 |
| 与 Cognitive Tree 集成 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §8 | 认知状态引用 |
| 与 Answer-LLM 集成 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §5 | §9 | 穿透层上下文读取 |
| Token 预算管理 | `DESIGN_FULL_CONCEPT.md` §5.3 | §10 | 动态预算分配 |
| 压缩策略 | `DESIGN_FULL_CONCEPT.md` §5.3 | §10 | 规则模板 vs LLM 驱动 |

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/context_manager.py` | 上下文管理器主类 | ~300 行 | 新增 |
| `core/agent/context_assembler.py` | 上下文组装器（为 LLM 生成 Prompt） | ~200 行 | 新增 |
| `core/agent/context_compressor.py` | 上下文压缩器（规则模板 + 可选 LLM） | ~150 行 | 新增 |
| `core/agent/token_budget.py` | Token 预算管理器 | ~100 行 | 新增 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/orchestrator.py` | 每轮调用 `ContextManager.update()` 和 `ContextManager.assemble()` | 编排层 |
| `core/agent/persistence/session_manager.py` | 新增 `ContextWindow` 的读写方法 | 会话管理 |

---

## 3. 现有实现评估

### 3.1 数据模型（已定义）

**定义位置**: `ENGINEERING_DATA_MODEL.md` §7.3

| 模型 | 字段 | 说明 | 状态 |
|------|------|------|------|
| `ContextWindow` | `hot_layer`, `warm_layer`, `cool_layer`, `cold_index`, `base_size`, `complexity_factor`, `user_preference_factor`, `token_budget` | 分层工作记忆 | ✅ 已定义 |
| `TurnRecord` | `turn_id`, `user_input`, `intent`, `response`, `timestamp`, `metadata` | Hot Layer：完整轮次 | ✅ 已定义 |
| `TurnSummary` | `turn_id`, `category`, `key_entities`, `result_status`, `timestamp` | Warm Layer：单轮摘要 | ✅ 已定义 |
| `TopicSummary` | `topic_id`, `summary_text`, `key_decisions`, `unresolved_issues`, `user_preferences`, `start_turn`, `end_turn` | Cool Layer：多轮合并 | ✅ 已定义 |
| `ColdIndexEntry` | `topic_id`, `topic_tag`, `key_decisions`, `user_preference_updates` | Cold Layer：仅索引 | ✅ 已定义 |

### 3.2 持久化（已实现）

**实现位置**: `ENGINEERING_PERSISTENCE.md` §6-§8

| 功能 | 状态 | 备注 |
|------|------|------|
| Hot Layer（内存 OrderedDict） | ✅ 已实现 | `SessionManager` |
| Warm Layer（SQLite） | ✅ 已实现 | `SQLiteSessionStore` |
| Cold Layer（归档文件） | ✅ 已实现 | `TieredStorageManager` |
| 自动迁移（Hot→Warm→Cold） | ✅ 已实现 | `TieredStorageManager` |

### 3.3 差距分析

| 设计文档需求 | 现有实现 | 差距 | 优先级 |
|------------|---------|------|--------|
| 分层上下文管理器（统一 API） | 无 | 需新增 `ContextManager` | P1 |
| 上下文组装器（为 LLM 生成 Prompt） | 无 | 需新增 `ContextAssembler` | P1 |
| 上下文压缩（Warm→Cool→Cold） | 无 | 需新增 `ContextCompressor` | P1 |
| Token 预算动态管理 | 无 | 需新增 `TokenBudgetManager` | P2 |
| 与 Topic Tree 集成（主题继承） | 无 | 需新增 `ContextManager` 集成 | P2 |
| 与 Cognitive Tree 集成（认知状态） | 无 | 需新增 `ContextManager` 集成 | P2 |
| 与 Answer-LLM 集成（上下文组装） | 无 | 需新增 `ContextAssembler` 集成 | P2 |

---

## 4. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         用户输入层                                            │
│                              ↓                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  认知双工层（PCR / Intent / Planning）                                         │
│  ────────────────────────────────────────────────────────────────────────  │
│  • 每轮输出 → ContextManager.update()                                        │
│  • 意图、实体、PCR 输出、Cognitive Tree 节点 → 写入 Hot Layer                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Context Manager（本文档）                                                     │
│  ═══════════════════════════════════════════════════════════════════  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐            │
│  │ ContextManager   │  │ ContextAssembler │  │ ContextCompressor│            │
│  │ 分层管理         │  │ Prompt 组装      │  │ 压缩（规则+LLM） │            │
│  │ Hot/Warm/Cool/   │  │ 为 6 个 LLM 实例 │  │ Warm→Cool→Cold  │            │
│  │ Cold 自动迁移    │  │ 生成上下文包     │  │ 摘要生成         │            │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘            │
│  ┌──────────────────┐  ┌──────────────────┐                                   │
│  │ TokenBudgetManager│  │ TopicTreeIntegrator│                                 │
│  │ 动态预算分配     │  │ 主题继承         │                                  │
│  │ 8000 tokens 上限 │  │ 活跃分支注入     │                                  │
│  └──────────────────┘  └──────────────────┘                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  6 个 LLM 实例                                                                │
│  ────────────────────────────────────────────────────────────────────────  │
│  PCR-LLM / Intent-LLM / Planning-LLM / Meta-Cognitive-LLM / Reflective-LLM / Answer-LLM │
│  • 每个实例通过 ContextAssembler.get_context(llm_name) 获取专属上下文包       │
├─────────────────────────────────────────────────────────────────────────────┤
│  穿透层：Answer-LLM                                                            │
│  ────────────────────────────────────────────────────────────────────────  │
│  • 读取 ContextWindow（全部 4 层）                                              │
│  • 读取 Topic Tree 活跃分支（最近 3 主题）                                      │
│  • 读取 Cognitive Tree 活跃推理链（最近 5 节点）                               │
│  • 组装综合上下文 → 生成回复                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 分层上下文管理

### 5.1 `ContextManager`

```python
class ContextManager:
    """上下文管理器 — 分层工作记忆的统一入口。"""
    
    def __init__(
        self,
        session_manager: SessionManager,
        config: ContextManagerConfig,
    ):
        self._session_mgr = session_manager
        self._config = config
        self._compressor = ContextCompressor()
        self._budget = TokenBudgetManager(config.base_token_budget)
    
    # ── 更新 ──
    def update(self, session_id: str, turn_record: TurnRecord) -> None:
        """
        每轮结束后更新上下文。
        
        流程：
        1. 将 TurnRecord 写入 Hot Layer（内存）
        2. 如果 Hot Layer 超过容量（3 轮），触发降级：
           - Hot → Warm：生成 TurnSummary，写入 SQLite
           - Warm → Cool：合并为 TopicSummary，写入 SQLite
           - Cool → Cold：归档为 gzip JSONL
        3. 更新 Token 预算
        """
        # 1. 写入 Hot Layer
        session = self._session_mgr.get_session(session_id)
        session.dialogue_state.context_window.hot_layer.append(turn_record)
        
        # 2. 检查容量，触发降级
        self._maybe_demote_hot(session_id, session)
        
        # 3. 更新 Token 预算
        self._budget.update_spent(turn_record)
    
    def _maybe_demote_hot(self, session_id: str, session: Session) -> None:
        """检查 Hot Layer 容量，触发降级。"""
        hot = session.dialogue_state.context_window.hot_layer
        if len(hot) > self._config.hot_capacity:
            # Hot → Warm： oldest 记录降级
            oldest = hot.pop(0)
            summary = self._compressor.compress_turn(oldest)
            session.dialogue_state.context_window.warm_layer.append(summary)
            self._maybe_demote_warm(session_id, session)
    
    def _maybe_demote_warm(self, session_id: str, session: Session) -> None:
        """检查 Warm Layer 容量，触发降级。"""
        warm = session.dialogue_state.context_window.warm_layer
        if len(warm) > self._config.warm_capacity:
            # Warm → Cool：合并最近 N 个 Warm 记录为 TopicSummary
            to_merge = warm[:self._config.warm_merge_batch]
            topic_summary = self._compressor.merge_turns(to_merge)
            session.dialogue_state.context_window.cool_layer.append(topic_summary)
            del warm[:self._config.warm_merge_batch]
            self._maybe_demote_cool(session_id, session)
    
    def _maybe_demote_cool(self, session_id: str, session: Session) -> None:
        """检查 Cool Layer 容量，触发降级。"""
        cool = session.dialogue_state.context_window.cool_layer
        if len(cool) > self._config.cool_capacity:
            # Cool → Cold：归档为索引
            oldest = cool.pop(0)
            index_entry = ColdIndexEntry(
                topic_id=oldest.topic_id,
                topic_tag=oldest.summary_text[:50],
                key_decisions=oldest.key_decisions,
                user_preference_updates=oldest.user_preferences,
            )
            session.dialogue_state.context_window.cold_index.append(index_entry)
            
            # 持久化到归档
            self._session_mgr.archive_cool_to_cold(session_id, oldest)
    
    # ── 查询 ──
    def get_hot_layer(self, session_id: str) -> List[TurnRecord]:
        """获取 Hot Layer（最近 1-3 轮，完整记录）。"""
        session = self._session_mgr.get_session(session_id)
        return session.dialogue_state.context_window.hot_layer
    
    def get_warm_layer(self, session_id: str) -> List[TurnSummary]:
        """获取 Warm Layer（最近 4-10 轮，摘要）。"""
        session = self._session_mgr.get_session(session_id)
        return session.dialogue_state.context_window.warm_layer
    
    def get_cool_layer(self, session_id: str) -> List[TopicSummary]:
        """获取 Cool Layer（最近 11-30 轮，合并摘要）。"""
        session = self._session_mgr.get_session(session_id)
        return session.dialogue_state.context_window.cool_layer
    
    def get_cold_index(self, session_id: str) -> List[ColdIndexEntry]:
        """获取 Cold Layer（超过 30 轮，仅索引）。"""
        session = self._session_mgr.get_session(session_id)
        return session.dialogue_state.context_window.cold_index
    
    # ── 回热（按需加载）──
    def rehydrate_cold(self, session_id: str, topic_id: str) -> Optional[TopicSummary]:
        """从 Cold 层回热到 Cool 层（用户询问历史话题时）。"""
        archived = self._session_mgr.load_archived_topic(session_id, topic_id)
        if archived:
            session = self._session_mgr.get_session(session_id)
            session.dialogue_state.context_window.cool_layer.append(archived)
            return archived
        return None
```

### 5.2 `ContextManagerConfig`

```python
@dataclass
class ContextManagerConfig:
    """上下文管理器配置。"""
    
    # 各层容量
    hot_capacity: int = 3          # 最近 1-3 轮（完整记录）
    warm_capacity: int = 7        # 最近 4-10 轮（单轮摘要）
    warm_merge_batch: int = 3     # 每 3 个 Warm 合并为 1 个 Cool
    cool_capacity: int = 20       # 最近 11-30 轮（合并摘要）
    
    # Token 预算
    base_token_budget: int = 8000  # 默认 8000 tokens
    
    # 压缩配置
    compression_strategy: str = "rule"  # "rule" | "llm" | "hybrid"
    # rule: 使用规则模板（快速，低质量）
    # llm: 使用 LLM 生成摘要（慢速，高质量）
    # hybrid: 规则为主，LLM 辅助（推荐）
    
    # 回热配置
    enable_rehydration: bool = True  # 是否允许从 Cold 回热
    rehydration_max_topics: int = 3  # 最多回热 3 个主题
```

---

## 6. 上下文组装器

### 6.1 `ContextAssembler`

```python
class ContextAssembler:
    """上下文组装器 — 为 6 个 LLM 实例生成专属上下文包。"""
    
    def __init__(self, context_manager: ContextManager, config: ContextManagerConfig):
        self._ctx_mgr = context_manager
        self._config = config
    
    def assemble(self, session_id: str, llm_name: str) -> Dict[str, Any]:
        """
        为指定 LLM 实例组装上下文包。
        
        不同 LLM 需要不同上下文：
        - PCR-LLM: 最近 1 轮 + PCR 历史
        - Intent-LLM: 最近 3 轮 + 实体提取历史
        - Planning-LLM: 最近 3 轮 + 工具注册表 + 活跃主题
        - Meta-Cognitive-LLM: 最近 5 轮 + Cognitive Tree 最近 10 节点
        - Reflective-LLM: 全部历史（跨会话）+ 用户画像
        - Answer-LLM: 全部 4 层 + Topic Tree + Cognitive Tree
        """
        assemblers = {
            "PCR-LLM": self._assemble_for_pcr,
            "Intent-LLM": self._assemble_for_intent,
            "Planning-LLM": self._assemble_for_planning,
            "Meta-Cognitive-LLM": self._assemble_for_meta,
            "Reflective-LLM": self._assemble_for_reflective,
            "Answer-LLM": self._assemble_for_answer,
        }
        
        assembler = assemblers.get(llm_name, self._assemble_default)
        return assembler(session_id)
    
    def _assemble_for_pcr(self, session_id: str) -> Dict[str, Any]:
        """PCR-LLM: 最近 1 轮 + 简短历史统计。"""
        hot = self._ctx_mgr.get_hot_layer(session_id)
        warm = self._ctx_mgr.get_warm_layer(session_id)
        
        return {
            "current_turn": hot[-1] if hot else None,
            "recent_history": [t.user_input for t in hot[-2:]] if len(hot) > 1 else [],
            "turn_count": len(hot) + len(warm),
            "token_budget_remaining": self._ctx_mgr._budget.remaining,
        }
    
    def _assemble_for_intent(self, session_id: str) -> Dict[str, Any]:
        """Intent-LLM: 最近 3 轮 + 实体提取历史 + 当前主题。"""
        hot = self._ctx_mgr.get_hot_layer(session_id)
        warm = self._ctx_mgr.get_warm_layer(session_id)
        
        return {
            "recent_turns": hot[-3:] if len(hot) >= 3 else hot,
            "extracted_entities": self._collect_entities(hot + warm),
            "current_topic": self._get_current_topic(session_id),
            "intent_history": [t.category for t in warm[-5:]] if warm else [],
        }
    
    def _assemble_for_planning(self, session_id: str) -> Dict[str, Any]:
        """Planning-LLM: 最近 3 轮 + 工具注册表 + 活跃主题 + 已执行计划。"""
        hot = self._ctx_mgr.get_hot_layer(session_id)
        warm = self._ctx_mgr.get_warm_layer(session_id)
        
        return {
            "recent_turns": hot[-3:] if len(hot) >= 3 else hot,
            "active_topic": self._get_current_topic(session_id),
            "executed_plans": self._collect_executed_plans(hot + warm),
            "available_tools": self._get_available_tools(),
        }
    
    def _assemble_for_meta(self, session_id: str) -> Dict[str, Any]:
        """Meta-Cognitive-LLM: 最近 5 轮 + Cognitive Tree 最近 10 节点。"""
        hot = self._ctx_mgr.get_hot_layer(session_id)
        warm = self._ctx_mgr.get_warm_layer(session_id)
        cool = self._ctx_mgr.get_cool_layer(session_id)
        
        return {
            "recent_turns": hot + warm[:2] if warm else hot,
            "cognitive_nodes": self._get_recent_cognitive_nodes(session_id, n=10),
            "validation_queue": self._get_validation_queue(session_id),
        }
    
    def _assemble_for_reflective(self, session_id: str) -> Dict[str, Any]:
        """Reflective-LLM: 全部历史 + 用户画像 + 跨会话摘要。"""
        return {
            "all_hot": self._ctx_mgr.get_hot_layer(session_id),
            "all_warm": self._ctx_mgr.get_warm_layer(session_id),
            "all_cool": self._ctx_mgr.get_cool_layer(session_id),
            "cold_index": self._ctx_mgr.get_cold_index(session_id),
            "user_profile": self._get_user_profile(session_id),
        }
    
    def _assemble_for_answer(self, session_id: str) -> Dict[str, Any]:
        """Answer-LLM: 全部 4 层 + Topic Tree + Cognitive Tree。"""
        return {
            "hot_layer": self._ctx_mgr.get_hot_layer(session_id),
            "warm_layer": self._ctx_mgr.get_warm_layer(session_id),
            "cool_layer": self._ctx_mgr.get_cool_layer(session_id),
            "cold_index": self._ctx_mgr.get_cold_index(session_id),
            "topic_tree_branch": self._get_topic_tree_branch(session_id),
            "cognitive_tree_branch": self._get_cognitive_tree_branch(session_id),
            "system_confidence": self._get_system_confidence(session_id),
        }
    
    def _assemble_default(self, session_id: str) -> Dict[str, Any]:
        """默认组装：最近 3 轮。"""
        hot = self._ctx_mgr.get_hot_layer(session_id)
        return {"recent_turns": hot[-3:] if len(hot) >= 3 else hot}
    
    # ── 辅助方法 ──
    def _collect_entities(self, records: List) -> List[Dict[str, Any]]:
        """从记录中提取实体。"""
        entities = []
        for r in records:
            if hasattr(r, 'intent') and r.intent.entities:
                for e in r.intent.entities:
                    entities.append({"type": e.type.value, "value": str(e.value)})
        return entities
    
    def _get_current_topic(self, session_id: str) -> Optional[str]:
        """获取当前主题（从 Topic Tree）。"""
        # 委托给 TopicTreeOperations
        return None  # 占位
    
    def _get_recent_cognitive_nodes(self, session_id: str, n: int) -> List[Dict[str, Any]]:
        """获取最近 N 个 Cognitive Tree 节点。"""
        # 委托给 CognitiveTreeStore
        return []
    
    def _get_topic_tree_branch(self, session_id: str) -> List[str]:
        """获取 Topic Tree 活跃分支。"""
        # 委托给 TopicTreeOperations
        return []
    
    def _get_cognitive_tree_branch(self, session_id: str) -> List[str]:
        """获取 Cognitive Tree 活跃推理链。"""
        # 委托给 CognitiveTreeStore
        return []
    
    def _get_system_confidence(self, session_id: str) -> float:
        """获取系统综合置信度。"""
        # 基于 PCR 输出和 FusionEngine 结果计算
        return 0.5  # 占位
```

---

## 7. 与 Topic Tree 的集成

### 7.1 主题继承

```python
class ContextTopicIntegrator:
    """Context Manager 与 Topic Tree 的集成器。"""
    
    def __init__(self, context_manager: ContextManager, topic_tree_ops: TopicTreeOperations):
        self._ctx_mgr = context_manager
        self._tree_ops = topic_tree_ops
    
    def inject_topic_context(self, session_id: str, context_package: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Topic Tree 信息注入上下文包。
        
        注入内容：
        - 活跃分支（最近 3 个主题）
        - 当前主题的关键词
        - 相关实体（当前主题下的实体列表）
        """
        active_branch = self._tree_ops.get_active_branch(session_id)
        
        if active_branch:
            context_package["topic_context"] = {
                "active_branch": [n.content for n in active_branch[-3:]],
                "current_topic": active_branch[-1].content if active_branch else None,
                "topic_entities": self._extract_topic_entities(active_branch[-1]),
            }
        
        return context_package
    
    def _extract_topic_entities(self, node: TopicTreeNode) -> List[str]:
        """从主题节点提取实体。"""
        # 从 node.content 解析（如 "scan_memory_MEMORY_ADDRESS:0x401000"）
        entities = []
        if "_" in node.content:
            parts = node.content.split("_")
            for part in parts[1:]:
                if ":" in part:
                    entity_type, entity_value = part.split(":", 1)
                    entities.append(f"{entity_type}={entity_value}")
        return entities
```

---

## 8. 与 Cognitive Tree 的集成

### 8.1 认知状态引用

```python
class ContextCognitiveIntegrator:
    """Context Manager 与 Cognitive Tree 的集成器。"""
    
    def __init__(self, context_manager: ContextManager, cognitive_tree_store: CognitiveTreeStore):
        self._ctx_mgr = context_manager
        self._cog_store = cognitive_tree_store
    
    def inject_cognitive_context(self, session_id: str, context_package: Dict[str, Any], llm_name: str) -> Dict[str, Any]:
        """
        将 Cognitive Tree 信息注入上下文包。
        
        不同 LLM 注入不同内容：
        - Planning-LLM: 最近 DECISION 节点（已执行的计划）
        - Meta-Cognitive-LLM: 最近 HYPOTHESIS + REASONING 节点（待验证的推理）
        - Answer-LLM: 全部活跃分支（推理链 + 决策 + 反思）
        """
        tree = self._cog_store.load_tree(session_id)
        
        if llm_name == "Planning-LLM":
            decision_nodes = tree.find_by_type(CogType.DECISION)[-3:]
            context_package["cognitive_context"] = {
                "recent_decisions": [n.content for n in decision_nodes],
            }
        
        elif llm_name == "Meta-Cognitive-LLM":
            hypothesis_nodes = tree.find_by_type(CogType.HYPOTHESIS)[-5:]
            reasoning_nodes = tree.find_by_type(CogType.REASONING)[-5:]
            context_package["cognitive_context"] = {
                "recent_hypotheses": [n.content for n in hypothesis_nodes],
                "recent_reasoning": [n.content for n in reasoning_nodes],
                "validation_required": [n.node_id for n in hypothesis_nodes if n.status == CogNodeStatus.CREATED],
            }
        
        elif llm_name == "Answer-LLM":
            active_branch = tree.find_active_branch()
            context_package["cognitive_context"] = {
                "active_reasoning_chain": [n.content for n in active_branch[-5:]],
                "system_confidence": self._compute_average_confidence(active_branch),
                "recent_reflections": [n.content for n in tree.find_by_type(CogType.REFLECTION)[-3:]],
            }
        
        return context_package
    
    def _compute_average_confidence(self, nodes: List[CognitiveTreeNode]) -> float:
        """计算活跃分支的平均置信度。"""
        if not nodes:
            return 0.0
        return sum(n.confidence for n in nodes) / len(nodes)
```

---

## 9. 与 Answer-LLM 的集成

### 9.1 `AnswerContextAssembler`

```python
class AnswerContextAssembler:
    """Answer-LLM 专用上下文组装器 — 读取所有层。"""
    
    def __init__(self, context_manager: ContextManager):
        self._ctx_mgr = context_manager
    
    def build_answer_context(self, session_id: str) -> str:
        """
        为 Answer-LLM 构建综合上下文字符串（Prompt 的一部分）。
        
        结构：
        1. 系统指令（固定模板）
        2. 当前主题（Topic Tree）
        3. 认知状态（Cognitive Tree）
        4. 对话历史（Context Window，分层）
        5. 约束声明（诚实度、长度限制）
        """
        parts = []
        
        # 1. 系统指令
        parts.append("## 系统指令\n你是 DialogMesh 助手，请基于以下上下文回复用户。")
        
        # 2. 当前主题
        parts.append("## 当前主题\n" + self._get_topic_summary(session_id))
        
        # 3. 认知状态
        parts.append("## 认知状态\n" + self._get_cognitive_summary(session_id))
        
        # 4. 对话历史（分层）
        parts.append("## 对话历史")
        parts.append(self._format_hot_layer(session_id))
        parts.append(self._format_warm_layer(session_id))
        parts.append(self._format_cool_layer(session_id))
        parts.append(self._format_cold_index(session_id))
        
        # 5. 约束声明
        confidence = self._get_system_confidence(session_id)
        if confidence < 0.7:
            parts.append("⚠️ 系统置信度低于 0.7，请在回复中声明不确定性。")
        
        return "\n\n".join(parts)
    
    def _format_hot_layer(self, session_id: str) -> str:
        """格式化 Hot Layer（完整记录）。"""
        hot = self._ctx_mgr.get_hot_layer(session_id)
        lines = ["### 最近对话（完整）"]
        for record in hot:
            lines.append(f"用户: {record.user_input}")
            lines.append(f"系统: {record.response}")
            lines.append(f"意图: {record.intent.category.value}")
            lines.append("")
        return "\n".join(lines)
    
    def _format_warm_layer(self, session_id: str) -> str:
        """格式化 Warm Layer（摘要）。"""
        warm = self._ctx_mgr.get_warm_layer(session_id)
        if not warm:
            return ""
        lines = ["### 近期对话摘要"]
        for summary in warm[-5:]:  # 最近 5 个摘要
            lines.append(f"- 轮次 {summary.turn_id}: {summary.category}，实体: {summary.key_entities}")
        return "\n".join(lines)
    
    def _format_cool_layer(self, session_id: str) -> str:
        """格式化 Cool Layer（合并摘要）。"""
        cool = self._ctx_mgr.get_cool_layer(session_id)
        if not cool:
            return ""
        lines = ["### 历史话题摘要"]
        for summary in cool[-3:]:  # 最近 3 个话题
            lines.append(f"- {summary.summary_text}")
            lines.append(f"  关键决策: {summary.key_decisions}")
        return "\n".join(lines)
    
    def _format_cold_index(self, session_id: str) -> str:
        """格式化 Cold Layer（索引）。"""
        cold = self._ctx_mgr.get_cold_index(session_id)
        if not cold:
            return ""
        lines = ["### 历史话题索引"]
        for entry in cold[-3:]:  # 最近 3 个索引
            lines.append(f"- {entry.topic_tag}")
        return "\n".join(lines)
```

---

## 10. Token 预算管理

### 10.1 `TokenBudgetManager`

```python
class TokenBudgetManager:
    """Token 预算管理器 — 动态分配 LLM 的 Token 预算。"""
    
    def __init__(self, base_budget: int = 8000):
        self._base = base_budget
        self._spent = 0
        self._allocated: Dict[str, int] = {}  # LLM 名称 -> 已分配
    
    @property
    def remaining(self) -> int:
        return self._base - self._spent
    
    def allocate(self, llm_name: str, min_tokens: int, max_tokens: int) -> int:
        """
        为指定 LLM 分配 Token 预算。
        
        分配策略：
        - 如果剩余预算 > max_tokens → 分配 max_tokens
        - 如果剩余预算 < min_tokens → 分配 0（标记为预算不足）
        - 否则 → 分配剩余预算的 80%（留 20% 给后续 LLM）
        """
        remaining = self.remaining
        
        if remaining < min_tokens:
            return 0  # 预算不足
        
        allocated = min(max_tokens, remaining * 0.8)
        self._spent += allocated
        self._allocated[llm_name] = allocated
        return int(allocated)
    
    def update_spent(self, turn_record: TurnRecord) -> None:
        """根据实际使用更新已消耗预算。"""
        # 估算：输入长度 + 输出长度
        input_tokens = len(turn_record.user_input) // 4  # 粗略估算：1 token ≈ 4 字符
        output_tokens = len(turn_record.response) // 4
        self._spent += input_tokens + output_tokens
    
    def reset(self) -> None:
        """重置预算（新会话开始时）。"""
        self._spent = 0
        self._allocated = {}
    
    def get_allocation_report(self) -> Dict[str, Any]:
        """获取预算分配报告。"""
        return {
            "base_budget": self._base,
            "spent": self._spent,
            "remaining": self.remaining,
            "utilization_rate": self._spent / self._base if self._base > 0 else 0,
            "allocated_by_llm": self._allocated,
        }
```

### 10.2 压缩策略

```python
class ContextCompressor:
    """上下文压缩器 — Warm→Cool→Cold 的压缩。"""
    
    def compress_turn(self, turn: TurnRecord) -> TurnSummary:
        """
        将 TurnRecord 压缩为 TurnSummary。
        
        规则模板压缩：
        - 保留：意图类别、关键实体、结果状态
        - 丢弃：完整用户输入、完整系统回复、中间推理
        """
        return TurnSummary(
            turn_id=turn.turn_id,
            category=turn.intent.category.value,
            key_entities=[{"type": e.type.value, "value": str(e.value)} for e in turn.intent.entities[:3]],
            result_status="success" if turn.response else "clarification",
            timestamp=turn.timestamp,
        )
    
    def merge_turns(self, summaries: List[TurnSummary]) -> TopicSummary:
        """
        将多个 TurnSummary 合并为 TopicSummary。
        
        规则模板合并：
        - 提取共同主题（意图类别）
        - 合并关键实体（去重）
        - 提取关键决策（成功/失败）
        - 提取未解决问题（clarification）
        """
        topic_id = f"topic-{summaries[0].turn_id}-{summaries[-1].turn_id}"
        
        # 提取共同主题
        categories = [s.category for s in summaries]
        main_category = max(set(categories), key=categories.count)
        
        # 合并实体
        all_entities = []
        for s in summaries:
            all_entities.extend(s.key_entities)
        unique_entities = list({json.dumps(e) for e in all_entities})
        
        # 提取决策
        decisions = [f"轮次 {s.turn_id}: {s.category} → {s.result_status}" for s in summaries]
        
        # 未解决问题
        unresolved = [f"轮次 {s.turn_id}: 需要澄清" for s in summaries if s.result_status == "clarification"]
        
        return TopicSummary(
            topic_id=topic_id,
            summary_text=f"主题：{main_category}，涉及 {len(unique_entities)} 个实体，{len(summaries)} 轮对话",
            key_decisions=decisions,
            unresolved_issues=unresolved,
            user_preferences=[],
            start_turn=summaries[0].turn_id,
            end_turn=summaries[-1].turn_id,
        )
    
    def compress_to_index(self, topic: TopicSummary) -> ColdIndexEntry:
        """将 TopicSummary 压缩为 ColdIndexEntry。"""
        return ColdIndexEntry(
            topic_id=topic.topic_id,
            topic_tag=topic.summary_text[:50],
            key_decisions=topic.key_decisions[:3],  # 仅保留前 3 个决策
            user_preference_updates=topic.user_preferences[:3],
        )
```

---

## 11. 测试策略

### 11.1 测试目标

| 测试类型 | 覆盖率 | 关键验证点 |
|---------|--------|----------|
| 单元测试 | 100% | 分层管理（Hot→Warm→Cool→Cold）的独立测试 |
| 集成测试 | 90% | 上下文组装（6 个 LLM 实例）的端到端测试 |
| 压缩测试 | 100% | TurnRecord→TurnSummary→TopicSummary→ColdIndexEntry 的压缩链 |
| Token 预算测试 | 100% | 动态分配、超额分配、预算不足场景 |
| 回热测试 | 100% | Cold→Cool 回热的正确性和完整性 |

### 11.2 关键测试用例

**用例 1：分层降级链**
```python
def test_tiered_demotion_chain():
    mgr = ContextManager(mock_session_manager, ContextManagerConfig())
    
    # 模拟 15 轮对话
    for i in range(15):
        turn = TurnRecord(
            turn_id=i,
            user_input=f"test input {i}",
            intent=Intent(category=IntentCategory.SCAN_MEMORY),
            response=f"response {i}",
            timestamp=time.time(),
        )
        mgr.update("sess-1", turn)
    
    # 验证分层
    hot = mgr.get_hot_layer("sess-1")
    warm = mgr.get_warm_layer("sess-1")
    cool = mgr.get_cool_layer("sess-1")
    
    assert len(hot) <= 3  # Hot 容量
    assert len(warm) <= 7  # Warm 容量
    assert len(cool) <= 20  # Cool 容量
```

**用例 2：Token 预算分配**
```python
def test_token_budget_allocation():
    budget = TokenBudgetManager(base_budget=1000)
    
    # 分配 PCR-LLM
    pcr_tokens = budget.allocate("PCR-LLM", min_tokens=100, max_tokens=500)
    assert 0 < pcr_tokens <= 500
    
    # 分配 Intent-LLM
    intent_tokens = budget.allocate("Intent-LLM", min_tokens=200, max_tokens=800)
    assert 0 < intent_tokens <= 800
    
    # 验证总分配不超过预算
    assert budget._spent <= 1000
```

**用例 3：上下文组装（Answer-LLM）**
```python
def test_assemble_for_answer():
    assembler = ContextAssembler(mock_context_manager, ContextManagerConfig())
    
    ctx = assembler.assemble("sess-1", "Answer-LLM")
    
    assert "hot_layer" in ctx
    assert "warm_layer" in ctx
    assert "cool_layer" in ctx
    assert "cold_index" in ctx
    assert "topic_tree_branch" in ctx
    assert "cognitive_tree_branch" in ctx
```

---

## 12. 附录：简化与待讨论项

### 12.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | LLM 驱动压缩 | Cool Layer 的二级摘要使用 LLM 生成 | 使用规则模板（提取关键词拼接） | LLM 压缩成本高，初期使用规则降低延迟 | Phase 2 引入轻量摘要 LLM（3B 参数）时实现 |
| **S-02** | Token 精确计数 | 基于 tokenizer 的精确 Token 计数 | 使用字符数/4 的粗略估算 | 精确计数需要 tiktoken 等库，增加依赖 | Phase 2 引入精确计数时实现 |
| **S-03** | 跨会话上下文共享 | 相似会话的上下文共享（全局缓存） | 仅会话级上下文 | 跨会话共享需要全局索引和隐私控制 | Phase 3 引入全局上下文缓存时实现 |
| **S-04** | 自适应压缩率 | 基于 LLM 反馈动态调整压缩率 | 固定压缩率（Warm 每 3 个合并） | 自适应压缩需要评估压缩质量，增加复杂度 | Phase 2 引入压缩质量评估时实现 |
| **S-05** | 语义回热 | 基于语义相似度从 Cold 层回热 | 仅基于 topic_id 精确匹配回热 | 语义回热需要 embedding 计算，增加延迟 | Phase 2 引入 embedding 层时实现 |

### 12.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | Hot Layer 容量 | A) 固定 3 轮  B) 基于 PCR 复杂度动态调整（复杂任务保留更多轮次）  C) 基于用户偏好调整 | 建议 B：复杂任务（如多步骤分析）需要更多上下文 |
| **D-02** | Warm 合并批次 | A) 固定 3 个合并为 1 个  B) 基于主题相似度动态合并  C) 基于 Token 预算动态调整 | 建议 A：固定批次简单可靠，动态合并增加复杂度 |
| **D-03** | Token 预算分配策略 | A) 固定比例（PCR:10%, Intent:20%, Planning:30%, Answer:40%）  B) 基于任务复杂度动态分配  C) 基于历史使用率自适应 | 建议 B：复杂任务分配更多预算给 Planning-LLM |
| **D-04** | 冷层归档保留期 | A) 固定 30 天  B) 基于主题重要性（活跃主题保留更久）  C) 基于用户画像（重要用户保留更久） | 建议 B：活跃主题保留 90 天，冷门主题 7 天 |
| **D-05** | 上下文注入格式 | A) 纯文本（当前）  B) 结构化 JSON（便于 LLM 解析）  C) 混合（文本 + 结构化标记） | 建议 C：文本便于人类阅读，结构化标记便于 LLM 提取关键信息 |

### 12.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_FULL_CONCEPT.md` §5.3 | §5 | ✅ 等价 | 4 层工作记忆（Hot/Warm/Cool/Cold）覆盖 |
| `DESIGN_FULL_CONCEPT.md` §5.3 | §6 | ✅ 等价 | 上下文组装器（6 个 LLM 实例）覆盖 |
| `DESIGN_FULL_CONCEPT.md` §5.3 | §10 | ✅ 等价 | Token 预算管理覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §8 | ✅ 等价 | Cognitive Tree 认知状态引用覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §5 | §9 | ✅ 等价 | Answer-LLM 穿透层上下文组装覆盖 |
| `ENGINEERING_DATA_MODEL.md` §7.3 | §5 | ✅ 等价 | ContextWindow / TurnRecord / TurnSummary / TopicSummary / ColdIndexEntry 数据模型对齐 |
| `ENGINEERING_PERSISTENCE.md` §6-§8 | §5 | ✅ 等价 | Hot/Warm/Cold 层持久化对齐 |

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档和已有数据模型/持久化定义生成。数据模型和持久化层已在 `ENGINEERING_DATA_MODEL.md` 和 `ENGINEERING_PERSISTENCE.md` 中实现，本文档新增约 **750 行代码**（ContextManager + ContextAssembler + ContextCompressor + TokenBudgetManager）。所有简化项已在 §12.1 中诚实标记，待讨论项在 §12.2 中列出，等待团队确认。*
