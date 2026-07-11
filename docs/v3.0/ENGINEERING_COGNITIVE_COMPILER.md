# DialogMesh 认知编译器 — 工程实现文档

> **文档编号**: ENGINEERING-COGNITIVE-COMPILER-009  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 工程待实现（数据模型已定义）  
> **对应设计文档**: `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2（Cognitive Tree）+ `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.2（访问控制）  
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`（认知双工架构）  
> **对应数据模型**: `ENGINEERING_DATA_MODEL.md` §12（CognitiveTreeNode / CognitiveTree / AccessControlMatrix）  
> **对应持久化**: `ENGINEERING_PERSISTENCE.md` §12（Cognitive Tree 存储）  
> **原则**: Cognitive Tree 是 LLM 的共享心智空间，认知编译器是信息进入该空间的唯一入口。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览](#4-架构总览)
- [5. 认知编译器核心](#5-认知编译器核心)
- [6. 节点生命周期管理](#6-节点生命周期管理)
- [7. 边关系管理](#7-边关系管理)
- [8. 访问控制矩阵](#8-访问控制矩阵)
- [9. 事件总线](#9-事件总线)
- [10. 查询与遍历](#10-查询与遍历)
- [11. 与 6 个 LLM 实例的集成](#11-与-6-个-llm-实例的集成)
- [12. 测试策略](#12-测试策略)
- [13. 附录：简化与待讨论项](#13-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh **Cognitive Compiler（认知编译器）**的完整实现规范。认知编译器是 v3.0 多层 LLM 认知架构的**核心枢纽**，负责将 6 个 LLM 实例的推理结果编译为 Cognitive Tree 节点，管理节点生命周期、边关系、访问控制和事件通知。

### 1.2 范围

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| 节点编译 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §5 | 将 LLM 输出编译为 CognitiveTreeNode |
| 生命周期管理 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §6 | 创建 → 验证 → 采纳 → 归档 |
| 边关系管理 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §7 | DERIVES/SUPPORTS/CONTRADICTS/... |
| 访问控制 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.2 | §8 | 6 个 LLM 实例的权限矩阵 |
| 事件总线 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.3 | §9 | 异步事件通知 |
| 查询与遍历 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §10 | 按类型/LLM/状态查询，DFS/BFS |
| 与 LLM 实例集成 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3 | §11 | 6 个 LLM 实例的读写模式 |

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/cognitive_compiler/compiler.py` | 认知编译器主类 | ~300 行 | 新增 |
| `core/agent/cognitive_compiler/lifecycle.py` | 节点生命周期管理器 | ~150 行 | 新增 |
| `core/agent/cognitive_compiler/edge_manager.py` | 边关系管理器 | ~150 行 | 新增 |
| `core/agent/cognitive_compiler/access_control.py` | 访问控制矩阵 | ~100 行 | 新增 |
| `core/agent/cognitive_compiler/event_bus.py` | 事件总线 | ~150 行 | 新增 |
| `core/agent/cognitive_compiler/querier.py` | 查询与遍历引擎 | ~150 行 | 新增 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/cognitive_tree/tree.py` | 集成编译器作为唯一写入口 | 树操作 |
| `core/agent/cognitive_tree/store.py` | 支持事务性写入 | 存储层 |
| `core/agent/orchestrator.py` | 每轮调用 `CognitiveCompiler.compile()` | 编排层 |

---

## 3. 现有实现评估

### 3.1 数据模型（已定义）

**定义位置**: `ENGINEERING_DATA_MODEL.md` §12

| 模型 | 字段 | 说明 | 状态 |
|------|------|------|------|
| `CognitiveTreeNode` | `node_id`, `cog_type`, `source_llm`, `timestamp`, `content`, `confidence`, `evidence`, `action`, `action_result`, `status`, `reflections`, `validations`, `version_history`, `cross_refs`, `metadata`, `topic_refs` | 认知节点 | ✅ 已定义 |
| `CognitiveTree` | `session_id`, `nodes`, `edges`, `_by_type`, `_by_llm`, `_by_status`, `root`, `active_branch`, `stale_branches`, `depth_limit` | 认知树 | ✅ 已定义 |
| `CognitiveTreeEdge` | `edge_id`, `source_id`, `target_id`, `edge_type`, `weight`, `condition`, `metadata` | 认知边 | ✅ 已定义 |
| `AccessControlMatrix` | `permissions` | 权限矩阵 | ✅ 已定义 |

### 3.2 持久化（已定义）

**定义位置**: `ENGINEERING_PERSISTENCE.md` §12

| 功能 | 状态 | 备注 |
|------|------|------|
| `cognitive_nodes` 表 | ✅ 已定义 | SQLite |
| `cognitive_edges` 表 | ✅ 已定义 | SQLite |
| `CognitiveTreeStore` | ✅ 已定义 | 权限检查 + 版本历史 |
| 事务性写入 | ⚠️ 已定义 | `pending_writes` + `flush()` |

### 3.3 差距分析

| 设计文档需求 | 现有实现 | 差距 | 优先级 |
|------------|---------|------|--------|
| 认知编译器（统一入口） | 无 | 需新增 `CognitiveCompiler` | P1 |
| 节点生命周期管理 | 无 | 需新增 `NodeLifecycleManager` | P1 |
| 边关系管理 | 无 | 需新增 `EdgeManager` | P1 |
| 访问控制矩阵（运行时检查） | 数据模型已定义 | 需实现运行时检查逻辑 | P1 |
| 事件总线（异步通知） | 无 | 需新增 `EventBus` | P1 |
| 查询与遍历引擎 | 数据模型已定义方法 | 需实现高效查询 | P2 |
| 与 6 个 LLM 实例的集成 | 无 | 需定义每个 LLM 的读写模式 | P1 |

---

## 4. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         6 个 LLM 实例                                        │
│  PCR-LLM / Intent-LLM / Planning-LLM / Meta-Cognitive-LLM / Reflective-LLM / Answer-LLM │
│                              ↓ 推理输出                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  认知编译器（CognitiveCompiler）                                              │
│  ═══════════════════════════════════════════════════════════════════  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐            │
│  │ compile()        │  │ NodeLifecycle    │  │ EdgeManager      │            │
│  │ 统一编译入口     │  │ 生命周期管理     │  │ 边关系管理       │            │
│  │ 权限检查         │  │ 创建→验证→采纳  │  │ DERIVES/SUPPORTS │            │
│  │ 事件触发         │  │ →归档→版本       │  │ /CONTRADICTS/... │            │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐            │
│  │ AccessControl    │  │ EventBus         │  │ Querier          │            │
│  │ 访问控制矩阵     │  │ 异步事件通知     │  │ 查询与遍历       │            │
│  │ 6 个 LLM 权限    │  │ 订阅/发布/过滤   │  │ 按类型/LLM/状态  │            │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘            │
├─────────────────────────────────────────────────────────────────────────────┤
│  Cognitive Tree（数据模型已定义）                                              │
│  ────────────────────────────────────────────────────────────────────────  │
│  ┌──────────────────────┐  ┌──────────────────────────────┐                 │
│  │ 节点（nodes）          │  │ 边（edges）                    │                 │
│  │  PERCEPTION/HYPOTHESIS │  │  DERIVES/SUPPORTS/CONTRADICTS  │                 │
│  │  REASONING/DECISION  │  │  CONDITIONAL/ALTERNATIVE/...   │                 │
│  │  ACTION/OBSERVATION  │  │                                │                 │
│  │  REFLECTION/VALIDATION│  │                                │                 │
│  │  LEARNING/COMMUNICATION│  │                                │                 │
│  └──────────────────────┘  └──────────────────────────────┘                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  持久化层（SQLite + 内存索引）                                                  │
│  ────────────────────────────────────────────────────────────────────────  │
│  cognitive_nodes | cognitive_edges | schema_version                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 认知编译器核心

### 5.1 `CognitiveCompiler`

```python
class CognitiveCompiler:
    """认知编译器 — 6 个 LLM 实例的推理结果进入 Cognitive Tree 的唯一入口。"""
    
    def __init__(
        self,
        cognitive_tree_store: CognitiveTreeStore,
        access_control: AccessControlMatrix,
        event_bus: EventBus,
        lifecycle_manager: NodeLifecycleManager,
        edge_manager: EdgeManager,
    ):
        self._store = cognitive_tree_store
        self._access = access_control
        self._event_bus = event_bus
        self._lifecycle = lifecycle_manager
        self._edge_mgr = edge_manager
    
    def compile(
        self,
        session_id: str,
        llm_name: str,
        cog_type: CogType,
        content: str,
        confidence: float = 0.5,
        evidence: List[str] = None,
        action: Optional[str] = None,
        action_result: Optional[str] = None,
        parent_node_id: Optional[str] = None,
        edge_type: CogEdgeType = CogEdgeType.DERIVES,
    ) -> Optional[CognitiveTreeNode]:
        """
        将 LLM 推理结果编译为 Cognitive Tree 节点。
        
        这是 6 个 LLM 实例将信息写入 Cognitive Tree 的唯一入口。
        
        流程：
        1. 权限检查：llm_name 是否可以创建 cog_type 类型的节点？
        2. 创建节点
        3. 如果有 parent_node_id，创建边关系
        4. 触发事件（NODE_CREATED）
        5. 返回节点
        """
        # 1. 权限检查
        if not self._access.check_create(llm_name, cog_type):
            raise PermissionError(
                f"LLM '{llm_name}' cannot create {cog_type.value} nodes. "
                f"Allowed types: {self._access.get_allowed_types(llm_name)}"
            )
        
        # 2. 创建节点
        node = CognitiveTreeNode(
            cog_type=cog_type,
            source_llm=llm_name,
            content=content,
            confidence=confidence,
            evidence=evidence or [],
            action=action,
            action_result=action_result,
        )
        
        # 3. 保存到存储（带权限检查）
        self._store.save_node(session_id, node, requesting_llm=llm_name)
        
        # 4. 创建边关系（如果有父节点）
        if parent_node_id:
            self._edge_mgr.create_edge(
                session_id=session_id,
                source_id=parent_node_id,
                target_id=node.node_id,
                edge_type=edge_type,
                requesting_llm=llm_name,
            )
        
        # 5. 触发事件
        self._event_bus.publish(Event(
            type=EventType.NODE_CREATED,
            data={
                "session_id": session_id,
                "node_id": node.node_id,
                "cog_type": cog_type.value,
                "source_llm": llm_name,
                "confidence": confidence,
            },
        ))
        
        return node
    
    def compile_batch(
        self,
        session_id: str,
        llm_name: str,
        nodes_data: List[Dict[str, Any]],
    ) -> List[CognitiveTreeNode]:
        """批量编译（用于 Reflective-LLM 的批量复盘）。"""
        results = []
        for data in nodes_data:
            try:
                node = self.compile(
                    session_id=session_id,
                    llm_name=llm_name,
                    cog_type=data["cog_type"],
                    content=data["content"],
                    confidence=data.get("confidence", 0.5),
                    evidence=data.get("evidence"),
                    action=data.get("action"),
                    parent_node_id=data.get("parent_node_id"),
                    edge_type=data.get("edge_type", CogEdgeType.DERIVES),
                )
                results.append(node)
            except PermissionError:
                continue  # 跳过无权限的节点
        return results
