# 待拍板清单总表 — 对话树 / 意图 / 画像（2026-08-03）

> 目的：把三模块审计沉淀的拍板项统一列出，逐个解决。
> 来源：discourse_tree/（KERNEL_ABSORPTION + IMPLEMENTATION_AUDIT + DESIGN_AUDIT）、intent/（AUDIT_ENTRY + IMPLEMENTATION_AUDIT + DESIGN_AUDIT）、profile/（AUDIT_ENTRY + IMPLEMENTATION_AUDIT + DESIGN_AUDIT + EXTERNAL_REFERENCE）。
> 用法：每项含"问题 / 选项 / 当前建议 / 关联"。拍板后在表中标记 ✅ 并写 DECISIONS 文档。

---

## 零、跨模块关联（先看清依赖再逐个拍）

```
画像 ←→ 对话树：组块边界 ← 认知状态；摘要 = 个体化记忆痕迹（KERNEL §九）
画像 ←→ 意图：L3 _profile_vote（OCEAN C）；SubIntent.chain_votes[profile]
意图 ←→ 对话树：primary_intent 来源；话题切换信号；域选择；compass（4 接口全断）
画像 ←→ PCR：P4 双向先验（画像反哺 PCR + PCR 注入画像）
意图 ←→ PCR：D-14 zone→intent 先验已通（唯一闭环）
对话树 ←→ 行为链：树操作 diff（A17）；激活计数喂行为链
```

**建议拍板顺序**（依赖驱动）：
```
① 意图内核范式（意图是对话树/画像的输入源，先定）
② 画像本体归一（画像被对话树/意图/PCR 消费，次定）
③ 对话树内核组装（消费意图+画像，最后定）
```

---

## 一、意图模块拍板项（9 项）

| # | 问题 | 选项 | 建议 | 关联 |
|---|---|---|---|---|
| I1 | 意图范式 | 确定性优先 / LLM-first / 认知双工 | ✅ **三时相结构（见下）** | 对话树切分信号 |
| I2 | 四套类别归一 | IntentCategory（旧）/ SubIntent.category（新）/ expectation（PCR）/ prompts 16 类 | ✅ **种子集 + 行为链补种（见 R2）** | 对话树 primary_intent |
| I3 | 新包接线 | engine 是否启用 dual_track 热路径 | 启用；补 llm 缺失时诚实降级（现全 pass 静默）| — |
| I4 | 旧 8 阶段去留 | 修复 registry 断链复活 / 新包替代 | 新包替代，旧版归档 un_use | — |
| I5 | 5 链验证补全 | fusion_decider/ambiguity_gate 零引用 | 接入 multi_intent_splitter（A4 多链投票），不再 trust LLM | 画像 profile 链 |
| I6 | PCR 调控恢复 | 9 模块调控点 | 至少 fusion/ambiguity 两处落地 | PCR |
| I7 | 意图↔对话树 4 接口 | primary_intent 来源 / 话题切换 / 域选择 / compass | 定一来源 + 三维模型接入切分 + 域选择恢复 | 对话树 I 组 |
| I8 | shim 清理 | 11 引用方防御式 / 全切新包 | 全切新包 + 显式降级日志 | — |
| I9 | 测试补全 | intent/ 10 文件无专属测试 | 按 v2 §11.1 标准补 + 黄金示例集 | — |

### 意图补充（IMPLEMENTATION_AUDIT §八 交叉项）
| # | 问题 | 说明 |
|---|---|---|
| I10 | 自适应阈值两套归一 | v3_common GP+MLP（632L）vs coordinator Bayesian——选一或分层 |
| I11 | 多意图拆分验证 | splitter 跳过 5 链验证（trust LLM）vs 文档要求规则为主 |
| I12 | 认知双工形态 | ENGINEERING §9.2 规则∥LLM vs 新包 coordinator 单 LLM 调用 |

---

## 二、画像模块拍板项（12 项 + 外部吸收）

