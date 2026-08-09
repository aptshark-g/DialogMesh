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

---

## 七、二轮补充核查：测试文件真实性 + 断言质量（2026-08-01 追加）

> 补充人: 设计讨论会话 | 对象: §一"PCRRouterV2 无测试 → 17/17 passed" 的修正

### 7.1 git 证实：测试文件在首轮报告写作前已存在（首轮确为硬伤）

```
b41653d  2026-07-22 23:28  PCR V2: zero hardcoded keywords...            → 引入 tests/test_pcr_v2.py
1982eee  2026-07-23 23:57  Review fixes r1-r4...                          → 引入 tests/test_pcr_v2_dedicated.py
77c2f14  2026-07-24 11:37  Dual-track PCR: grammar_tagger + nemotron...   → 更新 test_pcr_v2.py
首轮报告 PCR_DEEP_INVESTIGATION.md: 2026-07-31 写作
```

**判定**: 二轮纠正成立——测试在首轮报告前已存在，"全仓库 rg 无测试"是首轮遗漏。

### 7.2 但"17/17 passed = 实现可用"是过度解读：核心行为零验证

逐个审读 17 个测试，发现大量**恒真断言**（任何输出都通过）：

| 测试 | 断言 | 判定 |
|------|------|:---:|
| `test_v2_routing` | 期望 zone 写在测试列表里但解包 `text, _, desc` **丢弃**，只断言 `execution_mode in (6值)` | ❌ 恒真 |
| `test_tool_command` | `r.zone in (6个zone)` | ❌ 恒真 |
| `test_chinese_query` | `r.execution_mode in (6值)` | ❌ 恒真 |
| `test_cognitive_level_inference` | `r.cognitive_level in (light/moderate/heavy)` | ❌ 恒真 |
| `test_structural_fallback_works` | `execution_mode in (6值)` | ❌ 恒真 |
| `test_short_empty` | `zone in (MIXED/ATOMIC)` | ⚠️ 半恒真 |
| StructuralFeatures 5 项 | entity/verb/question/imperative/cjk 具体值 | ✅ 有效 |
| `test_metadata_complete` | metadata 键存在 | ✅ 有效 |
| `test_zone_mapping_is_complete` | zone→mode 映射表 | ✅ 有效(静态) |
| `test_no_hardcoded_keywords` | 无中文词表 | ✅ 有效 |

**结论**: `route()` 返回的 x/y/z 坐标与 zone 是否落入设计阈值，**从未被断言**。"17/17 green"与"生产从未正确运行"可以同时成立——这正是首轮与二轮的共同盲区。

### 7.3 源码审读新增问题（二轮未提）

1. **生产首轮 60-80s 卡顿**: `route()→_compute_mood→_load_mood_vectors` 先探测 LM Studio(127.0.0.1:1234) 失败后加载 `bge-small-zh-v1.5`，首次 60-80s。测试 82s 即此。需预加载/缓存/降级策略
2. **LLM review 生产行为未测**: `_should_review()` 默认探测本地模型名后启用；测试手动 `_llm_review_enabled=False` 跳过。LLM 覆盖坐标(偏差>0.3 重算 zone)的路径零覆盖
3. **动词检测启发式**: 形态学后缀(ing/ed/ize)+辅音结尾短词，中文 verb_count 偏低；`不.` 正则误判"不是/不用"为疑问

### 7.4 修正后优先级

| 序 | 动作 | 理由 |
|:---:|------|------|
| 1 | **补真实路由断言测试**(zone 期望值) | 先有回归基线再动接线 |
| 2 | P0-4 类名拼错 PCRV2Router→PCRRouterV2 | 一行修复 |
| 3 | P0-5 agent_native override/字段名 | 两处修复 |
| 4 | P0-2 CLI 挂载换 PCRRouterV2 | 让 `dm pcr route` 有真实输出 |
| 5 | mood vectors 预加载/缓存 | 消除生产首轮 60-80s |

### 7.5 与"设计凝练"的关系

本次核查不改变 DESIGN_PCR_DRAFT 的糅合方向（§五/§七/§九/§十二），但强化两点：
- PCRRouterV2 的"零硬编码"实现路线值得保留（17 测试确认无词表）
- 但坐标/zone 阈值需要**按设计文档重定并补断言**，不能以"测试全绿"视为已对齐设计