```

---

## 6. 节点生命周期管理

### 6.1 `NodeLifecycleManager`

```python
class NodeLifecycleManager:
    """节点生命周期管理器 — 管理 CognitiveTreeNode 的完整生命周期。"""
    
    def __init__(self, cognitive_tree_store: CognitiveTreeStore):
        self._store = cognitive_tree_store
    
    # ── 生命周期状态机 ──
    # CREATED → ACTIVE → VALIDATED / INVALIDATED → SUPERSEDED / ARCHIVED
    
    def activate(self, session_id: str, node_id: str, requesting_llm: str) -> bool:
        """
        将节点从 CREATED 激活为 ACTIVE。
        
        触发条件：
        - Planning-LLM 采纳了某个推理作为执行计划
        - Answer-LLM 确认某个假设作为回复依据
        """
        return self._transition(
            session_id, node_id, requesting_llm,
            from_status=CogNodeStatus.CREATED,
            to_status=CogNodeStatus.ACTIVE,
        )
    
    def validate(self, session_id: str, node_id: str, requesting_llm: str, validation_result: str) -> bool:
        """
        验证节点（Meta-Cognitive-LLM 调用）。
        
        结果：
        - 验证通过 → VALIDATED
        - 验证失败 → INVALIDATED
        """
        node = self._store.load_node(session_id, node_id)
        if not node:
            return False
        
        # 添加验证记录
        node.validations.append(validation_result)
        
        # 判断验证结果
        if "PASS" in validation_result or "VALID" in validation_result:
            new_status = CogNodeStatus.VALIDATED
        else:
            new_status = CogNodeStatus.INVALIDATED
        
        return self._transition(
            session_id, node_id, requesting_llm,
            from_status=node.status,
            to_status=new_status,
        )
    
    def supersede(self, session_id: str, node_id: str, requesting_llm: str, new_node_id: str) -> bool:
        """
        将节点标记为 SUPERSEDED（被新版本替代）。
        
        触发条件：
        - 同一 LLM 产生了新的、更准确的推理
        - Meta-Cognitive-LLM 发现旧版本存在错误
        """
        # 创建新版本边
        self._store.add_edge(session_id, CognitiveTreeEdge(
            source_id=node_id,
            target_id=new_node_id,
            edge_type=CogEdgeType.REFINES,
        ))
        
        return self._transition(
            session_id, node_id, requesting_llm,
            from_status=CogNodeStatus.ACTIVE,
            to_status=CogNodeStatus.SUPERSEDED,
        )
    
    def archive(self, session_id: str, node_id: str, requesting_llm: str) -> bool:
        """
        将节点归档（Reflective-LLM 调用）。
        
        触发条件：
        - 节点超过保留期（如 30 天）
        -  Reflective-LLM 的定期清理任务
        """
        return self._transition(
            session_id, node_id, requesting_llm,
            from_status=CogNodeStatus.VALIDATED,
            to_status=CogNodeStatus.ARCHIVED,
        )
    
    def _transition(
        self,
        session_id: str,
        node_id: str,
        requesting_llm: str,
        from_status: CogNodeStatus,
        to_status: CogNodeStatus,
    ) -> bool:
        """状态转换的通用方法。"""
        node = self._store.load_node(session_id, node_id)
        if not node:
            return False
        
        # 检查当前状态是否匹配
        if node.status != from_status:
            return False
        
        # 检查权限
        if not self._store._access.check_update(requesting_llm, node_id, node.source_llm):
            raise PermissionError(
                f"LLM '{requesting_llm}' cannot update node '{node_id}' (owned by {node.source_llm})"
            )
        
        # 执行状态转换
        node.status = to_status
        node.version_history.append(json.dumps({
            "time": time.time(),
            "from": from_status.value,
            "to": to_status.value,
            "by": requesting_llm,
        }))
        
        self._store.update_node(session_id, node_id, {"status": to_status}, requesting_llm)
        return True
