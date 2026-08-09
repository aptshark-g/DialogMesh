# DESIGN_PCR.md — PCR 新设计（凝练版 v0.1）

> 状态: **v0.2 凝练基线 + A18 自适应闭环**（2026-08-01）
> 来源: `DESIGN_PCR_DRAFT.md`（14 节草稿）+ `PCR_DESIGN_SUMMARY.md`（核心摘要）+ `PCR_REFACTOR_PREP_MAPPING.md`（改造映射）
> 定位: PCR 改造的设计主文档，实现时对照 `PCR_REFACTOR_PREP_MAPPING.md` 执行；docs 原有文档不动
> 说明: 本文档只凝练"拍板后的设计"，讨论过程与未采纳方案回查草稿对应章节

---

## 0. 文档导览

| 章节 | 内容 | 关联来源 |
|------|------|---------|
| §1 定位与职责边界 | PCR 是什么、干什么、不干什么 | 草稿 §2/§14.3 |
| §2 双视图产出 | 坐标(算法) + 罗盘标签(LLM)，并列计算 | 拍板 1/8，摘要 §二/§六 |
| §3 维度系统 | 声明式注册、可插拔、权重可配置 | 拍板 2/6，草稿 §13 |
| §4 三阶段渐进切分 | 粗切 → 异步细化 → 后验维护 | 拍板 3 |
| §5 子图协同 | C/S 被动架构、口径与反哺 | 拍板 4/9/10 |
| §6 关联链协同 | L3 粗处理、规则辅助、pcr_computed | 拍板 5 |
| §7 接口协议 | PCRResult / route() / 事件契约 | 映射 §二 |
| §8 权重配置与验证 | YAML 权重、黄金样例、真实断言 | 拍板 6/7 |
| §9 改造落点 | P0/P1/P2 文件清单、执行顺序 | 映射 §三/§六 |
| §10 糅合来源索引 | 保留/废弃/借鉴/文献 | 草稿 §4-§13 |

---

## 1. 定位与职责边界

**一句话定位**: PCR（意图粗处理）是意图理解管线的 **L3 粗处理层**，负责在输入时产出双视图（坐标 + 罗盘标签）与粗切分骨架；它决定**子图口径**（取哪些域、预算多少），**不编译子图内容**。

### 1.1 职责边界表

| 做（PCR 职责） | 不做（交给下游） |
|---------------|----------------|
| L3 粗处理：输入时快速产出意图坐标/标签 | 子图内容编译（SubgraphCompiler） |
| 输出粗切分 segment 骨架（边界候选 + 置信度） | 主题精切分（LLM 回答期间关联链异步细化） |
| 决定子图口径（选域 / 预算） | 最终内容选择（子图"预期上下文"由子图服务端回应） |
| 主动拉取子图/关联链"预期上下文"作为先验 | 全量 NLP 处理（关联链是 NLP 核心，PCR 只干粗活） |
| 输出 pcr_computed 事件供 FusionEngine 复用 | 重复计算下游已产出的信息 |

### 1.2 三条关键约束（讨论确认）

1. **切分是渐进精化**：PCR 只承诺"边界候选 + 置信度"，关联链/后验可纠错，不级联放大错误。
2. **职责单一**：关联链是 NLP 处理核心；PCR 只做 L3 粗处理，不越权。
3. **防重复计算**：PCR 归属关联链第三层领域，仅做粗处理，精算在关联链；PCR 产物必须可被下游复用而非重算。

---

## 2. 产出：双视图（并列计算）

### 2.1 双视图定义

| 视图 | 内容 | 服务对象 | 用途 |
|------|------|---------|------|
| **坐标视图** | XYZ 三轴值 + zone 路由标签 | 算法/路由/子图选域 | 确定性路由、域口径选择 |
| **罗盘标签** | 温度 / 距离 / 价值（语义化标签） | LLM | LLM 导航、意图理解辅助 |

### 2.2 并列计算（拍板 8）

