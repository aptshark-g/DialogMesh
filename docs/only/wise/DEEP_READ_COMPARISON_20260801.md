# 深读对比：pi × outlines × snips-nlu × DialogMesh

> 深读日期: 2026-08-01
> 素材: C:\tmp\oss-ref\pi（Pi Agent Harness, earendil-works）+ C:\tmp\oss-ref\outlines（约束解码）+ C:\tmp\oss-ref\snips-nlu（意图解析）
> 结论先行: **我们之前对主流的学习停在"清单级"——写了借鉴方向，但没读实现，导致 2 处方向性误读；pi 的 compaction/skills 与我们 A24/A8 哲学高度共鸣，值得深吸收。**

---

## 一、pi（Pi Agent Harness）— agent 运行时

### 1.1 核心机制（源码级）

| 机制 | 实现 | 位置 |
|------|------|------|
| 统一消息模型 | 所有消息（user/assistant/tool_result/compaction/branch_summary）都是 `AgentMessage`，**只在 LLM 调用边界 `convertToLlm` 转换** | `packages/agent/src/agent-loop.ts` |
| 会话树 | `SessionTreeEntry` 序列化（message/compaction/branch_summary/model_change...），支持 **branch/fork 可回溯** | `packages/agent/src/harness/session/session.ts` (528L) |
| 压缩 | `compact()` 保留**文件操作状态**（readFiles/modifiedFiles）+ 序列化会话 + 生成压缩摘要 + `retainedTail` 保留尾部 | `packages/agent/src/harness/compaction/compaction.ts` (880L) |
| 技能注入 | skills 以 `<available_skills>` XML 列表注入 system prompt（name/description/location），**模型按需读 SKILL.md（懒加载）** | `packages/agent/src/harness/system-prompt.ts` (34L) |
| 工具循环 | agent-loop：工具调用 → tool_result → 继续；retry + stream 事件 | `agent-loop.ts` + `agent-harness.ts` (1185L) |

### 1.2 与 DialogMesh 的深层次对照

| pi | DialogMesh | 差异点（深度） |
|----|-----------|----------------|
| 会话树 + compaction | 对话树 + L5 压缩 | **pi 压缩保留"文件操作状态"（行为证据），不只留摘要**——对应 A24 可逆推性：压缩要能反推行为链。我们 L5 压缩保留的是实体/意图，未显式保留"改了什么文件" |
| `<available_skills>` XML 懒加载 | DESIGN_SKILL_LAYER 技能选择 | pi 的做法是"清单注入 + 模型自决读不读"，我们更偏"规则选技能"——两者可糅合：清单注入 + 规则预筛 |
| 统一消息模型 | PCRResult/事件契约 | 同构（分层抽象，边界转换），我们已在做 |

### 1.3 可深吸收点

- **P0**: 压缩时保留"行为证据"（modifiedFiles/action 列表）——升级 L5 压缩的可逆推性（A24 落地）
- **P1**: 技能 XML 清单注入 + 模型懒加载——与 A8 表达形式哲学直接对应，且实现成本低

---

## 二、outlines — 约束解码（结构化生成）

### 2.1 核心机制（源码级）

| 机制 | 实现 | 位置 |
|------|------|------|
| 约束编译 | JSON Schema / regex / CFG 编译为 logits processor | `generator.py` + `backends/get_*_logits_processor` |
| **生成时 mask** | 在生成**每个 token 时**用约束 mask 非法 token（不是生成后校验！） | `processors/base_logits_processor.py` |
| 张量抽象 | tensor_adapter 统一 mlx/numpy/torch | `base_logits_processor.py` |
| 双模型 | BlackBoxGenerator（无约束）/ SteerableModel（约束） | `generator.py` |

### 2.2 深层次对照（修正我们的误读）

**DESIGN_PCR §10.3 我们写的**: "outlines / 约束解码：LLM 输出后结构化校验/解码，作为后验维护手段"

**实际 outlines 做的事**: **生成时约束**（logits masking）——在采样阶段就排除非法 token，根本不会产生非法输出。这不是"输出后校验"，是"输出前约束"。**我们写反了方向。**

| outlines | DialogMesh | 差异点（深度） |
|----------|-----------|----------------|
| 生成时 mask 约束 | PCR LLM 协同审查（生成后偏差>0.3 覆盖） | outlines 是硬约束（符号编译成 token 级 mask），我们是软校验（生成后比对）——**神经符号糅合的极致形态** |
| CFG 引导生成 | 无 | 对话树/意图结构可编译成 CFG 约束 LLM 输出 |

