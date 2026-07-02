# 架构缺口修复方案 — 最优版（效果优先，不限制改动量）

> 记录日期：2026-06-23
> 决策原则：效果与全面性优先，不限制代码改动量

---

## 已确认方案（3 个 P0/P1 缺口）

### 1. PCR 反馈闭环 — A+M（GP + 小 MLP 特征变换）
### 2. 冷启动策略 — LLM 介入 + 可配置词表 + 混合语言 + 阀门阈值
### 3. 异步 LLM — 流式原生异步实现

---

## 新增确认方案（6 个审计问题）

### 4. 规则冲突检测 — 方案 B（规则图谱 + 静态分析）【最优】

**选择理由**：静态可验证，CI 前就能发现冲突，而非运行时才发现。

**实现**：构建规则冲突图，用连通分量检测。正则表达式重叠分析基于 fuzz 生成 + 领域隔离。
- 规则图谱：`core/agent/intent_parser/rule_graph.py`
- 静态分析：`core/agent/intent_parser/static_conflict_checker.py`
- CI 脚本：`scripts/check_rule_conflicts.py`

### 5. 蓝图粒度 — 方案 B（子蓝图嵌套，执行计划语义）【最优】

**选择理由**：蓝图真正成为执行计划，而非策略标签。Executor 能精确展开嵌套蓝图。

**实现**：
```python
@dataclass(frozen=True)
class Blueprint:
    id: str
    description: str
    steps: List[Union[str, "Blueprint"]]  # 支持嵌套
    gate: str
    latency_budget_ms: int
    requires_llm: bool = False
    fallback_id: Optional[str] = None
    max_nesting_depth: int = 3
```
- `BlueprintLibrary.validate()`：检查循环依赖、工具注册、嵌套深度
- `BlueprintExecutor.expand()`：递归展开蓝图为扁平工具序列
- 向后兼容：保留 `sequence` 为 `steps` 的 deprecated 别名

### 6. 分布式锁接口 — 完整实现（Redis + 单机适配）【最优】

**选择理由**：预留接口不够，直接实现完整的 Redis 分布式锁，单机用适配器。

**实现**：
- `DistributedLock` ABC 接口
- `ThreadingLockAdapter`（单机）
- `RedisLockAdapter`（Redis Redlock 实现）
- `SessionStore` ABC 接口
- `InMemorySessionStore`（单机）
- `RedisSessionStore`（Redis 哈希存储）
- `SQLiteSessionStore`（轻量持久化，无 Redis 时可用）
- `AgentService` 注入锁和存储

### 7. WebSocket 事件注册表 — 完整 Schema 验证 + 第三方扩展【最优】

**选择理由**：第三方可安全扩展，核心事件受保护，Schema 版本管理。

**实现**：
- `EventTypeRegistry`：注册表 + Schema 验证
- `EventBuilder`：使用注册表验证 payload
- `EventVersion`：版本管理
- 核心事件禁止覆盖
- 未知事件转发给前端
- Schema 嵌入版本号

### 8. FSM 外部状态映射 — 完整分层 + 双向映射 + 历史追溯【最优】

**选择理由**：不只是单向映射，支持前端查询历史状态转换。

**实现**：
- `ClarificationState.to_external()`：内部 → 外部
- `ClarificationState.from_external()`：外部 → 内部（反向解析）
- `StateTransitionLog`：记录状态转换历史
- WebSocket 发送外部状态，API 返回外部状态
- 调试模式暴露内部状态

### 9. MCP 依赖边界文档 — 完整文档 + 部署矩阵 + 功能矩阵【最优】

**选择理由**：纯文档，但要做就做完整。

**实现**：
- `docs/MCP_DEPLOYMENT_MATRIX.md`：部署场景对照表
- 功能矩阵：每个功能标注是否需要 MCP
- 部署脚本：最小部署、完整部署、Claude Desktop 集成
- 环境变量配置模板

---

## 实现顺序（按依赖关系）

1. 分布式锁接口（SessionStore 是其他模块的基础）
2. 蓝图粒度（Executor 依赖存储）
3. 规则冲突检测（独立模块，可并行）
4. WebSocket 事件注册表（独立模块，可并行）
5. FSM 外部状态映射（小改动）
6. MCP 文档（纯文档，可并行）
7. 异步 LLM（中等改动）
8. 冷启动策略（中等改动，依赖 LLM 异步）
9. PCR 反馈闭环（最大改动，最后）