- 坐标与罗盘标签**各自独立产出，互不推导**（标签不是坐标的简单映射）。
- **冲突不裁决**：两视图服务对象不同（算法 vs LLM），出现分歧时记录冲突供后验分析，不做二选一。
- **成本控制**：复用坐标中间结果（结构特征/距离计算），非全量重复计算。

### 2.3 产出契约（PCRResult 扩展）

```
PCRResult:
  x_axis / y_axis / z_axis   # 坐标视图（算法路由用）
  zone                       # 6 zone 路由结果
  labels: { temperature, distance, value }  # 罗盘标签（LLM 导航用）
  segments: [SegmentSkeleton] # 粗切分骨架（边界候选 + 置信度）
  domain_scope: { domains, budget }  # 子图口径（选域/预算）
  conflicts: [...]           # 双视图冲突记录（供后验）
```

---

## 3. 维度系统：声明式注册（拍板 2/6）

### 3.1 设计原则

- **声明式注册**：维度集通过注册表声明（参照 `SubsystemRegistry` 模式），可插拔、可增删。
- **权重可配置**：权重放 YAML，不硬编码；**调权重优先于斟酌去留**。
- **零硬编码**：保留 PCRRouterV2 的"无词表"原则，检测逻辑用形态学启发式/正则/模型，不用关键词列表。
- **维度可换**：同一维度 = 一组可插拔计算器（主/备/兜底 fallback 栈），主实现不可用时自动降级。
- **独立 unit + 注册表（对齐 snips ProcessingUnit，2026-08-01 深读）**：每个维度计算器升级为独立 parser unit，经注册表声明（@register 模式），引擎按配置选——比“同一函数内 fallback 栈”更彻底，可插拔性对齐 snips-nlu 的三态解析器（deterministic/probabilistic/lookup 同一接口）。

### 3.2 默认维度集（v0.1 基线）

| 轴 | 语义 | 默认计算器栈（主 → 备 → 兜底） | 备注 |
|----|------|-------------------------------|------|
| **X 距离** | 语义距离/新颖度 | nomic cos + IDF → Stanza SVO 结构距离 → entity_density | **混合保留**：nomic cos + IDF + entity_density 按权重融合，不删维度（拍板 6） |
| **Y 粒度** | 结构粒度 | StructuralFeatures.extract（动词/实体/疑问形态学）→ LLM 实体补全后重算 | 公式与 v2 一致：`min(v/5,1)*0.4 + min(e/5,1)*0.3 + min(w/20,1)*0.3` |
| **Z 温度** | 情感温度 | LM Studio nomic → BGE → NRC-VAD → 结构 fallback | 沿用 v2 四级降级链 |

> 注：v2 实现中 X 轴实际退化为 `entity_density*0.5+0.3`（≈词汇新颖度）。新设计两条路：补回语义距离计算（nomic cos/子图召回做距离），或明确降级为"词汇新颖度"轴——**必须显式定义，不得隐性退化**。

### 3.3 LLM 糅合机制（保留 v2 工程骨架）

1. **LLM 补全闸门**：实体 = 0 且文本 > 10 字才触发 LLM 实体提取（成本控制，算法先跑、LLM 只在零信号时介入）。
2. **LLM 协同审查**：模型大小感知（small 3 信号 / medium 语法标签 / large 仅坐标）；偏差 > 0.3 才覆盖坐标重算（防抖动）。
3. 该机制与文献结论一致（7-30B 中间带在语法标签上受益），作为实现层模板保留。
4. **LLM 输出 JSON Schema 约束（生成时，对齐 outlines，2026-08-01 深读）**：zone/labels 输出用 JSON Schema 约束生成（logits masking，采样阶段排除非法 token），不是生成后校验——绝不产生格式错误，从“软校验”升级为“硬约束”。

---

## 4. 三阶段渐进切分（拍板 3）

**核心思想：切不着急。** 输入时只给粗切分，精化放在 LLM 回答期间和后验。

