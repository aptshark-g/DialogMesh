# PCR 深度审计报告 — 二轮核查结论

> 核查日期: 2026-08-01
> 核查对象: `docs/only/PCR_DEEP_INVESTIGATION.md` (2026-07-31)
> 方法: 逐条对照当前代码真实状态 (代码已因 Batch 1-7 修复发生变动)
> 结论先行: **报告主体论断 80% 仍属实, 2 条已过时, 1 条部分过时**

---

## 一、核查总览

| 论断 | 报告结论 | 当前状态 | 判定 |
|------|---------|---------|:---:|
| P0-1 引擎 _pcr_router 从不赋值 | ❌ 不执行 | `_pcr_router = PCRLLM` (registry 已挂) | ⚠️ 部分属实 |
| P0-1b route 返回 None | ❌ 空壳 | `PCRLLM.route(text) → None` (实测) | ✅ 属实 |
| P0-2 CLI 挂错实现 PCRLLM | ❌ 签名不匹配 | `cmd_pcr` 调 `pcr.process(text)` str vs dict | ✅ 属实 |
| P0-3 三套实现并存 | ❌ 契约分裂 | interface.py + pcr_router_v2 + coordinate_router | ✅ 属实 |
| P0-3b register_pcr 继承错误 | ❌ 注册必炸 | `issubclass(cls, IPCRRouter)` 强制, RuleBasedPCR 不继承 | ✅ 属实 |
| P0-4 类名拼错 | ❌ PCRV2Router | `engineering_bridges.py:31` 仍是 PCRV2Router | ✅ 属实 |
| P0-5 agent_native 字段错 | ❌ 静默失败 | `override=` + `.x/.y/.z` (实际 x_axis/y_axis/z_axis) | ✅ 属实 |
| P1-1 5 阶段 Pipeline 零实现 | ❌ | 仅 `ExpectationIdentifier = str` 假别名 | ✅ 属实 |
| P1-2 NoiseSpan 拓扑零实现 | ❌ | 全代码零引用 | ✅ 属实 |
| P1-5 X 轴公式偏离 | ⚠️ 部分 | nomic 768d (S,O)cos + IDF, 偏离 BGE 但方向一致 | ✅ 属实 |
| P1-6 6 zone 阈值不一致 | ⚠️ | pcr_router_v2 vs coordinate_router vs 设计 三套不同 | ✅ 属实 |
| P1-7 PCR_COMPUTED 未发布 | ❌ | 事件类型定义, 但 PCR 从未运行 → 从未发布 | ✅ 属实 |
| PCRRouterV2 无测试 | ❌ 严重 | **tests/test_pcr_v2.py + test_pcr_v2_dedicated.py 17/17 passed** | ❌ **已过时** |
| 168/170 是旧包成绩 | ⚠️ | 旧包测试仍在, 但新实现测试已补 | ⚠️ 部分过时 |
| 收敛方案 10 条 | 建议 | 见下"已落实 vs 未落实" | — |

---

## 二、关键判定明细

### ✅ 完全属实 (报告准确)

1. **PCRLLM 是空壳** — `route()` 只有 docstring 返回 None; `_build_prompt` 不填充占位符
2. **CLI 挂错实现** — `cli/registry.py:260 _pcr_factory()` 返回 PCRLLM 而非 PCRRouterV2
3. **三套契约分裂** — `IPCRRouter.evaluate` / `PCRRouterV2.route` / `PCRLLM.process` 无共同接口
4. **类名拼错** — `engineering_bridges.py:31` `PCRV2Router` → 应为 `PCRRouterV2`, ImportError 被吞, PCRBridge 永远降级
5. **agent_native 调用错误** — `route(text, override=...)` TypeError 被吞; `.x/.y/.z` 恒为默认值
6. **5 阶段 Pipeline 假实现** — `ExpectationIdentifier = str` 是类型别名不是类
7. **NoiseSpan 零实现** — 设计核心概念, 代码无踪迹
8. **zone 阈值三套不一致** — 设计(x<0.2,y<0.2) vs v2(0.3/0.3) vs coordinate_router
9. **PCR_COMPUTED 从未发布** — 事件枚举有定义, 但 PCR 不运行 → 永不触发

### ❌ 已过时 (报告不准确, 需更新)

1. **"PCRRouterV2 无测试"** — 现已存在 `tests/test_pcr_v2.py` (4 tests) + `tests/test_pcr_v2_dedicated.py` (13 tests), **17/17 passed (82s)**。报告 §四.2 说"全仓库 rg 未找到" — 这两个文件应在报告写作时已存在, 或写作时遗漏
2. **"无测试"推论** — 报告 §六 说"与当前主实现 PCRRouterV2 无关" — 现已有专属测试且全绿