```

---

## 7. 边关系管理

### 7.1 `EdgeManager`

```python
class EdgeManager:
    """边关系管理器 — 管理 Cognitive Tree 节点间的推理关系。"""
    
    def __init__(self, cognitive_tree_store: CognitiveTreeStore):
        self._store = cognitive_tree_store
    
    def create_edge(
        self,
        session_id: str,
        source_id: str,
        target_id: str,
        edge_type: CogEdgeType,
        weight: float = 1.0,
        condition: Optional[str] = None,
        requesting_llm: str = "",
    ) -> bool:
        """
        创建认知边。
        
        权限检查：
        - 某些 LLM 不能创建某些边类型（如 Planning-LLM 不能创建 CONTRADICTS 边）
        """
        # 检查边类型权限
        if not self._check_edge_type_permission(requesting_llm, edge_type):
            raise PermissionError(
                f"LLM '{requesting_llm}' cannot create {edge_type.value} edges"
            )
        
        edge = CognitiveTreeEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            condition=condition,
        )
        
        self._store.save_edge(session_id, edge)
        return True
    
    def find_contradictions(self, session_id: str, node_id: str) -> List[CognitiveTreeEdge]:
        """查找与某节点矛盾的所有边。"""
        all_edges = self._store.load_edges(session_id)
        contradictions = [
            e for e in all_edges
            if (e.source_id == node_id or e.target_id == node_id)
            and e.edge_type == CogEdgeType.CONTRADICTS
        ]
        return contradictions
    
    def find_supports(self, session_id: str, node_id: str) -> List[CognitiveTreeEdge]:
        """查找支持某节点的所有边。"""
        all_edges = self._store.load_edges(session_id)
        supports = [
            e for e in all_edges
            if e.target_id == node_id and e.edge_type == CogEdgeType.SUPPORTS
        ]
        return supports
    
    def find_derived_chain(self, session_id: str, start_node_id: str) -> List[str]:
        """查找从起始节点出发的推导链（DERIVES 边）。"""
        chain = [start_node_id]
        current = start_node_id
        
        for _ in range(10):  # 深度限制
            edges = self._store.load_edges_from(session_id, current)
            derive_edges = [e for e in edges if e.edge_type == CogEdgeType.DERIVES]
            if not derive_edges:
                break
            # 取权重最高的推导
            best = max(derive_edges, key=lambda e: e.weight)
            chain.append(best.target_id)
            current = best.target_id
        
        return chain
    
    def _check_edge_type_permission(self, llm_name: str, edge_type: CogEdgeType) -> bool:
        """检查 LLM 是否有权限创建某类型的边。"""
        # 默认权限：所有 LLM 可以创建 DERIVES 和 SUPPORTS
        # Meta-Cognitive-LLM 可以创建所有类型（包括 CONTRADICTS）
        # Reflective-LLM 只能创建 SUMMARIZES 和 CROSS_REF
        
        restricted_edges = {
            "PCR-LLM": {CogEdgeType.CONTRADICTS, CogEdgeType.CONDITIONAL},
            "Intent-LLM": {CogEdgeType.CONTRADICTS},
            "Planning-LLM": {CogEdgeType.CONTRADICTS, CogEdgeType.VALIDATION},
            "Meta-Cognitive-LLM": set(),  # 无限制
            "Reflective-LLM": {CogEdgeType.DERIVES, CogEdgeType.SUPPORTS, CogEdgeType.CONTRADICTS, CogEdgeType.CONDITIONAL},
            "Answer-LLM": {CogEdgeType.CONTRADICTS, CogEdgeType.VALIDATION},
        }
        
        forbidden = restricted_edges.get(llm_name, set())
        return edge_type not in forbidden