```
输入文本
  │
  ▼
[阶段1] PCR 粗切分 ──→ segment 骨架（边界候选 + 置信度）
  │                        （输入时，毫秒级，无 LLM 依赖）
  ▼
[阶段2] LLM 回答期间 ──→ 关联链异步细化切分
                           （利用 2-5s LLM 等待窗口，不占用户时间）
  ▼
[阶段3] LLM 后验维护 ──→ 事后纠错/收敛（可修正阶段1/2 结果）
```

| 阶段 | 时机 | 执行者 | 产出 | 承诺 |
|------|------|--------|------|------|
| 1 粗切 | 输入时 | PCR（算法为主） | segment 骨架 + 置信度 | 只给候选，允许错 |
| 2 细化 | LLM 回答期间 | 关联链（异步） | 细化主题边界 | 利用等待窗口，不阻塞回复 |
| 3 维护 | 回答后 | LLM 后验 | 修正后的最终切分 | 可纠错，不级联放大 |

**设计要点**：
- 与对话树主题切分**共享原语**（SegmentIR）：EDU + 粘合度 ≈ TextTiling 对话版；不重复实现两套切分逻辑。
- 意图切分与对话树主题切分**同构**：发出时即可区分意图，不必等回复后再切——这是阶段 1 存在的理由。

---

## 5. 子图协同：C/S 被动架构（拍板 4/9/10）

### 5.1 架构

- **PCR = 客户端**：主动开通道，向子图/关联链请求"预期上下文"。
- **子图 = 服务端**：收到请求后回应预期上下文先验（坐标偏置）。
- **非事件订阅/推送**：主动拉取解耦清晰、时序可控、降级明确。

### 5.2 协议

```
请求  PCR → 子图:  { domain_scope: { domains, budget } }   # PCR 定的口径
响应  子图 → PCR:  { prior: { coordinate_bias, expected_context } }  # 预期上下文先验
```

- PCR 决定子图**口径**（选域/预算），不决定子图**内容**（编译是 SubgraphCompiler 的活）。
- 子图反哺的是**预期上下文先验**（坐标偏置），反过来协同 PCR 判断。
- 约束：**同轮只拉一次 + 超时降级**（拉不到 → 纯结构坐标兜底，不阻塞）。

### 5.4 服务端现状核查（2026-08-01 实测）

- **现有接口**：`core/agent/compiler/subgraph_compiler.py` 只有 `compile(query, max_tokens)` 全量编译；`core/agent/v4/cognitive/subgraph_compiler.py` 只有 `compile_dialogue(intent, extra_budget)`。**均无"按 domain_scope 拉取预期上下文先验"的 pull API** → §9 P1 需新增 `pull_prior(domain_scope) → SubgraphPrior`。
- **domains 枚举来源**：v4 编译器内部硬编码分配比例 `{D:0.35, K:0.20, E:0.05, B:0.15, R:0.10, P:0.10, F:0.05}`（discourse/engineering/knowledge...），数据来自引擎内部对象（`_discourse_tree`/`_engineering_knowledge` 等）。**新设计不沿用硬编码比例**：domains 由"主题树域 + 关联链规则"枚举，PCR 只传选域结果。
- **budget 依据**：v4 现为 `self._budget`（默认 2000）+ `extra_budget`；新设计预算 = 域权重 × 轮次预算，权重可配（§8.1）。

### 5.3 反哺收敛（拍板 9）

```
快照(当前坐标) → 拉取预期上下文先验 → 校正(一轮) → 收敛
```

- 只做**一轮快照→校正**收敛，防死循环（不做迭代式互相修正）。
- 校正后的坐标仅作为本轮输出，不反向写回子图触发再拉取。

---

## 6. 关联链协同：双向（拍板 5）

- **PCR → 关联链**：PCR 是 L3 粗处理，产出（坐标/标签/骨架）作为关联链 L3 的**初始值**，防重复计算。
- **关联链 → PCR**：关联链凝练出规则，辅助 PCR 粗处理（规则作为维度计算器的可注入先验）。
- **定位**：关联链是 NLP 处理核心；PCR 只负责 L3 粗处理，两者双向但不越权。