### ⚠️ 部分过时

1. **P0-1 "引擎从不接线"** — 报告说 `_pcr_router = None` 从不赋值。当前 `start_engine()` 已通过 registry 挂载 `_pcr_router = PCRLLM` (错误实现但非 None)。"从不赋值"已不成立, "挂了错误实现"仍成立
2. **收敛方案** — 方案 9 (补 PCRRouterV2 测试) 已落实; 方案 3/4 (修 CLI 挂载/引擎装配) 部分落实 (挂了但挂错)

---

## 三、测试超时原因分析 (用户问题)

```
test_v2_routing 挂起根因:
  route(text) → _compute_mood → _load_mood_vectors
  → Try 1: LM Studio (127.0.0.1:1234) — 5s timeout, 快速失败
  → Try 2: sentence_transformers BAAI/bge-small-zh-v1.5
     → 模型已缓存 (models--BAAI--bge-small-zh-v1.5 在 HF hub)
     → 但首次加载 ~60-80s (CPU + onnx 初始化)

验证: 提高超时后 17/17 passed in 82s
结论: 不是死锁, 是首次加载慢。第二次跑会快 (类级缓存 _mood_vectors)
```

**建议**: pytest 超时从默认提升到 120s+; 或在测试 fixture 里预加载 mood vectors 避免每次全量下载/加载。

---

## 四、报告方法论评价

### 做得好的

- 文档时间线梳理完整 (4 代演进) — 价值高
- 接线盘点逐层追踪 (引擎/CLI/API/编排器/事件) — 这正是"追真实行为"
- 问题分级 (P0/P1/P2) 清晰
- 收敛方案具体可执行

### 不足的

1. **测试盘点遗漏** — 说"全仓库 rg 无 PCRRouterV2 测试"但 `tests/test_pcr_v2*.py` 存在。可能是写作时未跑 `rg -l` 或路径遗漏。**这是报告的硬伤 — 影响了"无测试"这一重要结论**
2. **静态判断为主** — 多数论断基于代码阅读, 未实际运行 route() 验证 (如能实测会发现 PCRLLM.route 返回 None 但 handlers 有 fallback)
3. **未区分"当前"与"写作时"** — 报告应标注核查时间戳, 后续变动无法追踪

---

## 五、建议行动

### 按报告收敛方案 (仍有效)

| # | 方案 | 状态 | 行动 |
|---|------|:---:|------|
| 1 | 定主实现 PCRRouterV2 | ✅ | 已定 (17 tests 支持) |
| 2 | 定主契约 route(text) → PCRResult | ⚠️ | 需统一 CLI/engine/bridges |
| 3 | 修 CLI _pcr_factory → PCRRouterV2 | ❌ | **下一步核心** |
| 4 | 修引擎装配 | ⚠️ | 已挂但挂错 (PCRLLM) |
| 5 | 修桥接类名 PCRV2Router → PCRRouterV2 | ❌ | 一行修复 |
| 6 | 修 agent_native override + 字段名 | ❌ | 两处修复 |
| 7 | 旧包处置 | ⚠️ | 需决策 |
| 8 | 补 5 阶段 (至少 Tier0) | ❌ | 设计落地 |
| 9 | 补测试 | ✅ | 已完成 (17/17) |
| 10 | 接 8 链信号 | ❌ | 设计落地 |

### 优先级建议

1. **P0-4 类名拼错** — 一行修复, 消除 PCRBridge 永久降级
2. **P0-5 agent_native** — 两处修复, 消除静默失败
3. **P0-2 CLI 挂载** — 换 PCRRouterV2, 让 `dm pcr route` 有真实输出
4. **P1-6 zone 阈值** — 统一到设计文档值
5. **P1-1/P1-2** — 5 阶段 Pipeline + NoiseSpan 是业务链核心, 需设计讨论后实施

---

## 六、结论

**报告质量高, 主体论断仍成立** — PCR 确实是"设计多代演进、代码分裂 3 套、生产路径从未真正运行"的典型模块。**唯一硬伤是测试盘点遗漏** (PCRRouterV2 已有 17 个测试且全绿), 这恰好说明"数端点不如跑行为" — 如果报告作者实测 route(), 会发现测试存在且实现可用, 问题只在接线。

当前最大问题不是"PCR 无实现", 而是 **"好实现 (PCRRouterV2) 挂在错误位置 (PCRLLM)"** + **3 个接线点的静默错误** (类名拼错/override/字段名)。修复成本低, 收益是 PCR 首次真正进入生产路径。