```

---

## 8. 访问控制矩阵

### 8.1 `AccessControlMatrix`（运行时实现）

```python
class AccessControlMatrix:
    """LLM 实例对 Cognitive Tree 的访问权限矩阵 — 运行时实现。"""
    
    # 默认权限配置（设计文档 §6.2）
    DEFAULT_PERMISSIONS = {
        "PCR-LLM": {
            "can_create": {CogType.PERCEPTION, CogType.HYPOTHESIS},
            "can_read": "all",
            "can_update": "own",
            "can_delete": "none",
        },
        "Intent-LLM": {
            "can_create": {CogType.HYPOTHESIS, CogType.REASONING},
            "can_read": "all",
            "can_update": "own",
            "can_delete": "none",
        },
        "Planning-LLM": {
            "can_create": {CogType.REASONING, CogType.DECISION, CogType.ALTERNATIVE},
            "can_read": "all",
            "can_update": "own",
            "can_delete": "none",
        },
        "Meta-Cognitive-LLM": {
            "can_create": {CogType.VALIDATION, CogType.REFLECTION},
            "can_read": "all",
            "can_update": "all",  # 可以修改任何节点的 status
            "can_delete": "none",
        },
        "Reflective-LLM": {
            "can_create": {CogType.LEARNING, CogType.REFLECTION},
            "can_read": "all",
            "can_update": "none",
            "can_delete": "none",
        },
        "Answer-LLM": {
            "can_create": {CogType.HYPOTHESIS},
            "can_read": "all",
            "can_update": "own",
            "can_delete": "none",
        },
    }
    
    def __init__(self, permissions: Optional[Dict] = None):
        self._permissions = permissions or self.DEFAULT_PERMISSIONS
    
    def check_create(self, llm_name: str, cog_type: CogType) -> bool:
        """检查 LLM 是否可以创建某类型的节点。"""
        perms = self._permissions.get(llm_name, {})
        allowed = perms.get("can_create", set())
        return cog_type in allowed
    
    def check_read(self, llm_name: str, node_id: str) -> bool:
        """检查 LLM 是否可以读取某节点。"""
        perms = self._permissions.get(llm_name, {})
        return perms.get("can_read", "none") == "all"
    
    def check_update(self, llm_name: str, node_id: str, node_owner: str) -> bool:
        """检查 LLM 是否可以修改某节点。"""
        perms = self._permissions.get(llm_name, {})
        update_perm = perms.get("can_update", "none")
        
        if update_perm == "all":
            return True
        elif update_perm == "own":
            return llm_name == node_owner
        else:
            return False
    
    def check_delete(self, llm_name: str, node_id: str) -> bool:
        """检查 LLM 是否可以删除某节点。"""
        perms = self._permissions.get(llm_name, {})
        return perms.get("can_delete", "none") != "none"
    
    def get_allowed_types(self, llm_name: str) -> Set[str]:
        """获取某 LLM 可以创建的节点类型列表。"""
        perms = self._permissions.get(llm_name, {})
        allowed = perms.get("can_create", set())
        return {t.value for t in allowed}
