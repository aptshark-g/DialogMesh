# Subgraph 深度审计 — 三实现分裂 + 双 registry 断链

> 审计日期: 2026-08-01
> 对象: 子图编译器（跨链通信织物, BUSINESS_CHAIN_10）
> 方法: AST 依赖分析 + 运行时探针（.venv, 真实 engine 启动）
> 结论先行: **三套实现并存（分裂）+ 双 registry 只挂一半（断链）+ 消费方只用 v4 但 engine 没挂载**

---

## 一、全景盘点（找齐验证）

### 1.1 AST 真实依赖（非注释）

| 类型 | 位置 | 说明 |
|------|------|------|
| 真实 import+实例化 | `assembly/context_assembly.py:56-57` | v4 SubgraphCompiler() |
| 真实 import+实例化 | `assembly/unified_context.py:213-214` | v4 SubgraphCompiler(budget) |
| 真实 import | `cli/commands/__init__.py` | subgraph_cmd |
| 真实 import | `cli/entry.py` | cmd_subgraph_show/expand |

**关键词命中 40+ 文件里，绝大多数只是注释/字符串提到 subgraph，不是真实依赖。**

### 1.2 三个 SubgraphCompiler 实现（分裂）

| # | 文件 | 行数 | 机制 | 消费方 | 判定 |
|---|------|:---:|------|--------|:---:|
| 1 | `compiler/subgraph_compiler.py` | 13KB | 概念图水波展开（v3.0 DESIGN_V4_CONTEXT_ENGINEERING §4.4） | 无真实调用 | ❌ 死代码 |
| 2 | `v4/cognitive/subgraph_compiler.py` | 7.5KB | 跨域上下文编译（dialogue/meta 双视角） | context_assembly + unified_context + registry | ✅ 主实现 |
| 3 | `engine/deep_modules.py:325` | — | k-hop BFS 从 PersistentGraph | 无真实调用 | ❌ 死代码 |

---

## 二、双 registry 断链（核心发现，与 PCR 同型）

```
start_engine()          → build_dialogmesh_registry (49 项)
   → subgraph ✅ 注册  → engine._subgraph ✅ 挂载
_create_engine_instance → subsystem_registrations._registry (41 项)
   → subgraph ❌ 未注册 → engine._subgraph = None ❌
```

**实测证据**（探针 3）:
- `_create_engine_instance` 后 `engine._subgraph: None`
- 但 `_discourse_tree`/`_engineering_knowledge`/`_world_objects`/`_behavior_graph_adapter`/`_ocean_analyst` 全部真实存在
- registry B 41 项无 subgraph；registry A 49 项有（required=False）

**根因**: 与 PCR 完全同型——v6 演进中出现两个 engine 创建路径，各自维护独立 registry；子图只注册进了 A（start_engine），B（_create_engine_instance）缺失。

### 2.1 影响面精确化（2026-08-01 复核修正）

**B 不是 CLI/API 主路径**。实际启动链：

```
CLI / API (v6_app) → get_engine()
  → _engine 未运行 → 自动 start_engine()（A 路径）→ subgraph ✅ 挂载
  → get_engine 触发自动 start 同样走 A

测试 / 直接实例化 / EnginePool → _create_engine_instance()（B 路径）
  → subgraph ❌ 未挂载
  （EnginePool._create_engine → B；get_pool_engine() 当前无调用方，属预留场景）
```

**修正结论**：CLI/API 正常启动路径子图是挂载的（A 注册了）。B 缺注册主要影响
测试、直接实例化、以及预留的 EnginePool 多 worker 场景。审计初稿"生产路径
_subgraph=None"表述过度概括，特此修正。**修复方向不变**——B 补注册消除双路径
不一致，防止未来 EnginePool 启用后子图静默缺失。

---

## 三、主实现（v4）数据源真实性

**探针 4（真实 engine + v4 编译器）**:
```
compile_dialogue: entries=4 tokens=218
  [K] engineering 约束 ×3  ✅ 取到
  [B] behavior_graph stats ✅ 取到（node_count=0）
  D/E/P/F 域 ❌ 空（dialogue 树无数据 / world_objects 空 / ocean 空）
compile_meta: entries=2 tokens=70
```

**判定**: 编译器机制可用、数据源接口接得上（K/B 有数据），但：
- D 域（对话树）: `_trees` 为空 → 无 topic
- E 域（world_objects）: 空 dict
- P/F 域（ocean profile）: 无 profile
- R 域（关联链）: 代码里 alloc 有 R=10%，但 compile_dialogue **根本没实现 R 域获取**（alloc 声明了却没取）
- I 域（inertia）: 硬编码 `"inertia: pending implementation"` 占位符
- V 域（version control）: `_vcs` 属性在 engine 上 MISSING → meta 的 V 域取不到

**硬编码比例问题**（DESIGN_PCR §5.4 已点名）:
- dialogue alloc 硬编码 `{D:0.35, K:0.20, E:0.05, B:0.15, R:0.10, P:0.10, F:0.05}`
- meta alloc 硬编码 `{V:0.25, E:0.30, M:0.15, I:0.15, P:0.10, Q:0.05}`
- 与实际能取到的数据严重不符（alloc 说 R=10% 但 R 没实现；I=15% 但占位）

---

## 四、消费方接线状态