### 2.3 可深吸收点

- **P1**: PCR LLM 输出加 schema 约束（zone/labels 用 JSON Schema 约束生成，杜绝格式错误）——从"生成后校验"升级为"生成时约束"
- **P2**: 对话树结构 → CFG 引导主题切分输出（Def-DTS 方向 + outlines 实现）

---

## 三、snips-nlu — 意图解析

### 3.1 核心机制（源码级）

| 机制 | 实现 | 位置 |
|------|------|------|
| **三态解析器并存** | deterministic（规则，快/可解释）/ probabilistic（统计）/ lookup（查找）——同一接口，注册机制可插拔 | `intent_parser/*.py` |
| 两步管线 | ProbabilisticIntentParser = IntentClassifier（意图分类）→ SlotFiller（槽填充） | `probabilistic_intent_parser.py` (250L) |
| 注册机制 | `@IntentParser.register("probabilistic_intent_parser")` + ProcessingUnit 抽象 | `intent_parser.py` (85L) |

### 3.2 深层次对照

| snips-nlu | DialogMesh | 差异点（深度） |
|-----------|-----------|----------------|
| 三态解析器（deterministic/probabilistic/lookup） | PCR 维度计算器 fallback 栈（主/备/兜底） | **同构**！snips 做得更彻底：parser 是独立 unit，引擎按配置选；我们 fallback 栈在同一函数内 |
| IntentClassifier → SlotFiller | 关联链 L3 意图 → 子图口径 | 我们意图后是"子图/上下文组装"，snips 是"槽填充"——功能目标不同，但"分类→提取"两步结构可借鉴 |
| ProcessingUnit 注册 | SubsystemRegistry | 同构（声明式注册） |

### 3.3 可深吸收点

- **P0**: PCR 维度计算器 fallback 栈升级为"独立 parser unit + 注册表"（对齐 snips 的 ProcessingUnit 模式）——与 §3 维度声明式注册合并
- **P1**: 意图分类 → 槽填充两步，映射到"意图 → 子图口径"——PCR 产出 domain_scope 可视为"槽"（域/预算）

---

## 四、跨项目对比总表

| 维度 | pi | outlines | snips-nlu | DialogMesh 现状 |
|------|----|----------|-----------|----------------|
| 核心抽象 | 统一消息 + 会话树 | logits mask 约束 | 三态 parser + 注册 | 事件契约 + fallback 栈 |
| 压缩/抽象 | 保留行为证据 + 摘要 | — | — | L5 压缩（未保留行为证据） |
| 技能/知识注入 | XML 清单懒加载 | — | — | Skill 层（规则选技能） |
| 约束机制 | — | 生成时 mask | — | 生成后软校验 |
| 可插拔性 | 工具/skill 插件 | — | ProcessingUnit 注册 | SubsystemRegistry |

---

## 五、我们"表面学习"的自我修正

1. **outlines 误读（方向性）**: §10.3 写"输出后校验"——实际是"生成时 mask"。修正后：PCR 应从"生成后比对"升级为"生成时约束"。
2. **snips 只抄了方向**: "确定性特征 + 分类器 + fallback"——深读后真正值得抄的是 **ProcessingUnit 注册机制 + 三态并存**，不是 fallback 顺序。
3. **pi 完全没读**: 我们的"技能/压缩"设计没对照 pi 的 compaction（保留行为证据）和 XML 技能清单——pi 的实现直接验证了 A24/A8。

---

## 六、深吸收落地建议（按优先级）

| 优先级 | 吸收点 | 落地位置 |
|:---:|--------|---------|
| P0 | 压缩保留行为证据（modifiedFiles/action） | L5 压缩 + A24 落地 |
| P0 | PCR 维度计算器 → 独立 unit + 注册表 | DESIGN_PCR §3（对齐 snips） |
| P1 | PCR LLM 输出 JSON Schema 约束（生成时） | DESIGN_PCR §3.3（对齐 outlines） |
| P1 | 技能 XML 清单注入 + 懒加载 | Skill 层 + A8 |
| P2 | 对话树结构 → CFG 引导切分输出 | 三阶段切分（对齐 Def-DTS + outlines） |


---

## 七、openclaw（pi 的扩展）深读 — 记忆架构（memory-architecture.md + dreaming + compaction + standing-intents + context-engine）

### 7.1 openclaw 扩展了 pi 什么