```

---

## 9. 事件总线

### 9.1 `EventBus`

```python
class EventBus:
    """Cognitive Tree 的异步事件通知系统。"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Subscription]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
    
    def start(self):
        """启动后台事件处理任务。"""
        self._running = True
        self._worker_task = asyncio.create_task(self._process_loop())
    
    def stop(self):
        """停止事件处理。"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
    
    def subscribe(
        self,
        event_type: str,
        filter: Dict[str, Any],
        callback: Callable[[Event], None],
    ) -> str:
        """
        订阅事件。
        
        filter 示例：
        {"source_llm": "Planning-LLM", "cog_type": "DECISION"}
        """
        sub_id = str(uuid.uuid4())
        self._subscribers[event_type].append(Subscription(sub_id, filter, callback))
        return sub_id
    
    def unsubscribe(self, sub_id: str) -> bool:
        """取消订阅。"""
        for event_type, subs in self._subscribers.items():
            for i, sub in enumerate(subs):
                if sub.id == sub_id:
                    subs.pop(i)
                    return True
        return False
    
    def publish(self, event: Event):
        """发布事件到队列。"""
        self._queue.put_nowait(event)
    
    async def _process_loop(self):
        """后台事件处理循环。"""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[EventBus] Error processing event: {e}")
    
    async def _dispatch(self, event: Event):
        """分发事件到匹配的订阅者。"""
        for sub in self._subscribers.get(event.type, []):
            if self._match_filter(event, sub.filter):
                # 异步调用回调
                asyncio.create_task(self._safe_callback(sub.callback, event))
    
    async def _safe_callback(self, callback: Callable, event: Event):
        """安全调用回调（捕获异常）。"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)
        except Exception as e:
            print(f"[EventBus] Callback error: {e}")
    
    def _match_filter(self, event: Event, filter: Dict[str, Any]) -> bool:
        """检查事件是否匹配过滤条件。"""
        for key, value in filter.items():
            if event.data.get(key) != value:
                return False
        return True
```

### 9.2 事件类型

```python
class EventType(Enum):
    """Cognitive Tree 事件类型。"""
    NODE_CREATED = "node_created"
    NODE_ACTIVATED = "node_activated"
    NODE_VALIDATED = "node_validated"
    NODE_INVALIDATED = "node_invalidated"
    NODE_SUPERSEDED = "node_superseded"
    NODE_ARCHIVED = "node_archived"
    EDGE_CREATED = "edge_created"
    CONFLICT_DETECTED = "conflict_detected"
    STATUS_CHANGED = "status_changed"
    BRANCH_SWITCHED = "branch_switched"
    USER_FEEDBACK = "user_feedback"
    SESSION_ENDED = "session_ended"
```

---

## 10. 查询与遍历

### 10.1 `Querier`

```python
class Querier:
    """Cognitive Tree 查询与遍历引擎。"""
    
    def __init__(self, cognitive_tree_store: CognitiveTreeStore):
        self._store = cognitive_tree_store
    
    # ── 按属性查询 ──
    def find_by_type(self, session_id: str, cog_type: CogType) -> List[CognitiveTreeNode]:
        """按认知类型查询。"""
        nodes = self._store.load_nodes(session_id)
        return [n for n in nodes if n.cog_type == cog_type]
    
    def find_by_llm(self, session_id: str, llm_name: str) -> List[CognitiveTreeNode]:
        """按 LLM 来源查询。"""
        nodes = self._store.load_nodes(session_id)
        return [n for n in nodes if n.source_llm == llm_name]
    
    def find_by_status(self, session_id: str, status: CogNodeStatus) -> List[CognitiveTreeNode]:
        """按状态查询。"""
        nodes = self._store.load_nodes(session_id)
        return [n for n in nodes if n.status == status]
    
    def find_active(self, session_id: str) -> List[CognitiveTreeNode]:
        """查找所有 ACTIVE 节点。"""
        return self.find_by_status(session_id, CogNodeStatus.ACTIVE)
    
    # ── 遍历 ──
    def traverse_dfs(self, session_id: str, start_node_id: str) -> List[CognitiveTreeNode]:
        """深度优先遍历。"""
        visited = set()
        result = []
        stack = [start_node_id]
        
        while stack:
            node_id = stack.pop()
            if node_id in visited:
                continue
            visited.add(node_id)
            
            node = self._store.load_node(session_id, node_id)
            if node:
                result.append(node)
                # 获取出边目标节点
                edges = self._store.load_edges_from(session_id, node_id)
                for edge in edges:
                    if edge.target_id not in visited:
                        stack.append(edge.target_id)
        
        return result
    
    def traverse_bfs(self, session_id: str, start_node_id: str) -> List[CognitiveTreeNode]:
        """广度优先遍历。"""
        visited = set()
        result = []
        queue = deque([start_node_id])
        
        while queue:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            
            node = self._store.load_node(session_id, node_id)
            if node:
                result.append(node)
                edges = self._store.load_edges_from(session_id, node_id)
                for edge in edges:
                    if edge.target_id not in visited:
                        queue.append(edge.target_id)
        
        return result
    
    def find_active_branch(self, session_id: str) -> List[CognitiveTreeNode]:
        """查找当前活跃分支（从 root 到最新的 ACTIVE 节点）。"""
        # 找到最新的 ACTIVE 节点
        active_nodes = self.find_active(session_id)
        if not active_nodes:
            return []
        
        latest = max(active_nodes, key=lambda n: n.timestamp)
        
        # 回溯到 root
        branch = [latest]
        current = latest
        
        for _ in range(10):  # 深度限制
            edges = self._store.load_edges_to(session_id, current.node_id)
            parent_edges = [e for e in edges if e.edge_type in (CogEdgeType.DERIVES, CogEdgeType.SUPPORTS)]
            if not parent_edges:
                break
            best = max(parent_edges, key=lambda e: e.weight)
            parent = self._store.load_node(session_id, best.source_id)
            if parent:
                branch.insert(0, parent)
                current = parent
            else:
                break
        
        return branch
    
    def find_stale_branches(self, session_id: str, max_age_seconds: float = 3600) -> List[List[CognitiveTreeNode]]:
        """查找失效分支（超过最大年龄未更新的 ACTIVE 节点）。"""
        cutoff = time.time() - max_age_seconds
        active_nodes = self.find_active(session_id)
        
        stale = []
        for node in active_nodes:
            if node.timestamp < cutoff:
                branch = self.find_active_branch(session_id)  # 简化：找到包含该节点的分支
                stale.append(branch)
        
        return stale
```

---

## 11. 与 6 个 LLM 实例的集成

### 11.1 每个 LLM 的读写模式

| LLM 实例 | 创建节点类型 | 读取范围 | 修改权限 | 典型使用场景 |
|----------|------------|---------|---------|-------------|
| **PCR-LLM** | PERCEPTION, HYPOTHESIS | 全部 | 自己创建的 | 语义噪声分析 → 创建 PERCEPTION 节点；期望推断 → 创建 HYPOTHESIS 节点 |
| **Intent-LLM** | HYPOTHESIS, REASONING | 全部 | 自己创建的 | 深层意图理解 → 创建 HYPOTHESIS 节点；实体推断 → 创建 REASONING 节点 |
| **Planning-LLM** | REASONING, DECISION, ALTERNATIVE | 全部 | 自己创建的 | 计划生成 → 创建 DECISION 节点；备选方案 → 创建 ALTERNATIVE 节点 |
| **Meta-Cognitive-LLM** | VALIDATION, REFLECTION | 全部 | **所有节点** | 验证节点 → 创建 VALIDATION 节点；修改任何节点的 status（VALIDATED/INVALIDATED） |
| **Reflective-LLM** | LEARNING, REFLECTION | 全部 | 无（只读） | 长期复盘 → 创建 LEARNING 节点；分析偏见 → 创建 REFLECTION 节点 |
| **Answer-LLM** | HYPOTHESIS | 全部 | 自己创建的 | 回复策略 → 创建 HYPOTHESIS 节点；行动记录 → 创建 ACTION 节点 |

### 11.2 集成示例

```python
# PCR-LLM 写入示例
pcr_node = compiler.compile(
    session_id="sess-1",
    llm_name="PCR-LLM",
    cog_type=CogType.PERCEPTION,
    content="语义噪声分析：模糊度 0.3，结构不完整度 0.1",
    confidence=0.85,
)

# Intent-LLM 读取 PCR-LLM 的节点作为父节点
intent_node = compiler.compile(
    session_id="sess-1",
    llm_name="Intent-LLM",
    cog_type=CogType.HYPOTHESIS,
    content="深层意图：用户想要扫描内存地址",
    confidence=0.78,
    parent_node_id=pcr_node.node_id,  # 引用 PCR-LLM 的节点
    edge_type=CogEdgeType.DERIVES,
)

# Meta-Cognitive-LLM 验证 Intent-LLM 的假设
compiler.lifecycle.validate(
    session_id="sess-1",
    node_id=intent_node.node_id,
    requesting_llm="Meta-Cognitive-LLM",
    validation_result="PASS: 意图与实体一致，置信度合理",
)

# Meta-Cognitive-LLM 发现矛盾，创建 CONTRADICTS 边
compiler.edge_manager.create_edge(
    session_id="sess-1",
    source_id=some_other_node.node_id,
    target_id=intent_node.node_id,
    edge_type=CogEdgeType.CONTRADICTS,
    requesting_llm="Meta-Cognitive-LLM",
)
```

---

## 12. 测试策略

### 12.1 测试目标

| 测试类型 | 覆盖率 | 关键验证点 |
|---------|--------|----------|
| 单元测试 | 100% | 编译、生命周期、边管理、权限检查的独立测试 |
| 集成测试 | 90% | 6 个 LLM 实例的完整读写流程 |
| 权限测试 | 100% | 每个 LLM 的 create/read/update/delete 权限矩阵 |
| 事件测试 | 100% | 事件发布/订阅/过滤/分发 |
| 遍历测试 | 100% | DFS/BFS/活跃分支/失效分支的遍历正确性 |

### 12.2 关键测试用例

**用例 1：权限矩阵验证**
```python
def test_access_control_matrix():
    acm = AccessControlMatrix()
    
    # PCR-LLM 可以创建 PERCEPTION
    assert acm.check_create("PCR-LLM", CogType.PERCEPTION)
    
    # PCR-LLM 不能创建 VALIDATION
    assert not acm.check_create("PCR-LLM", CogType.VALIDATION)
    
    # Meta-Cognitive-LLM 可以修改任何节点
    assert acm.check_update("Meta-Cognitive-LLM", "any-node", "any-owner")
    
    # Planning-LLM 只能修改自己创建的节点
    assert acm.check_update("Planning-LLM", "node-1", "Planning-LLM")
    assert not acm.check_update("Planning-LLM", "node-1", "PCR-LLM")
```

**用例 2：生命周期状态机**
```python
def test_node_lifecycle():
    lifecycle = NodeLifecycleManager(mock_store)
    
    # 创建节点（CREATED）
    node = CognitiveTreeNode(status=CogNodeStatus.CREATED)
    
    # 激活（CREATED → ACTIVE）
    assert lifecycle.activate("sess-1", node.node_id, "Planning-LLM")
    assert node.status == CogNodeStatus.ACTIVE
    
    # 验证（ACTIVE → VALIDATED）
    assert lifecycle.validate("sess-1", node.node_id, "Meta-Cognitive-LLM", "PASS")
    assert node.status == CogNodeStatus.VALIDATED
```

**用例 3：事件总线**
```python
async def test_event_bus():
    bus = EventBus()
    bus.start()
    
    received_events = []
    
    def callback(event):
        received_events.append(event)
    
    # 订阅 NODE_CREATED 事件
    sub_id = bus.subscribe("node_created", {"source_llm": "PCR-LLM"}, callback)
    
    # 发布匹配事件
    bus.publish(Event(type="node_created", data={"source_llm": "PCR-LLM"}))
    
    # 等待事件处理
    await asyncio.sleep(0.1)
    
    assert len(received_events) == 1
    assert received_events[0].data["source_llm"] == "PCR-LLM"
    
    bus.stop()
```

---

## 13. 附录：简化与待讨论项

### 13.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | 节点版本控制 | 完整版本历史（diff + 回滚） | 仅记录状态变更日志 | 完整版本控制需要 diff 算法，增加复杂度 | Phase 2 引入版本控制时实现 |
| **S-02** | 图遍历优化 | 大规模树的子图查询优化（CTE/Neo4j） | 全量加载后内存遍历 | 当前会话级树规模可控（<1000 节点） | Phase 3 引入图数据库时优化 |
| **S-03** | 事件持久化 | 事件日志持久化到 SQLite | 仅内存队列 | 事件持久化用于审计，初期不需要 | Phase 2 引入审计日志时实现 |
| **S-04** | 跨会话查询 | 全局 Cognitive Tree 查询（跨会话统计） | 仅会话级查询 | 跨会话查询需要全局索引 | Phase 3 引入全局索引时实现 |
| **S-05** | 语义边搜索 | 基于内容的边搜索（相似节点自动关联） | 仅基于显式边类型 | 语义搜索需要 embedding 计算 | Phase 2 引入 embedding 层时实现 |

### 13.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | 节点保留期 | A) 固定 30 天  B) 基于状态（VALIDATED 保留更久）  C) 基于用户画像（活跃用户保留更久） | 建议 B：VALIDATED 节点保留 90 天，CREATED 节点 7 天 |
| **D-02** | 矛盾边处理 | A) 创建矛盾边后自动触发 Meta-Cognitive  B) 仅记录矛盾，等待定期巡检  C) 矛盾边阻止下游推导 | 建议 A：实时触发 Meta-Cognitive 验证，确保系统一致性 |
| **D-03** | 事件订阅模式 | A) 内存队列（当前）  B) Redis Pub/Sub（分布式）  C) 消息队列（RabbitMQ/Kafka） | 建议 A：初期单进程内存队列足够；Phase 3 引入 Redis |
| **D-04** | 权限动态调整 | A) 固定权限（当前）  B) 基于节点置信度动态调整（高置信度节点放宽修改权限）  C) 基于用户反馈调整 | 建议 A：固定权限简单可靠，动态调整增加不可预测性 |
| **D-05** | 编译失败处理 | A) 抛出异常（当前）  B) 降级为日志记录，继续执行  C) 重试机制（最多 3 次） | 建议 B：编译失败不应阻塞主流程，记录日志后降级处理 |

### 13.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §5-§10 | ✅ 等价 | Cognitive Tree 节点/边/遍历/查询全部覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.2 | §8 | ✅ 等价 | 访问控制矩阵（6 个 LLM 实例）全部覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.3 | §9 | ✅ 等价 | 事件总线（订阅/发布/过滤/分发）全部覆盖 |
| `ENGINEERING_DATA_MODEL.md` §12.1-§12.4 | §5-§8 | ✅ 等价 | CognitiveTreeNode / CognitiveTree / CognitiveTreeEdge / AccessControlMatrix 对齐 |
| `ENGINEERING_PERSISTENCE.md` §12 | §5 | ✅ 等价 | CognitiveTreeStore 事务性写入对齐 |
| `ENGINEERING_MULTILAYER_LLM.md` §5 | §11 | ✅ 等价 | 6 个 LLM 实例的读写模式对齐 |
| `ENGINEERING_MULTILAYER_LLM.md` §8 | §5, §10 | ✅ 等价 | Cognitive Tree 操作 API 对齐 |

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档和已有数据模型/持久化定义生成。数据模型和持久化层已在 `ENGINEERING_DATA_MODEL.md` 和 `ENGINEERING_PERSISTENCE.md` 中实现，本文档新增约 **1000 行代码**（CognitiveCompiler + NodeLifecycleManager + EdgeManager + AccessControlMatrix + EventBus + Querier）。所有简化项已在 §13.1 中诚实标记，待讨论项在 §13.2 中列出，等待团队确认。*
