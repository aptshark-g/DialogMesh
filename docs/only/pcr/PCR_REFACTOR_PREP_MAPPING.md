# PCR 改造准备 — 文件关系映射

> 2026-08-01 · 依据: DESIGN_PCR_DRAFT.md §14 拍板决策 + 当前代码核查
> 目的: 改造前先扯清"改哪些文件才有效"
> 核查注记: 2026-08-01 复核 — 已修正 2 处遗漏 (见 §三.0)

---

## 一、当前 PCR 接线全景（实测）

```
┌─────────────────────────────────────────────────────────┐
│              消费/引用 PCR 的所有点 (12 处)                │
├─────────────────────────────────────────────────────────┤
│ 1. cli/registry.py:260   _pcr_factory → PCRLLM  ❌挂错   │
│ 2. cli/engine.py          setattr _pcr_router (registry) │
│ 3. event/handlers.py:72   handle_pcr → route(text)       │
│    → PCRLLM.route 返回 None → 恒回退 MIXED               │
│ 4. api/v6_app.py:222      /v6/pcr → _pcr_router/_last_pcr│
│ 5. engineering_bridges:31 PCRV2Router ❌类名拼错         │
│    → ImportError 被吞 → PCRBridge 永远降级               │
│ 6. orchestrator/agent_native:141 route(override=) ❌     │
│    + .x/.y/.z (实际 x_axis/y_axis/z_axis) → 恒 0.5       │
│ 7. mcp/server.py:27       RuleBasedPCR (旧包装 evaluate) │
│ 8. service/agent_service.py  RuleBasedPCR + evaluate     │
│ 9. tools/cognitive_tools.py  PCRInput_v1 + evaluate      │
│ 10. v3_common/gates.py      PCRGate + evaluate           │
│ 11. pcr/ 旧包 (interface/datacontract/registry/...)      │
│     → 无实现类可注册 (issubclass IPCRRouter 强制)         │
│ 12. router/coordinate_router.py  影子实现 (阈值一致)      │
└─────────────────────────────────────────────────────────┘

主实现: pcr_router_v2.py (599行) — 零硬编码 + fallback 栈
        + LLM 闸门 + LLM 协同审查 (模型大小感知)
        ❌ 但: 三轴写死 / 不知下游 / 只吃 text 不吃切分
```

---

## 二、设计共识 (§14) → 改造落点映射

| 拍板决策 | 需要在哪实现 | 涉及文件 |
|---------|------------|---------|
| 1. 产出双视图: XYZ/zone 给算法 + 罗盘标签给 LLM | PCRResult 扩展 labels 字段 | `pcr_router_v2.py` |
| 2. 维度可插拔: 声明式注册, 权重可配置 | 维度注册表 (类似 SubsystemRegistry 模式) | `pcr_router_v2.py` 或新 `pcr_dimensions.py` |
| 3. 三阶段渐进切分: 粗切分→异步细化→后验 | PCR 输出 segment 骨架; 关联链/对话树消费 | `pcr_router_v2.py` + `event/handlers.py` + `discourse_block_tree.py` |
| 4. 子图双向: PCR 选域 + 子图反哺先验 | PCR 输入子图上下文; 输出域口径 | `pcr_router_v2.py` + `subgraph` 编译器 |
| 5. 关联链双向: PCR=L3 粗处理 + 链凝练规则辅助 | pcr_computed 事件 → FusionEngine L3 | `event/handlers.py` + `assoc_subscriber.py` |
| 6. X 轴混合保留: nomic+IDF+entity_density 权重可调 | _compute_distance 权重参数化 | `pcr_router_v2.py` |
| 7. 重做真实路由断言测试 | 修假测试 + 补 zone 断言 | `tests/test_pcr_v2*.py` |

---

## 三、有效修改文件清单（按优先级）

### 三.0 核查修正 (2026-08-01 复核)

**遗漏 1 — 双 registry 问题 (关键!)**
```
引擎有两个创建路径, 各用不同 registry:
  A. start_engine()           → build_dialogmesh_registry (registry.py:260)
     → _pcr_factory → PCRLLM (挂错实现)
  B. _create_engine_instance() → subsystem_registrations._registry
     → 完全没有 pcr 注册 → _pcr_router = None (PCR 不执行)

改造 _pcr_factory 时两处都要改:
  A: registry.py:260    _pcr_factory → PCRRouterV2
  B: subsystem_registrations.py  补注册 pcr_router (factory 或类)
否则只改 A, B 路径仍无 PCR — handlers 仍走 fallback MIXED
```

**遗漏 2 — RuleBasedPCR 类型错配**
```
RuleBasedPCR.evaluate(query: str) — 签名是 str
旧契约消费方传 PCRInput_v1 对象 (gates.py:190 / cognitive_tools.py:105)
→ 类型不匹配: str vs PCRInput_v1
→ 不只是"适配", 是"类型错配" — 旧消费方即使 import 成功也拿不到预期
```