| 层 | pi | openclaw 扩展 |
|----|----|--------------|
| 控制面 | 无 | Gateway（单常驻，WS 协议 + TypeBox→JSON Schema→Swift 代码生成，配对/设备信任） |
| 通道 | 无 | 25+ 通道（WhatsApp/Telegram/Slack/Discord/Signal/iMessage/WebChat） |
| 记忆 | 无 | memory-core：五层 tier + provenance + dreaming 凝练 + 双通道召回 + standing intents |
| 技能 | skills.ts | ClawHub 生态（5400+ skills） |
| 安全 | 无 | DM pairing / sandbox（docker/ssh/openshell）/ 结构性 provenance 门控 |

### 7.2 记忆架构五原则（与公约逐条对照——openclaw 独立实现了我们的核心公理）

| openclaw 原则 | DialogMesh 公约 | 判定 |
|--------------|---------------|:---:|
| No hidden state（模型只记得写入文件的东西，每面可检查可编辑） | A19 白盒化 | ✅ 验证 |
| Writing is the hard part（写入时策展 > 检索；策展移出回复路径进后台） | A15 温度 + A24 逆向动力 | ✅ 验证 |
| Write path is the security boundary（写入时强制 provenance，结构性门控非事后检测） | A21 安全 + A23 溯源置信 | ✅ 验证 |
| Deterministic gates, model judgment inside them | P2 算法与 LLM 不同颗粒度 + A18 | ✅ 验证 |
| Failures never block replies（记忆挂了降级不吞回合） | A16 不阻断 | ✅ 验证 |

**结论：我们的 25 公理不是"感觉上不错"——openclaw 用 5 条原则独立收敛到了同一批哲学。**

### 7.3 五层 tier（对照 A15 温度 / A7 分治）

| openclaw tier | 写入者 | 注入 | DialogMesh 对应 |
|---------------|--------|------|----------------|
| Instructions（AGENTS.md） | 人 | 始终 | 系统指令 |
| Curated core（MEMORY/USER.md） | dreaming 凝练 | 始终，预算内 | Hot（全量内存） |
| Episodic（daily notes） | agent/flush | 永不，按需搜索 | Warm/Cold（可加载） |
| Prospective（standing intents + cron） | intent 工具 | 仅触发时 | **我们缺（见 7.6）** |
| Review（DREAMS.md） | dreaming | 永不，给人读 | Archive（审计） |

### 7.4 provenance 与结构性安全（A21/A23 的工程答案）

- **Origin class 闭集**：owner/agent/untrusted/system 存 SQLite 列，模型不能通过散文伪造——"散文声称是 owner 的 ≠ owner 内容"
- **Session-kind 门控**：cron/heartbeat/subagent 会话不产生持久记忆候选（防脚手架噪音）
- **Recall-loop prevention**：从记忆注入的内容结构化标记，永不重新提取为新记忆——被召回 100 次还是一个事实（= P5 冻结知识不再参与竞争）
- **taint 通过凝练传播**：dreaming 的 gate 检查候选 provenance 不只是分数——untrusted 无法经 daily note 洗白进 MEMORY.md

### 7.5 双通道召回（A25 的工程答案）

- **Lane 1（零模型调用）**：bootstrap 注入 + 混合检索 × 指数衰减（30 天半衰期）× importance 乘数 + trigger 注入（词法/向量预筛，score≥0.72 注入隐藏块，每轮≤3）
- **Lane 2（escalation）**：两个确定性条件（回忆意图 + Lane 1 无强命中）才跑真子 agent——昂贵通道只花在值得的地方（LongMemEval 证据：时序/多跳问题正是扁平检索最弱处）

### 7.6 前瞻记忆 standing intents → 我们已有：行为链 + 冷启动模拟 + 共塑造式（2026-08-01 拍板修正）

- **定义**：事件条件化的未来动作（"当提到 launch checklist 时提醒确认 rollback owner"）——前瞻记忆，不是时钟调度
- **编译出模型（compile intentions out of the model）**：time-based → cron；event-based → SQLite（关键词/嵌入/scope/expiry/fire budget/cooldown）；aspiration → Markdown + review date
- **匹配路径零模型调用**：确定性 FTS 预筛 + 同步事务检查 scope/expiry/cooldown/fire budget
- **取消是持久状态非模型判断**（ProEvent 证据：主动系统过度主动 + 事件取消困难）
- **防烦扰是结构性的**：24h cooldown / 3 fires / 90d expiry / 每轮≤3 注入
- **引用证据**：TriggerBench（前瞻回忆随上下文增长衰减，会漂移成"总是提醒"启发式）

