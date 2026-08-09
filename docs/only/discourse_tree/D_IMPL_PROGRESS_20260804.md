# 对话树模块级补全施工记录 — 2026-08-04

> 范围：模块级补全（M1-M9 之后）——对话树 D 系列 + D-14 + M1-P12。
> 拍板依据：R6 D3（B 管理内核 + C 编译器 + A 接线门面）+ KERNEL_ABSORPTION §八/§九。
> 状态：✅ 完成（71/71 对话树+CLI 回归 + 相关跨模块回归全绿）。

---

## 一、D-14 CohesionScore 字段 bug（修复）

### 根因（实测）
```
core/agent/cli/registry.py:279          ← discourse_tree 注册 A 版
core/agent/cli/subsystem_registrations.py:24  ← 同上
start_engine Phase 3 setattr(engine, "_discourse_tree", A_instance)
  → 覆盖 engine.__init__ 建的 B 内核（runtime/engine.py:157）
  → CLI 测试 test_discourse_write_ops 用 A 版 feed()
  → A 版 feed() 794/830 行读 cohesion.total_score
  → A 版 CohesionScore 字段是 total → AttributeError（cli 测试唯一失败）
```

### 修复
1. **A 版防御**（`compiler/discourse_block_tree.py`）：
   - `CohesionScore` 增加 `total_score`/`macro_score`/`micro_score` 兼容属性
     （与 B 版 models 字段对齐，两套命名都可用）
2. **M1-P12**：A 版 `_llm_summarize` 移除硬编码
   `http://127.0.0.1:1234/v1/chat/completions` 直连 → 统一走
   `llm_provider` 参数，无 provider 时 BM25 兜底（零直连）。

---

## 二、D3 内核组装落地（P0：B 管理内核 + A 接线门面）

### 2.1 registry 切 B 内核
```
registry.py:279 / subsystem_registrations.py:24
  core.agent.compiler.discourse_block_tree:DiscourseBlockTreeManager  (A)
  → core.agent.discourse_block_tree.manager:DiscourseBlockTreeManager (B)
```
效果：`start_engine` 后 `engine._discourse_tree` 保持 B 内核
（engine `__init__` 本来就是 B，registry 覆盖是历史残留）。

### 2.2 B manager A 兼容写操作面（新增）
`discourse_block_tree/manager.py`：
- 读：`get_stats` / `find_block_by_reference` / `root_id` / `current_branch`
- 写：`split_block` / `merge_blocks` / `delete_block` / `promote_block` /
  `demote_block` / `compress_cold_blocks` / `set_block_summary`
- 上下文：`build_session_context` + `build_context` 参数分派
  （(sid, max_blocks) → 会话级；(block_id)/无参 → B 原生块级）

### 2.3 B DiscourseBlock A 兼容别名
`discourse_block_tree/models.py`：
- `edus` ↔ `atomic_units` / `parent` ↔ `parent_id` / `children` ↔ `child_ids`
- `temperature` ↔ `status`（setter 兼容 int 0-3 与字符串）
- `topic` ↔ `name`

CLI/API 门面（cmd_show/cmd_block/cmd_summary/batch3 memory/api_viz_edit）
无需改数据模型即可消费 B 内核。

### 2.4 CLI 门面适配
- `cmd_feed`：B 的 `_RouteResultCompat` 是字符串 decision + block_ids
  → 兼容 `.value` 与 `target_block_id` 两种形态
- `cmd_block`/`cmd_summary`：B 的 `summary` 是 ProgressiveSummary 对象
  → `get_best()` 归一 + `set_block_summary` 优先
- `batch3_cmd.cmd_memory_real_show`：温度计数改为 status 字符串语义

---

## 三、测试验证

```
对话树全量+CLI: 71/71 ✅（discourse_block_tree 全部 + compiler 旧单体 13
  + cli test_cli 28 全部，其中 test_discourse_write_ops 由 1 失败 → 全过）
新增 D3 回归:    test_a_facade.py 13/13 ✅（写操作面 + 别名 + D-14 + registry 指向）
核心回归:        kernel 49 + serializer 11 + statemachine 10 = 70/70 ✅
白盒编辑:        viz_edit 29/29 ✅
Event:           subscribers 8 + statemachine 10 + lifecycle 12 = 30/30 ✅
存储/网关/服务:  service_middleware 8 + gateway 14 + unified_graph 5 + fact 9 = 36/36 ✅
行为/意图/画像:  adapter 8 + intent 8 + fact_store 9 = 25/25 ✅
关联链/L3:       association_service 21 + l3_intent 1 + funnel 2 = 24/24 ✅
设计矩阵:        test_discourse_design_matrix 11/11 ✅
```

> 已知预存在失败（非本次引入）：`tests/test_discourse_integration.py`
> collection 错误 —— `load_module_from_path` 动态加载相对导入模块失败
> （测试基建问题，segmenter.py 等文件未改动）。

---

## 四、改动文件清单

```
core/agent/compiler/discourse_block_tree.py       D-14 兼容属性 + M1-P12 直连移除
core/agent/discourse_block_tree/models.py         A 兼容别名（edus/parent/children/temperature/topic）
core/agent/discourse_block_tree/manager.py        A 兼容写操作面 + build_context 分派
core/agent/discourse_block_tree/test_a_facade.py  新增 13 项回归
core/agent/cli/registry.py                        discourse_tree 注册 → B 内核
core/agent/cli/subsystem_registrations.py         discourse_tree 注册 → B 内核
core/agent/cli/commands/discourse_cmd.py          feed 返回值 / summary 对象 / set_block_summary
core/agent/cli/commands/batch3_cmd.py             memory 温度计数 status 语义
```

## 五、与 KERNEL_ABSORPTION 对照

- §三 契约：`ingest_turn`/`feed` 统一（B 已具备）✅
- D3：C 编译器（decompose/inject 完整版保留在 compiler/）+ B 管理 + A 接线 ✅
- C6 字段名：v3_evolution/v3_milestone 双读兜底（既有）✅
- C2 灰区：A 版已有 gray_buffer A13 延迟；B 版 classify_quadrant 已实现 ✅
- C4 语义唤醒：B 版 summary_engine.semantic_wake + test_semantic_wake ✅
- D11 三范式标签：compass 已实现（p10_cmd context-paradigm）✅

> 剩余（记录不施工）：C5 四级摘要行为链元信息（注解层方案，待关联链联动）、
> C9 attach 路由落地（classify_quadrant 已就绪，待路由接入）。