| # | 问题 | 选项 | 建议 | 关联 |
|---|---|---|---|---|
| P1 | 画像本体归一 | OCEAN 10 维 / 惯性权重图 / 双轨 Track A+B / user_engine 字段 | 事实条目列表（bounded）+ OCEAN 投影层 + 惯性图行为模式层（H1）| 对话树/意图/PCR 全消费 |
| P2 | _cognitive_profile 复活 | CognitiveProfileV2 生产路径接线 vs 废弃 | 吸收到统一内核（Track A 认知状态层）| 引擎 |
| P3 | PROFILE_GAP 修正 | 95% → 实测 30-40% | 更新文档（A18 诚实）| — |
| P4 | L3 profile 视角接线 | engine validate() 传 profile_traits | OCEAN dims → conscientiousness 映射 | 意图 I5 |
| P5 | 对话树组块边界 ← 认知状态 | 疲劳/注意力/惯性接入 | Track A 认知状态层供组块判据（KERNEL §八.8.4）| 对话树 |
| P6 | P4 双向先验落地 | PCR→TrackA EMA + 画像→3D 路由偏置 | 双向都做（公理级）| PCR |
| P7 | inertia_graph 喂数据 | 6 视角 evidence 源拍板 | 行为链/关联链/对话树/元认知/LLM/工程链 | 行为链/关联链 |
| P8 | ContextCompiler P 域 | 注册 ProfileContextSource / 统一子图路径 | 注册 + 与子图 P/F 域同源 | 子图 |
| P9 | v2 双轨 11 模块去留 | 全吸收 / 部分废弃 | llm_profile_analyst/signal_filter 已死；tag_layer/dynamics/convergence 吸收 | — |
| P10 | g 因子领域化 | domain 相对 | 领域细分（coding/math/...）| — |
| P11 | CLI 死命令 + 双名注册 | p4/p10 签名对齐 + registry 归一 + save 挂载 | 修 | — |
| P12 | 画像测试 | 黄金示例集先行 | OCEAN/user_engine/双轨家族补真实断言 | A18 |

### 画像外部吸收（EXTERNAL_REFERENCE H 系列）
| # | 吸收项 | 说明 |
|---|---|---|
| H1 | USER.md 事实列表 + 预算 + LLM consolidation | 画像本体重构核心（P1 细化）|
| H2 | declarative-facts 写入规范 prompt | 新增画像写入引导 |
| H3 | background_review fork 后验 | A6 后验落地（每轮后台评估）|
| H4 | consent-gated 冷启动 | 画像冷启动（补 llm 模拟路径）|
| H5 | 注入扫描 + 快照冻结 + 防循环 | 画像存储安全 |
| H6 | who-vs-how 分工 | 画像=who / 技能=how（化解画像↔行为链边界）|

---

## 三、对话树模块拍板项（13 项）

| # | 问题 | 选项 | 建议 | 关联 |
|---|---|---|---|---|
| D1 | 输入源 | 原文（现实现）/ Observation/Dialogue 域产物 | 待定（两套设计契约未对齐）| 认知管线 |
| D2 | primary_intent 来源 | SyntacticDecomposer 规则 / B 层 LLM | 定一（吃意图 I2/I7 产物）| 意图 |
| D3 | 分裂归一内核骨架 | A 单体门面 / B 拆包 / C 编译器 | C 编译器 + B 管理 + A 接线（IMPLEMENTATION_AUDIT §五）| — |
| D4 | PCR 调控 | 接不接 PCR 信号 | 接：噪声→切分敏感度、期望→attach 倾向 | PCR |
| D5 | 温度多因子权重 | 时间×访问×主题×语义唤醒 | 合成规则 + BGE>0.8 回 Hot（C4 修复）| 行为链/画像 P5 |
| D6 | 摘要边界 | 只做轻量 v1-v3 / v4 命题压缩给记忆侧 | v1-v3 + 记忆侧 v4（平衡点三问 1）| 画像/子图 |
| D7 | 温度接口边界 | 对话树暴露缩放建议 / 自己做压缩 | 暴露接口，记忆侧执行（平衡点三问 2）| 温度系统 |
| D8 | 灰区决策 | 单阈值快路径 + 四象限 / A13 长证明后验 | 快路径 + 灰区走 A13 跨轮收敛（C2 修复）| 意图 I1 |
| D9 | 链与树关系 | 注解层 / 节点内建 chains | 注解层为事实源，块级 chains 仅缓存视图 | 关联链 |
| D10 | DualStructure 吸收 | 事实轨+逻辑轨+虚拟边 | 吸收（A12/A17 落点）| 执行层 |
| D11 | 三范式标签输出 | [温度·距离·信息价值] | 采纳（compass 已实现，修 C6 字段名）| 罗盘 |
| D12 | ContextCompiler 域接口 | get_domain_C(意图类别) | 落地（预算 60/25/15 下游规格）| 子图 |
| D13 | P0 验证集 | 黄金示例集三测 V1/V2/V3 | 先建（A18）| — |