```
PCR(粗) ──坐标/标签/骨架──→ FusionEngine L3（初始值）
   ▲                            │
   └──── 凝练规则辅助 ────────────┘
```

- 事件：`pcr_computed`（PCRResult 完整产物）→ 关联链 FusionEngine 消费。

---

## 7. 接口协议

### 7.1 route() 契约（统一）

```
route(text, *, external_skeleton=None, subgraph_prior=None) → PCRResult
```

- **默认路径（内部粗切）**：route 内部先做 §4 阶段 1 粗切并产出 segment 骨架——骨架是 PCR 自己的产物，不是输入。
- **外部注入路径**：`external_skeleton` 仅在"上游（对话树等）已有切分"时传入复用；外部存在则优先，PCR 只做衔接修正，不与内部产出混在一个参数里。
- `subgraph_prior`：子图反哺先验（§5）。
- 输出：PCRResult（§2.3 字段），含坐标、zone、labels、segments、domain_scope。
- 只吃 text 是 v2 的短板，新设计必须接受骨架输入/产出。

### 7.2 事件

| 事件 | 载荷 | 消费者 |
|------|------|--------|
| `pcr_computed` | PCRResult | 关联链 FusionEngine（L3 初始值）、路由/API |

### 7.3 消费方适配策略

- 新契约统一走 `route() → PCRResult`（zone + labels + segments）。
- 旧契约消费方（`evaluate(PCRInput_v1)`：mcp/service/tools/gates）暂不改，v2 成为唯一主实现后走适配或归档。
- 已知类型错配：`RuleBasedPCR.evaluate(query: str)` 与旧消费方传 `PCRInput_v1` 不符——归档旧包时一并处理。

---

## 8. 权重配置与验证基准（拍板 6/7）

### 8.1 权重 YAML（示例）

```yaml
dimensions:
  x_distance:
    enabled: true
    weight: 1.0
    calculators:            # 主/备/兜底 fallback 栈
      - { name: nomic_cos, weight: 0.5, enabled: true }
      - { name: idf,       weight: 0.3, enabled: true }
      - { name: entity_density, weight: 0.2, enabled: true }
  y_granularity:
    weight: 1.0
    formula: { verb: 0.4, entity: 0.3, wordcount: 0.3, caps: [5, 5, 20] }
  z_temperature:
    weight: 1.0
    calculators:
      - { name: lm_studio_nomic, weight: 0.6, enabled: true }
      - { name: bge,             weight: 0.4, enabled: true }
      - { name: nrc_vad,         weight: 0.0, enabled: false }   # fallback 链

zone_thresholds:             # 基线 = 设计文档值（与 coordinate_router 一致）
  atomic: { x: 0.2, y: 0.2, adaptive: true, vmin: 0.05, vmax: 0.35 }   # 设计文档 DESIGN_V4.0 / coordinate_router
  abyss:  { x: 0.7, y: 0.7, z: 0.5, adaptive: true, vmin: 0.55, vmax: 0.85 }  # 同上
  # 注: pcr_router_v2 实现为"放宽版" (x<0.3,y<0.3; x>0.7,y>0.6,z>0.3)
  #     属待校准差异，不作基线；最终以黄金样例集回归定稿 (§8.2)

adaptive:                    # A18 自适应闭环（拍板 2026-08-01）
  engine: parameter_registry # 主用 ParameterRegistry（EMA observe/adapt + 策略预设）
  tier: hot|warm|cold        # 参数自身热冷分层（RFC §8）
  cooldown_sec: { hot: 60, warm: 600, cold: 3600 }
  min_samples: 3             # 最少采样数才触发调整
  step: 0.02                 # 单次调整步长（复用 DeltaAdjuster 模式）
```

### 8.2 验证基准（黄金样例集）