### P0 — 接线修复 (让 PCR 首次真正进入生产路径)

| # | 文件 | 改动 | 为什么有效 |
|---|------|------|-----------|
| 1 | `cli/registry.py:260` | `_pcr_factory` 返回 PCRRouterV2 而非 PCRLLM | 所有走 registry 的路径立即生效 (engine/CLI/API) |
| 2 | `engineering_bridges.py:31` | `PCRV2Router` → `PCRRouterV2` | 一行修复, 消除 PCRBridge 永久降级 |
| 3 | `orchestrator/agent_native.py:141` | 去掉 `override=`, `.x/.y/.z` → `x_axis/y_axis/z_axis` | 消除编排器静默失败 |
| 4 | `event/handlers.py:72` | handle_pcr 消费 PCRResult (zone + labels) | 管线内 PCR 真实生效, 不再恒 MIXED |

### P1 — 设计落地 (§14 拍板项)

| # | 文件 | 改动 |
|---|------|------|
| 5 | `pcr_router_v2.py` | PCRResult 加 labels (温度/距离/价值罗盘) |
| 6 | `pcr_router_v2.py` | 维度声明式注册 + 权重可配置 (YAML) |
| 7 | `pcr_router_v2.py` | route 输入加 segment 骨架 (子图/上下文先验) |
| 8 | `api/v6_app.py` | /v6/pcr 输出罗盘标签 |
| 9 | `cli/commands/pcr_intent_cmd.py` | cmd_pcr_route 改调 route() 非 process() |
| 10 | `cli/commands/batch4_cmd.py` | _pcr_llm → _pcr_router 5 处 |

### P2 — 测试重写 (假测试清零)

| # | 文件 | 现状 | 改动 |
|---|------|------|------|
| 11 | `tests/test_pcr_v2.py` | test_v2_routing 不断言 zone; test_compare_old_pcr 类名错恒真 | 重写为真实断言: 期望 zone 逐条断言 |
| 12 | `tests/test_pcr_v2_dedicated.py` | 13 tests (需逐一审) | 补 zone 阈值断言 |

### 不改 (明确排除)

- `pcr/` 旧包 (interface/datacontract/lifecycle...) — 归档候选, 不改造
- `router/router_v4.py` — DEPRECATED
- `router/coordinate_router.py` — 影子实现, 若合并进 v2 则删
- `mcp/server.py` / `service/agent_service.py` / `tools/cognitive_tools.py` / `v3_common/gates.py` — 旧契约消费方, 若 v2 成为唯一主实现则改为适配或归档

---

## 四、依赖关系图 (改造后目标态)

```
                    ┌─────────────────────┐
                    │  pcr_router_v2.py    │ 核心 (改造)
                    │  维度注册表 (可插拔)  │
                    │  XYZ + 罗盘标签      │
                    │  segment 骨架输出    │
                    └──────┬──────────────┘
                           │ route() 返回 PCRResult
        ┌──────────────────┼──────────────────────┐
        ▼                  ▼                      ▼
┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ cli/registry │  │ event/handlers  │  │ orchestrator/    │
│ _pcr_factory │→ │ handle_pcr      │  │ agent_native     │
│ →PCRRouterV2 │  │ →pcr_computed   │  │ →x_axis 修正     │
└──────────────┘  └────────┬────────┘  └──────────────────┘
                           ▼
                ┌─────────────────────┐
                │ 关联链 FusionEngine  │  L3 消费 (防重复计算)
                │ L3 初始值 = PCR 坐标 │
                └─────────────────────┘
                           ▲
                ┌─────────────────────┐
                │ 子图 SubgraphCompiler│  双向: 选域口径 + 反哺先验
                └─────────────────────┘
```

---

## 五、关键判断

1. **改造核心是 pcr_router_v2.py 一个文件** — 维度可插拔 + 罗盘标签 + segment 骨架, 全在这
2. **接线修复 4 个文件即可让 PCR 首次真实运行** — registry/handlers/bridges/agent_native
3. **假测试在 test_pcr_v2.py 两个用例** — test_v2_routing (不断言 zone) + test_compare_old_pcr (类名错恒真)
4. **"无测试"论断 vs 假测试** — 报告说无测试(错, 有17个), 但17个里至少2个是假的 (用户判断更准: "假测试")
5. **旧契约消费方 (evaluate) 不急着改** — 先让 v2 主实现跑起来, 旧消费方走适配或归档

## 六、建议执行顺序

```
第 1 步: 修 4 个接线点 (P0) → PCR 首次真实运行, CLI/API 有真实输出
第 2 步: 重写假测试 (P2) → zone 断言真实, 防止回归
第 3 步: pcr_router_v2 改造 (P1) → 维度可插拔 + 罗盘标签 + segment 骨架
第 4 步: 接子图双向 + 关联链 pcr_computed (设计落地)
第 5 步: 旧包/旧契约归档决策
```