| 消费方 | 状态 | 说明 |
|--------|:---:|------|
| `assembly/context_assembly.py:56` | ⚠️ 懒加载 | try/except 内 import，失败静默 |
| `assembly/unified_context.py:213` | ⚠️ 懒加载 | 同上 |
| `cli/commands/subgraph_cmd.py` | ❌ 无效 | 读 `engine._subgraph`（None）+ 调 `expand_from_phrase`（v4 无此方法）|
| `cli/registry.py:340` | ✅ | start_engine 路径注册正确 |
| `api/v6_app.py` | ? | 待核查 |

**subgraph_cmd 双重失效**:
1. `getattr(e, '_subgraph', None)` → None（B registry 没挂）
2. 即使挂了 v4，`expand_from_phrase` 不存在（那是 deep_modules 第三个实现的 API 名？也不对——deep_modules 用的是 `expand`）→ `hasattr(sg, 'expand')` 才可能走到

---

## 五、CLI `dm subgraph` 实际行为

**CLI 正常启动（get_engine → start_engine → A 路径）时 `_subgraph` 已挂载**；
但命令仍可能失效，因为 `cmd_subgraph_expand` 优先调 `expand_from_phrase`
（v4 无此方法）→ 落到 `expand`（v4 也没有）→ error。show 命令只显示
compiler 类型，不实际编译。

```
cmd_subgraph_show:   编译器中已加载 → 输出 {"compiler": "SubgraphCompiler"}（不验证数据）
cmd_subgraph_expand: 调 expand_from_phrase → v4 无此 API → {"error": ...}
```

---

## 六、与 PCR 审计的同型对照

| 特征 | PCR | Subgraph |
|------|-----|----------|
| 多代演进 → 代码分裂 | 3 套契约（interface/v2/coordinate） | 3 套编译器（v3水波/v4跨域/deep_modules k-hop） |
| 双 registry 断链 | B 缺 pcr_router（已修） | **B 缺 subgraph（未修）** |
| 消费方调用错误 API | cmd_pcr 调 process() | cmd_subgraph 调 expand_from_phrase() |
| 死代码 | pcr/ 旧包 | compiler/subgraph_compiler.py + deep_modules.py |
| try/except 吞错误 | lazy import failed | context_assembly 懒加载静默 |

---

## 七、修复建议（对齐 PCR 施工模式）

### P0 — 接线修复（让子图首次真实进入生产路径）
| # | 文件 | 改动 |
|---|------|------|
| 1 | `cli/subsystem_registrations.py` | 补注册 subgraph（对齐 registry.py:340 同路径） |
| 2 | `cli/commands/subgraph_cmd.py` | show 读 `_subgraph`；expand 改调 v4 的 `compile_dialogue`/`compile_meta` |

### P1 — 设计落地
| # | 改动 |
|---|------|
| 3 | v4 补 R 域实现（alloc 已声明 R=10% 但未取）；I 域去掉占位符 |
| 4 | alloc 比例改为配置（对齐 DESIGN_PCR §8.1 YAML 模式），不再硬编码 |
| 5 | **新增 `pull_prior(domain_scope) → SubgraphPrior`**（DESIGN_PCR §5.4）——子图反哺 PCR 的先验通道，X 轴真实参照的根 |
| 6 | V 域接 `_vcs`（engine 缺该属性，需在引擎装配时挂载或降级） |

### P2 — 清理
| # | 改动 |
|---|------|
| 7 | 归档死代码：`compiler/subgraph_compiler.py` + `deep_modules.py` 的 SubgraphCompiler（确认无调用后） |

---

## 八、结论

**子图与 PCR 是同一个病根**：v6 演进 → 双 registry 分裂 → B 路径缺注册
（测试/直接实例化/预留 EnginePool 场景 `_subgraph=None`；CLI/API 走 A 路径
正常挂载）→ 一旦走 B 路径即静默降级。主实现 v4 机制本身可用（K/B 数据源探活
成功），但 D/E/P/F/R/I/V 域大半取不到数据或未实现，alloc 硬编码比例与真实
数据不符。CLI expand 命令调用了 v4 不存在的 API（expand_from_phrase/expand）。

**修复顺序**: ① B registry 补注册（一行）+ CLI 修正 → 子图首次真实运行；② v4 补 R 域 + alloc 配置化；③ `pull_prior` 接口（打通 PCR §5 双向协同）；④ 死代码归档。

---

## 九、修复状态（2026-08-01 施工完成追加）

### 9.1 已修复（P0 + P1 全部）

| # | 修复 | 证据 |
|---|------|------|
| 1 | B registry 补注册 subgraph | 探针: `_create_engine_instance` 后 `_subgraph=SubgraphCompiler` |
| 2 | CLI expand 改调 compile_dialogue/compile_meta | subgraph_cmd.py 重写 |
| 3 | registry 注入 engine（连环 bug） | 对抗测试抓出：全默认参数类跳过注入 → 子图 engine=None 空编译 |
| 4 | v4 意图矩阵 + alloc YAML + cross_ref + 修剪 + pull_prior + to_ir + 事件扩展 + 图扩展 + zone 桥接 | 40 测试全绿 |
| 5 | G 域悬空指针 / family 缺失 / trim 计量不一致 | 对抗测试抓出并修复 |

### 9.2 未完成（已记录待做）

- `test_real_engine_integration` 标 slow（默认排除，防 CI 超时）
- 死代码归档（§12 暂缓，前置条件已明确）
- 前瞻预热闭环（DESIGN_SUBGRAPH §13.3 ③，独立立项）