- 建立黄金样例集（覆盖 6 zone × 典型意图类别 × 中英文本），每条标注期望 zone/labels。
- - 权重调整必须对照黄金样例集回归，否则"调了等于没调"。

**首批草案样例（10 条，覆盖 6 zone × 中英；期望值为草案，随阈值拍板与真实输出校准后定稿，P2 测试直接引用定稿版）**:

| # | 文本（中/英） | 期望 zone | 期望 labels | 备注 |
|---|--------------|----------|------------|------|
| 1 | 删除这个文件 / delete this file | ATOMIC | 温度中/距离近/价值中 | 单意图原子指令 |
| 2 | 把上个月所有未读邮件归档并生成报表 | PRECISION | 温度低/距离近/价值高 | 多步任务 |
| 3 | 量子退火在物流调度里到底怎么用 | EXPLORE | 温度低/距离远/价值中 | 跨域探索 |
| 4 | 帮我查一下人类存在的意义相关的论文 | ABYSS | 温度中/距离远/价值高 | 深域开放问题 |
| 5 | 我好烦，什么都不想做 | PSYCHE | 温度负/距离近/价值低 | 情绪主导 |
| 6 | 你知道昨天新闻里说的那个模型吗，随便聊聊 | MIXED | 温度中/距离中/价值低 | 混合意图 |
| 7 | How to deploy k8s cluster with terraform | PRECISION | 温度低/距离近/价值高 | 英文多步 |
| 8 | why do cats purr | EXPLORE | 温度中/距离远/价值中 | 英文轻探索 |
| 9 | fix the bug in auth module please | ATOMIC | 温度低/距离近/价值高 | 英文原子指令 |
| 10 | I feel exhausted and want to quit everything | PSYCHE | 温度负/距离近/价值低 | 英文情绪 |

### 8.3 验证策略

- **做完再检验**：先落地再验证，不边做边凑。
- **旧测试定性为"作假"**：恒真断言（不判 zone、类名错恒真）全部重做。
- 补**真实路由断言**：route() 的坐标/zone 逐条断言期望值（当前从未被真实断言）。
- zone 阈值三套不一致（0.2/0.2 vs 0.3/0.3）→ 以 YAML 定死一套并断言。

### 8.4 自适应闭环（A18 落地，2026-08-01 拍板）

**引擎**: ParameterRegistry（EMA observe/adapt + 策略预设），详见 `PCR_ADAPTIVE_AUDIT.md`

**三套参数系统拍板**:
- 主用 `core/agent/compiler/parameter_registry.py`（EMA 防抖 + 策略预设 + 已被 v4 world 使用 + 有单测）
- `adaptive_parameter.py` 保留（pipeline_api/cli 在用，不改不删）
- `v3_2/un_use/parameter_registry.py` 清理候选（后续归档）

**双轨信号**:
- 快信号（Hot/Warm 参数）: 黄金样例 zone 命中率 → observe() → adapt()（EMA 防抖，警惕过拟合样例集）
- 慢信号（Warm/Cold 参数）: CorrectionJournal 用户 zone 修正率 + 下游任务成功率 → 回流（A18 量化分层：用户反馈是最终真相）

**触发源（双上）**:
- 元认知周期扫描: 复用 `v4/cognitive/metacognition.py` 现有回路（消费 CorrectionJournal + DynamicsComputer）检测 zone 误判率漂移
- 行为链 drift: 复用 `DeltaAdjuster`（±0.02/50 轮模式，来自 CausalSubstrate）

**防震荡**: min_samples + cooldown（Hot 1min / Warm 10min / Cold 1h）+ clamp(vmin,vmax) + 步长有界

**审计**: Event Log + per-param change log（slow_path.threshold: 5→3→7 格式）+ CLI 白盒（dm pcr config show/set/reset，A19）

