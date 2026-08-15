# 七树接线 + 持久化施工记录（2026-08-15）

> 状态: 施工完成 ✅ | 触发: 用户"做上接线吧……还有持久化的, 这轮更新
> 尽可能完善后端闭环" | 前置核查: 大部分功能是"实现完整但没接线"
> （planner 六策略/七树中六树/联邦查询接口零生产调用）; 执行树持久化
> 是"没有"。上一轮已修生产取树恒 None（engine.get_agent_tree）。

## 一、核查结论（实现 vs 接线）

| 模块 | 实现 | 接线前状态 |
|---|---|---|
| planner/ 六策略规划器（PlanningSkill） | 完整 | 生产主链路未调用（孤儿） |
| 七树 AgentTreeManager | 完整 | 仅 ExecutionTree 有消费端（且生产取树曾恒 None）; Behavior/Association/Meta/Profile/Constraint 零生产调用方 |
| 执行树消费器（MetaTreeConsumer/ExecutionPatternStore/AuditFeedbackLoop） | 完整 | 生产取树断（上轮修） |
| 七树持久化 | ❌ 无 | save/load 均不存在 |
| 跨树联邦查询（global_query） | 完整 | 零生产入口 |

结论: 不是"功能没有", 是"生产路径没接"——壳与测试绿, 主链路断。

## 二、本轮施工（全部实测）

### 1. 七树序列化持久化（tree_manager.py）
- `AgentTreeNode.to_dict/from_dict` + `AgentTree.to_dict/from_dict`（原地
  重建, 保持实例引用）+ `AgentTreeManager.to_dict/from_dict/save/load`
  （原子写盘 tmp+replace, 与 discourse 落盘同模式）
- round-trip 测试: 执行/行为/元认知/关联树节点全恢复, 幂等

### 2. engine 挂载（runtime/engine.py）
- `get_agent_tree(sid)` 惰性创建时 Warm→Hot 自动 load
  （`data/agent_trees/{sid}.json`, env `DM_AGENT_TREES_DIR` 可覆盖）
- `_persist_agent_tree(sid, force)`（3s debounce, force 旁路）
- `query_agent_trees(text, sid)` 跨树联邦查询（带树名归属）

### 3. 七树消费接线（_consume_execution_tree 扩展）
- audit 事件 → `MetaTree.record_decision`（元认知裁决落树）
- doom_loop/failing_tool → `BehaviorTree.record_pattern`（工具风险模式,
  与 BehaviorBrain 用户模型隔离——执行模式非用户行为）
- 执行任务 ↔ meta 节点 → `AssociationTree.map_nodes`（跨树可查）
- 消费后立即 `_persist_agent_tree(force=True)`（终端状态持久化）

### 4. 规划→执行步骤级接线（task_runner.py + v3_session_api.py）
- `TaskConstraint.steps` 新字段: 任务图节点（用户确认的规划产物）作为
  步骤地图 → 落执行树 `create_task.steps` + `build_inject` 注入执行上下文
- v3_session_api Phase 4: `_get_task_graph_ws` 节点名 → steps 传入
- v3_session_api Phase 3.5: run_dag 后补 `_consume_execution_tree(force)`
  —— DAG 内 agentic 节点执行树不再只落内存（A17）

### 5. 白盒端点（stubs_api.py）
- `GET /v6/agent-trees?sid=xxx&q=关键字` — q 给定时联邦查询, 否则七树统计

## 三、验证

- 新增/扩展测试 8 项全绿（生产接线 4 + 持久化/消费/联邦/steps 4）
- 相关回归: execution/llm/meta/event + api 相关 173 全绿, blueprint 151 全绿
- **真实端到端（8000 API 重启后）**: task 请求 87s（LLM 主导）→ 执行树
  7 节点（1 task + 6 步骤: grep/grep/dir_list/run_shell/file_read/run_shell）
  → `/v6/agent-trees` 200 七树统计 → 联邦查询 q=hello.py 命中执行树 →
  `data/agent_trees/{sid}.json` 落盘含全部七树, 执行树 7 节点

## 四、边界与后续

- planner/ 六策略（PlanningSkill）仍未接主链路——当前规划 = BlueprintEngine
  模板 DAG + LLM 任务图; 是否引入 PlanningSkill 做第二规划通道留 P2 决策
- BehaviorTree/ProfileTree 与画像/用户模型的深度联动（W7）未做
- 七树跨会话聚合（多 session 联邦）未做

---

# 追加: 多会话聚合 + 七树前端绑定（2026-08-16）

> 状态: 施工完成 ✅ | 触发: 用户"继续1"（上轮建议 ① 多会话聚合/七树前端绑定）

## 一、后端（runtime/engine.py + stubs_api.py）

- `engine.query_all_agent_trees(text, max)` — 跨会话联邦查询: 已加载
  会话（内存）+ 盘上 Warm 层会话（逐文件 load 扫描, 查完即弃不驻留）
- `engine.agent_tree_sessions()` — 全部会话七树统计（loaded 标记内存/盘上）
- `/v6/agent-trees` 端点扩展:
  - 无 sid → 全部会话统计聚合（session_count/total_nodes）
  - 无 sid + q → 跨会话联邦查询（session_count + hits 带 session_id/tree）
  - 有 sid → 单会话（原行为不变）

## 二、前端（MetaCenterPage 七树 tab）

- `api/v6.ts` `getAgentTrees(sid?, q?)` + `types/api.ts` 类型
- MetaCenter 新增"七树"tab: 跨会话联邦查询框（hits 展示 tree/session/
  node_id/content）+ 聚合统计卡片（会话树数/节点总数）+ 每会话七树
  节点表（活跃/完成/归档）
- 顺带修复预存 tsc 错误: Sidebar.tsx 缺 `Activity` import

## 三、验证（全部实测）

- 后端测试 10/10（新增跨会话联邦 + 盘上扫描 2 项）; 回归 91 全绿
- tsc 零错误; vite build 成功（仅有预存 chunk 警告）
- 真实端到端（API 重启加载新代码）:
  - 聚合: 3 会话 / 9 节点（盘上）
  - 联邦查询 q=hello.py: 命中 4 条（跨会话执行树）
  - 新 task 请求 115s: 执行树 11 节点 → 新会话进聚合 → 联邦命中

## 四、边界

- 前端只读展示（联邦查询/统计）; 七树 CRUD 编辑仍留白盒后续
- 盘上扫描每次全文件 load（会话多时可加索引/缓存, 当前量级无害）