**对比（用户拍板修正）**：前瞻记忆我们已有——行为链（BUSINESS_CHAIN_05）就是干这个的：不仅提供过去信息分析，还做了冷启动设计（信息不足时用 LLM 模拟用户行为前瞻）。而且我们有更深的设计：共塑造式（co-shaping）——LLM 的回复与问题反向塑造用户的回答和思考，双重维度：其一过往历史（I2）、其二当下内容反馈（I3）；冷启动时其一不足则用 LLM 模拟。画像可学，但是单用户设计。

### 7.7 USER.md 格式契约（画像的警示）

- 命令式指令（Always/Never/Prefer）而非观察
- **更新就地替换（supersede in place）**，绝不追加矛盾版本——追加偏好历史会让模型答旧值（PrefEval ICLR 2025）
- 每次带状态元数据（观察日期、active/superseded）
- **两条文献证据**：PrefEval（arXiv:2502.09597）——偏好遵循随对话长度迅速衰减，即使有检索和提示；HorizonBench（arXiv:2604.17283）——系统常选用用户已改变的旧偏好，append-only 矛盾历史会重现该失败模式

**警示**：我们 BUSINESS_CHAIN_09 画像有 per-dim EMA history（append-only 式）——需对照此证据核查是否会让模型答旧值。

### 7.8 深层次对比结论

1. **openclaw 验证了公约核心**：白盒/写入即安全/确定性门控+模型在内/不阻断/冻结知识，全部有工程实现和文献支撑——我们不是"感觉上不错"。
2. **我们缺前瞻记忆维度**：standing intents 是独立的记忆机制，我们意图体系没有"事件触发"。
3. **openclaw 给了我们缺的工程答案**：provenance 的 SQLite 列实现、trigger 注入阈值（0.72/每轮3）、30 天半衰期、fire budget、supersede in place。
4. **画像 append-only 警示**：我们的 per-dim EMA history 可能违反 supersede in place 原则。

### 7.9 理论参考：认知-行为公理化体系（内部伪理论框架）

> 来源: `.hermes/desktop-attachments/认知-行为公理化体系（完善完整版）.txt`（56KB）—— 单用户画像的内部理论基础

| 公理化体系概念 | DialogMesh 对应 | 意义 |
|----------------------|---------------------|-----------|
| 双网络激活比 R_{D/E}（DMN 发散 / ECN 收敛） | A24 伪二阶抽象（DMN 发散→ECN 收敛→启发链） | **量化基础**：R_{D/E}>1 联想发散，R_{D/E}<1 理性执行 |
| 外部输入集 I(t0)={I1 输出指向, I2 历史互动, I3 当前语境, I4 第三方} | 共塑造式双重维度（I2 过往历史 + I3 当下反馈） | 用户行为模型的输入结构 |
| 情绪指数 Em = v(E实 - E内)（前景理论） | PCR Z 轴情绪温度（NRC-VAD） | 情绪量化的理论根 |
| 主体固有锚定集 A(S)={A1 人格, A2 三观, A3 身份, A4 背景} | 画像 OCEAN + 三观 | 画像的稳定层 |
| 双惯性系统 + 惯性成本 + 最小作用量原则 | 行为惯性（A15 温度多因子） | 行为预测的理论支撑 |
| 预期失衡 ΔE = E实 - E内 | A13 长证明后验的信念更新 | 预期与信念的连接 |


### 7.10 multi-agent 路由（多人格隔离设计，对标单用户与多模块边界）

- **agent 边界 = workspace + state + session + skills allowlist**：每个 agent 独立 workspace（AGENTS/SOUL/USER.md）、独立 agentDir（auth/model registry）、独立 SQLite 会话库、独立 skills 白名单；入站消息经 **bindings** 路由到对应 agent
- **“sessions_history 是更安全的跨会话召回路径”**：返回有界、脱敏的视图而非原始转写（剔除 thinking-block 签名、工具结果详情、<relevant-memories> 脚手架、工具调用 XML 标签）——对应我们 A21 安全的“召回时脱敏”维度
- **警示：不可复用 agentDir**：跨 agent 共用状态目录会导致 auth/session 冲突
- 对标：单用户设计下，我们的“模块边界”对应它的“agent 边界”——但我们是单用户但多认知模块的分工，而非多人格隔离