**最小接入路径**:
```
P0: 魔法数参数化 → 全部权重/阈值注册为 ParamDef（带 vmin/vmax）
P1: 快信号接线（黄金样例 → observe/adapt）
P2: 慢信号接线（CorrectionJournal 用户修正 → 回流）
P3: 元认知扫描 + 行为链 drift（复用现有回路 + DeltaAdjuster）
P4: 审计（Event Log + change log + CLI 白盒）
```

---

## 9. 改造落点（对齐 PCR_REFACTOR_PREP_MAPPING.md）

### 9.1 P0 接线修复（让 PCR 首次真实进入生产路径）

| # | 文件 | 改动 |
|---|------|------|
| 1 | `cli/registry.py:260` | `_pcr_factory` 返回 PCRRouterV2（现挂 PCRLLM 空壳 ❌） |
| 2 | `engineering_bridges.py:31` | `PCRV2Router` → `PCRRouterV2`（类名拼错，ImportError 被吞） |
| 3 | `orchestrator/agent_native.py:141` | 去掉 `override=`；`.x/.y/.z` → `x_axis/y_axis/z_axis`（现恒 0.5） |
| 4 | `event/handlers.py:72` | handle_pcr 消费 PCRResult（zone + labels），不再恒 MIXED |

**双 registry 遗漏（必须两处都改）**：
- `start_engine()` → `registry.py:260`（挂错实现）
- `_create_engine_instance()` → `subsystem_registrations._registry`（完全没注册 pcr，PCR 不执行）

### 9.2 P1 设计落地

| # | 文件 | 改动 |
|---|------|------|
| 5 | `pcr_router_v2.py` | PCRResult 加 labels（温度/距离/价值罗盘） |
| 6 | `pcr_router_v2.py` | 维度声明式注册 + 权重可配置（YAML） |
| 7 | `pcr_router_v2.py` | route 输入加 segment 骨架（子图/上下文先验） |
| 8 | `api/v6_app.py` | /v6/pcr 输出罗盘标签 |
| 9 | `cli/commands/pcr_intent_cmd.py` | cmd_pcr_route 改调 route() 非 process() |
| 10 | `cli/commands/batch4_cmd.py` | `_pcr_llm` → `_pcr_router`（5 处） |

**P1 补充（§5.4 核查结论）**：
- `core/agent/v4/cognitive/subgraph_compiler.py` 新增 `pull_prior(domain_scope) → SubgraphPrior` 接口；现有 `compile_dialogue` 的 alloc 硬编码比例不沿用，domains 由主题树域 + 关联链规则枚举。

### 9.3 P2 测试重写（假测试清零）

| # | 文件 | 改动 |
|---|------|------|
| 11 | `tests/test_pcr_v2.py` | `test_v2_routing`（不断言 zone）+ `test_compare_old_pcr`（类名错恒真）→ 真实断言 |
| 12 | `tests/test_pcr_v2_dedicated.py` | 13 tests 逐一审，补 zone 阈值断言 |

### 9.4 不改（明确排除）

- `pcr/` 旧包（interface/datacontract/lifecycle…）— 归档候选
- `router/router_v4.py` — DEPRECATED
- `router/coordinate_router.py` — 影子实现（若合并进 v2 则删）
- 旧契约消费方：`mcp/server.py`、`service/agent_service.py`、`tools/cognitive_tools.py`、`v3_common/gates.py`

### 9.5 执行顺序

```
第 1 步: 修 4 个接线点 (P0) + 重写假测试 (P2) 合并执行
        → 接线后立刻用真实 zone 断言验证（接线是否成功以断言为准）
第 2 步: 旧包/旧契约归档（P0 后立即做，避免 mcp/service 继续引用 RuleBasedPCR）
第 3 步: pcr_router_v2 改造 (P1) → 维度可插拔 + 罗盘标签 + segment 骨架
第 4 步: 子图 pull_prior 接口（§5.4）+ 关联链 pcr_computed（设计落地）
第 5 步: 黄金样例集定稿 + 全量回归
第 6 步: 自适应闭环接入 (§9.6) —— 魔法数参数化 + 双轨信号 + 三重触发
```