### 对话树施工项（非拍板，修复清单）
```
P0: 2 腐坏测试 + C6 字段名统一（v3_evolution vs v3_milestone）
P0: 内核组装路线（C+B+A）
P1: C2 灰区修复 / C4 温度语义唤醒
P2: C5 四级摘要行为链元信息 / C9 attach 落地（B classify_quadrant 已就绪）
```

---

## 四、统计与依赖

```
意图 12 项（I1-I12）· 画像 18 项（P1-P12 + H1-H6）· 对话树 13 项（D1-D13）
跨模块共享依赖（先拍这些）：
  I1/I2/I7（意图范式+类别+接口）→ 解锁 D2/D4/D12
  P1/P4/P5（画像本体+L3+认知状态）→ 解锁 I5/D5/D7
  P6（P4 双向先验）→ 解锁 PCR 侧
```

---

*本清单是后续 DECISIONS 文档的骨架。每拍一项，回填标记并记入对应模块 DECISIONS。*

---

## 五、已拍板决议

### R1 — I1 意图范式：三时相结构（2026-08-03 拍板）

```
意图范式 = 三时相混合（非三选一）

T0 Fast 产出（确定性边界）:
  三维模型 / 规则 / BGE 快匹配 → 初始意图（毫秒级，不阻塞）
  对应 layer0 Gate-0（>0.95 硬规则 Fast Path）

T1 Async 验证（LLM 回答窗口）:
  L3 MultiPerspectiveValidator（4 视角：discourse/profile/association/pcr）
  + 5 链验证（profile/association/discourse/literal/engineering）
  → 修正意图（回答期间异步跑，不增加首响延迟）

T2 后验修正:
  若 T1 发现 T0 错 → 回写（意图类别更新 + tree_annotation + profile_update）
  若 T1 漏 → 用户反馈/行为结果 → T2 修正
  对应 A16（快反馈后补修正）+ A13（长证明后验）
```

**可插拔白盒设计（编排哲学）**：
- 默认提供完整三时相（完整方案）
- 可跳过 T0 → 只做 T1 全验证（最准确，成本最高）
- 可关闭 T1 → 只用 T0 + T2（省 token，用户反馈兜底）
- 时相开关 = 参数（A18）；每个时相是白盒节点，用户可截断改接 LLM/多 agent（A19）
- 成本语义：T1 = token 换准确性；T2 = 后验开销换回收——用户按场景取舍

**与已有资产关系**：layer0 Gate-0/Gate-2 是 T0/T1 雏形；L3 4 视角是 T1 验证器（engine 已接，但同步）；A16/A13 是 T2 哲学。**缺口 = T1 移到回答窗口异步 + T2 回写实现**。

### R2 — I2 意图类别：种子集 + 行为链补种（2026-08-03 拍板）

```
意图类别体系 = 种子集（默认 6 类） + 行为链补种（可演化）

分层（绑定 I1 三时相，每套一套粒度）:
  T0 → expectation（服务模式，最粗: TOOL/ADVISOR/COMPANION，PCR 毫秒可判）
  T1 → SubIntent.category（6 类: 诊断/修复/探索/吐槽/信息查询/指令，L3 4 视角粒度）
  T2 → sub_intent 细节（子任务级，后验回写补充）
  prompts 16 类 → 仅作 T1 LLM 自由输出参考，不作为强制分类体系
  IntentCategory（旧 8 阶段）→ 断链产物，归档 un_use

可演化（分类体系不是天花板）:
  泛化不足信号: ① 灰区比例高 ② 用户频繁纠正 ③ other/unknown 堆积
  → 行为链补种: 跨会话重复行为模式 → 提议新类别
     （类别名 + 特征描述 + 证据序列）
  → 走 inertia_graph 生命周期: candidate → confirmed(≥3 视角) → stable(≥5 视角)
  → 注册进类别注册表（A18），T1 分类器下次可用

护栏（防类别爆炸）:
  新类别须满足: 重复≥N 次 + 跨≥2 视角 + 能解释历史样本（A24 可逆推）
  类别带版本/来源/证据字段，可归档（不活跃 → candidate 降级）
  扩展走 T2 后验时相，不阻塞 T0/T1；失败即丢弃
```