---

## 八、P1 阶段 1 数据结论（2026-08-01 追加，施工实测）

> 本节记录 P1 施工（本地 BGE 替代 + Z 软投票 + X prior 接口）后的实测数据。
> 结论先行：**骨架已通，组件质量未达标**。黄金样例集 11 条实测命中 2-4/11
> （PSYCHE 曾 2/2，软投票后回落到 0——见 Z 轴分析）。差距是组件质量问题，
> 不是接线/参数问题，继续调温度不会带来真实改进。

### 8.1 已落实（P0 全部 + P1 阶段 1 骨架）

| 项 | 状态 | 证据 |
|---|:---:|------|
| P0 接线 5 处（registry/双 registry/bridges/agent_native/handlers） | ✅ | 代码实测 |
| zone 阈值统一到设计基线（0.2/0.2、0.7/0.7/0.5） | ✅ | `_zone_from_xyz` |
| 本地 BGE 离线加载（HF_HUB_OFFLINE + 缓存模型） | ✅ | `.venv` 14.8s 加载成功 |
| 查询编码与 mood 向量来源匹配（`_query_embed`，nomic↔HTTP / BGE↔本地） | ✅ | 消除 768d/512d 维度错配 |
| Z 轴软投票替代 argmax（类别聚合，防类别数量稀释） | ✅ | 不再 10/14 硬偏 solution_seeking |
| X 轴 `subgraph_prior` 接口（§5 协议落位） | ✅ | route(text, subgraph_prior=...) |
| 双语 mood 描述符（32→64 锚点） | ✅ | config/mood_profiles.yaml |
| 假测试清零 → 设计契约断言 + strict xfail | ✅ | tests/test_pcr_v2.py |

### 8.2 Z 轴：锚点集不可分（核心缺口）

**数据**（`.venv` + 本地 BGE，64 个双语描述符）：

```
类内 cos mean=0.529  类间 cos mean=0.472  gap=0.057
「我好烦，什么都不想做」        → z=-0.26（设计需 < -0.5 → PSYCHE）
「为什么这个函数被优化掉了」      → z=+0.15（设计需 ≤ 0）
「I feel exhausted...」       → z=-0.28（设计需 < -0.5）
```

**判定**：BGE-small-zh 对这 4 类情绪/意图锚点的嵌入空间几乎重叠
（gap 0.057）。argmax / 描述符软投票 / 类别聚合软投票都无法从中分离出
可靠信号——调温度只是换一种自欺方式。**中文情绪离线判定为弱信号**，
按设计 §3.3 应由 **LLM 后验**最终裁决（LLM 糅合本来就是设计意图）。

### 8.3 X 轴：短句 BGE 余弦区分度不足（核心缺口）

**数据**（`subgraph_prior` 接口实测）：

```
「量子退火在物流调度里到底怎么用」 + 相关 prior「量子退火算法在组合优化中的应用」
  → X=0.51（应近，却远）
「把上个月所有未读邮件归档并生成报表」 + 自身 prior → X=0.33（应≈0）
```

**判定**：512 维短文本嵌入的 `1-cos` 在"新颖度"任务上分辨率太低。
`subgraph_prior` 接口方向正确，但只有 prior 是**真实的子图/历史向量**
（§5 `pull_prior`，而非任意文本）时才可靠。无真实 prior 时 X 显式退化到
结构新颖度（entity_density），不再用假参照冒充语义距离。

### 8.4 P1 后续方向（数据驱动）

1. **Z 轴中文情绪**：不追求离线 BGE 分类精度；保留软投票弱信号，
   最终由 LLM 后验审查裁决（§3.3）。英文情绪 NRC-VAD 路径保留。
2. **X 轴**：落地 `subgraph pull_prior(domain_scope)`（§5.4 已核查：
   现有编译器无此 API），prior 用真实用户上下文向量，而非文本 cos。
3. **测试**：黄金样例集保持 strict xfail 作为 P1 验收标准，P1 落地后
   移除 xfail 标记（strict=True 使 XPASS 变 FAIL，防止"环境退化假通过"）。