---

## 八、待讨论清单（2026-08-01 攒）

| # | 议题 | 证据/来源 | 关联 |
|---|------|-----------|------|
| 1 | 画像 append-only → supersede in place 改造 | PrefEval + HorizonBench（§7.7）vs BUSINESS_CHAIN_09 per-dim EMA history | A6/A15 |
| ✓ | **已拍板：数值 EMA 历史（时序视角，元认知漂移检测）+ 指令层 supersede（语义视角，模型当前生效值）共存 = 一个事实多视角（A1）** | 拍板 2026-08-01 | A1/A6/A15 |
| 2 | 前瞻记忆：是否借鉴 standing intents “编译出模型”结构（我们已有行为链 + 冷启动模拟 + 共塑造式） | §7.6 | A9/A13 |
| 3 | PCR 生成时约束（outlines logits mask）已吸收进 DESIGN_PCR §3.3 | §二 | A8 |
| 4 | 压缩保留行为证据（pi compaction modifiedFiles）→ L5 落地 | §一 | A24 |
| 5 | 召回时脱敏（sessions_history 有界脱敏视图）→ A21 维度补充 | §7.10 | A21/A19 |


### 7.11 steering queue（转向队列，对标 A16 冷热编排）

- **steer 模式（默认）**：运行中收到新消息 → 注入活动运行时，在**模型边界（工具批结束后）**drain，不打断正在跑的工具调用
- **为什么等当前 batch（三条设计理由）**：
  1. 工具批是一个工作单元，取消 = 半应用状态，下一步必须重做整批
  2. 每个工具调用保持真实结果，丢弃 = 伪造 aborted 结果，模型会把合成失败当真
  3. 上下文保持 append-only，steered 消息追加尾部，**provider prompt cache 保持有效**
- **四种模式**：steer（注入）/ followup（等运行结束）/ collect（合并兼容消息 debounce）/ interrupt（中止当前运行）
- **Burst 处理**：4 条消息同时来 → 下个模型边界按到达顺序 drain

**对标 A16：与我们“不阻断 + 后补修正”完全同构**
- openclaw steer = “修正应用到下一个模型步，而不是取消已请求的工具调用” = 我们“后补修正不覆盖已给回答，只影响未来 Tick”
- **新增工程价值点**：append-only 上下文 + prompt cache 保持有效（A17 事件溯源的额外收益）
- collect（合并兼容消息）对应我们的意图合并（A13 信念聚合）


### 7.12 session 管理（会话路由与生命周期，对标对话树/会话管理）

- **会话路由**：DM 共享 / 群组隔离 / 房间隔离 / cron 新会话 / webhook 隔离；identityLinks 映射多渠道同一用户
- **DM 隔离等级**：main（所有 DM 共享）/ per-peer / per-channel-peer / per-account-channel-peer（多用户必开，否则私密涌出）
- **会话生命周期**：不自动重置（默认，compaction 管活跃上下文）/ 每日重置 / 空闲重置；**新鲜度基于真实用户交互，heartbeat/cron/exec 不延长会话）
- **rememberAcrossConversations**：跨会话检索但**不合并 transcript**；私密 DM 可互相提供上下文，群组/频道双向隔离（隐私边界 A21）
- **会话重置时丢弃旧会话的排队系统事件**：避免 stale 后台更新混入新会话首条 prompt（A16/A17 一致性）
- **incognito sessions**：内存会话，不落盘/不 memory flush/不 archive（隐私模式）

**对标**：“什么算活动”的定义（真实用户交互 vs 系统事件）——对应 A15 温度访问频率维度的精确定义；跨会话检索不合并对应我们 L5/A25 的跨会话召回，隐私隔离对应 A21


### 7.13 SOUL.md 人格注入（对标画像/共塑造式的“声音”层）

- **SOUL.md = 声音层**：语气/观点/简洁/幽默/边界/直率程度——与 AGENTS.md（操作规则）分离；每次会话注入
- **写法原则**：短胜过长，锐利胜过模糊；讲行为效应的事，不讲人生故事/安全政策堆码
- **与我们的对应**：声音层（SOUL）vs 操作层（AGENTS）的分离 → 对应我们的“表达形式哲学 A8”+“行为第一公民 A9”（语气是行为的一部分）；对应共塑造式：人格注入反向塑造用户感知（“2am 想对话的助手”）
- **警示**：人格不是糊弄的允许证；公共场合声调要配合场景