**哲学对应**：聚类（行为重复）→ 凝练（命名+特征化）→ 反向验证（解释历史样本）= 二级抽象/逆向动力系统在意图域的落地。

**画像侧开口（H6 延伸）**：同一机制可给画像补种——行为链模式提议"画像事实条目"（who 侧：用户反复展示的稳定偏好/模式 → 提议 USER.md 事实），候选确认后写入画像。画像 P7（inertia 喂数据）与 I2 共用同一生命周期机制。

### R3 — I3 意图新包接线：按三时相落位（2026-08-03 拍板）

```
不引入"dual_track 总开关"，改为各文件按 I1 三时相落位:

T0（Fast 确定性边界）:
  现有 layer0 Gate-0 + PCR expectation + BGE 快匹配（不动，已存在）

T1（Async 验证/融合）:
  coordinator（单次 LLM 调用全上下文）= T1 主执行器
  multi_intent_splitter = T1 多意图拆分（接入 5 链验证，I5 执行项）
  ambiguity_gate（5 触发器）= T1 灰区判定（pass/auto/llm/ask_user 升级决策）
  fusion_decider（三策略 + PCR 调控）= T1 融合裁决（当前零引用，激活）
  L3 MultiPerspectiveValidator（4 视角）= T1 验证器（engine 已接，移异步）

T2（后验回写）:
  L3 feedback（tree_annotation + profile_update）= 回写通道（现成，激活）
  意图类别更新 + 行为链补种（R2）

无 LLM 诚实降级（修复静默退化）:
  现状: if not self.llm: return pass/单段（静默）
  改为: 显式降级日志 + 回退 T0 规则路径，T1 标记 degraded
        （A6/A18 诚实原则，不允许无痕降级）
```

**与 R1/R2 一致性**：T0 不动（已有）、T1 激活零引用金矿（fusion/ambiguity）、T2 接现成回写通道。接线范围明确 = 激活 fusion_decider + ambiguity_gate + 拆分验证补全 + L3 异步化。

### R4 — I7 意图↔对话树 4 接口：通用通道 + 订阅矩阵（2026-08-03 拍板）

```
T1 意图产物 → 4 个发布通道（EventLog/EventBus 落点，Phase 6 M→1 模式可复用）

① primary_intent 通道
   默认订阅: 对话树（块级 primary_intent）
   可订阅:   子图（域选择锚点）/ 元认知（review 对象）/ 行为链（预测输入）

② 话题切换信号通道（类别突变 + layer0 三维模型）
   默认订阅: 对话树（组块边界）
   可订阅:   关联链（细化切分触发）/ 子图（重编译触发）/ 温度系统（唤醒）

③ 域选择通道（intent + zone）
   默认订阅: ContextCompiler（域 C 权重）
   可订阅:   子图（P/F 域）/ 规划器（策略选择）

④ compass intent_novelty 通道（intent_history）
   默认订阅: 罗盘（信息价值）
   可订阅:   温度系统（驻留调整）/ 行为链（前瞻预测）
```

**拍板语义**：
- 通道 = 意图产物的发布，不强制任何模块消费
- 默认订阅集合 = 可配置白盒（A18/A19），模块可自由增减订阅
- 落地复用：蓝图 EventBus + 关联链 Event Sourcing（M→1 定向通道）已在位，意图 T1 产物写入即广播/定向投递
- 意图不是谁的子模块，而是与其他模块平等的生产者（关联链=NLP 核心，意图=信号源之一，子图/元认知/对话树=订阅方）

**对四接口的具体落位**：
- primary_intent 来源 = L3 tree_annotation.topic（T1 产物，现成通道）
- 话题切换信号 = 类别突变 + 三维模型（组块边界最精确判据，供 D4/D5 消费）
- 域选择输入 = L3 产物（intent + zone）喂 ContextCompiler（D12 get_domain_C 输入源）
- compass intent_novelty = T1 intent_history 喂罗盘（engine 已注入，补历史）