### 9.6 自适应接入（A18，2026-08-01 拍板）

| # | 文件 | 改动 |
|---|------|------|
| 13 | `pcr_router_v2.py` | 全部魔法数 → ParamDef 注册（ParameterRegistry，带 vmin/vmax/tier） |
| 14 | `pcr_router_v2.py` | 快信号：黄金样例 zone 命中率 observe/adapt |
| 15 | 新 adapter | 慢信号：CorrectionJournal 用户 zone 修正 → 回流 |
| 16 | `v4/cognitive/metacognition.py` | zone 误判率漂移 → 调整阈值（复用现有回路） |
| 17 | `association/delta_adjuster.py` 或新适配 | 行为链 drift → 步长调整（±0.02/50轮） |
| 18 | `cli/commands/pcr_intent_cmd.py` | dm pcr config show/set/reset（白盒 A19） |

---

## 10. 糅合来源索引

### 10.1 保留（PCRRouterV2 工程骨架）

- 四级降级链 + fallback 栈（维度计算器可换的工程形态）
- LLM 补全闸门（实体 = 0 才调 LLM）
- LLM 协同审查（模型大小感知，偏差 > 0.3 覆盖）
- 零硬编码 + 形态学启发式（中文动词偏低需修）
- route(text) → PCRResult 契约（但维度必须可插拔）

### 10.2 废弃/修正

- X 轴隐性退化为 entity_density → 必须显式定义（语义距离 or 词汇新颖度）
- zone 阈值三套不一致（v2 放宽版 vs 设计值 0.2/0.2、0.7/0.7/0.5）→ 以设计值为基线 + 黄金样例集校准 + 断言

### 10.3 借鉴主流（神经符号收敛方向，2026-08-01 深读修正）

- **outlines / 约束解码**：**生成时 logits mask**（采样阶段排除非法 token），不是输出后校验——PCR LLM 输出应加 JSON Schema 约束（§3.3.4）
- **Snips NLU**：**三态解析器并存 + ProcessingUnit 注册机制**（deterministic/probabilistic/lookup 同一接口）——PCR 维度计算器升级为独立 unit（§3.1）
- **pi（Pi Agent Harness）**：compaction 保留行为证据 + 技能 XML 清单懒加载（详见 DEEP_READ_COMPARISON_20260801.md，吸收进 L5/Skill 层）
- **Rasa DIET**：生产级意图分类，特征与分类解耦
- **Haystack routers**：路由组件化（维度/路由逻辑复用）
- 共识方向：**确定性先行 → LLM 分类（生成时约束）→ 结构化输出**

### 10.4 文献（已核实）

- Shi2023：7-30B 在语法标签任务上呈 U 型（中间带受益）→ 支持"算法先跑 + LLM 只在低信号时介入"
- ~~Min2024 / 348 篇元分析~~：查无此文，弃用

### 10.5 主题切分（阶段 2/3 依据）

- EDU + 粘合度 ≈ TextTiling 对话版
- DTS 主流已 LLM 化（Def-DTS / CobSeg）
- 建议 SegmentIR 共享原语，意图切分与对话树切分共用一套底层

---

## 附：与旧设计的核心差异

| 维度 | 旧设计 | 新设计 v0.1 |
|------|--------|------------|
| 产出 | 单视图坐标 | 双视图（坐标 + 罗盘标签，并列计算） |
| 维度 | 三轴写死 | 声明式注册、可插拔、权重 YAML |
| 切分 | 无/回复后再切 | 三阶段渐进（粗切 → 异步细化 → 后验维护） |
| 子图 | 无协同 | C/S 主动拉取预期上下文先验 |
| 关联链 | 无 | 双向：L3 粗处理 + 规则辅助 |
| 验证 | 恒真断言（作假） | 黄金样例集 + 真实路由断言 |
| 参数 | 魔法数硬编码 | ParameterRegistry 注册 + 双轨自适应 + 三重触发 |