### R5 — P1 画像本体：四层合一（2026-08-03 拍板）

```
画像本体 = 四层（事实层为基底，其余为投影/派生）

① 事实层（USER.md 式，who）—— 唯一可写基底
   H1 吸收: 事实条目列表 + 预算边界 + LLM consolidation
   R2 画像开口: 行为链模式补种事实条目
   写入规范: declarative facts / 减少未来 steering / 7 天时效（H2）

② 人格投影层（OCEAN 10 维 + MBTI）—— 从事实层派生 / LLM 评分
   消费方: 子图 P/F 域（现活）/ L3 _profile_vote（P4 接线）/ 意图新包 profile 参数
   现状: CLI 路径 OCEANProfileAnalyst 逐轮评分（保留为写入口之一）

③ 认知状态层（Track A 动力学）—— 注意力/疲劳/惯性，动态
   消费方: 对话树组块边界（P5）/ 3D 路由偏置（P6）
   现状: DynamicsComputer 9 维计算已实现（纸面），复活接线

④ 行为模式层（inertia 惯性权重图）—— 跨链稳定模式
   消费方: 参数覆盖 / 设计约束 / 各链阈值微调
   现状: InertiaWeightGraph 完整，挂载未喂（P7 喂数据源）

层级关系:
  事实层（可读可写）→ 其余三层（投影/派生，可计算、可配置）
  OCEAN 逐轮评分 = 事实层写入口之一（保留），非唯一
```

**对应 PENDING_DECISIONS 画像项**：
- P2（_cognitive_profile 复活）→ Track A 吸收为认知状态层（③）
- P9（v2 双轨 11 模块去留）→ dynamics/tag_layer/convergence 吸收到 ③④；llm_profile_analyst/signal_filter 废弃
- P10（g 因子领域化）→ 行为模式层标签（领域相对），执行项
- P12（画像测试）→ 四层各配黄金示例集断言，执行项
- H3（background_review 后验）→ 事实层维护机制（P 后验）
- H4（consent-gated 冷启动）→ 事实层冷启动（P 冷启动）
- H5（注入扫描+快照冻结）→ 事实层存储安全（P 存储）
- H6（who-vs-how）→ 事实层=who，行为链/技能=how（边界化解）

### R6 — 对话树 D1/D2/D3：输入源 + primary_intent + 内核骨架（2026-08-03 拍板）

```
D1 输入源:
  默认: 原文（T0 事件层，毫秒级粗切）
  可选注入先验: PCR 意图信号（expectation）+ 画像偏置（Track A 认知状态）
  Observation/Dialogue 域产物 = 替代输入源（白盒可配置，与 I1 可插拔哲学一致）
  契约: ingest_turn(原文 + 可选先验 → 块级结构 + 缩放建议)

D2 primary_intent 来源:
  主: T1 意图产物（R4 ① primary_intent 通道 = L3 tree_annotation.topic）
  兜底: SyntacticDecomposer 规则提取（无 LLM / T1 未产出时，T0 语义）
  定一: 不再有两套并存，T1 通道为主、规则兜底

D3 分裂归一内核骨架:
  组装: C 编译器（decompose/inject 完整实现）
        + B 管理（ingest_turn/ProgressiveSummary/cross_ref/四象限）
        + A 接线（engine/CLI/API/compass 门面）
  D 孤儿 → 归档 un_use
  E DiscourseManager → 保持废弃（unified_context 已取代）
  关键修复随组装: C6 字段名统一（v3_evolution vs v3_milestone）
                  + C2 灰区修复（不误 fork，走 A13 后验）
                  + C4 温度语义唤醒（BGE>0.8 回 Hot）
```

**对话树模块拍板完成**（D1-D13 全部落位：D4 PCR 调控=R1 T0 先验；D5 温度权重=R5 ③+行为链联动；D6/D7 摘要与温度接口=KERNEL 平衡点三问已定；D8 灰区=R1 T1；D9 链树关系=注解层；D10 DualStructure 吸收；D11 三范式标签；D12 get_domain_C=R4 ③；D13 验证集=执行项）
