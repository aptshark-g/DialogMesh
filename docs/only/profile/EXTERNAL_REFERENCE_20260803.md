# 外部参考：Hermes / Pi / snips-nlu 的画像与意图实现 — 2026-08-03

> 目的：画像内核拍板前，对照成熟项目实装。回答"画像/意图在现实中是怎么做的"。
> 研究对象（本地源码，非二手资料）：
> - **Hermes**（Nous Research agent，完整源码在 `C:\Users\APTShark\AppData\Local\hermes\hermes-agent`）——画像/记忆最成熟
> - **Pi**（earendil-works，openclaw 核心，`C:\tmp\oss-ref\pi`）——编码 agent 框架，画像弱
> - **snips-nlu**（`C:\tmp\oss-ref\snips-nlu`）——经典意图 NLU（LogReg + CRF），意图最成熟
> 方法：逐文件精读 + rg 引用追踪（与画像审计同法）。

---

## 一、Hermes 画像实现（核心资产，最值得吸收）

### 1.1 本体：双文件 bounded memory（MEMORY.md + USER.md）

```
MemoryStore（tools/memory_tool.py）
  ├─ MEMORY.md  ← "MEMORY (your personal notes)"    预算 2200 chars
  ├─ USER.md    ← "USER PROFILE (who the user is)"  预算 1375 chars  ← 画像本体
  ├─ 条目分隔符 "§"，文件即列表，append-only add / 定位 replace / 精确 remove
  ├─ 每轮 system prompt 注入两块（volatile 段）
  └─ 写门控（approval gate 可选）+ 注入扫描 + 外部漂移防护
```

**关键设计决策**：
1. **画像就是一段短文本列表**，不是多维向量。USER.md 每条目一句话（"User prefers concise responses"）。
2. **预算即边界**：超预算时工具返回"请合并/删除后重试"，由 LLM 自己完成 consolidation（同一轮内）。
3. **快照冻结**：`_system_prompt_snapshot` 在 load 时冻结，会话内不随写入变化 → prefix cache 稳定。工具响应反映 live 状态，system prompt 反映 load 时状态。
4. **注入防护**：`_sanitize_entries_for_snapshot` 对快照做威胁匹配，命中条目替换为 `[BLOCKED: ...]` 占位；live 列表保留原文供用户查看/删除（不静默丢弃攻击证据）。
5. **防循环**：`_MAX_CONSOLIDATION_FAILURES_PER_TURN = 3`，超限返回终态"本次不存了，继续回复用户"——记忆副作用永远不阻塞主回复。

### 1.2 写入规范（MEMORY_GUIDANCE，prompt_builder.py:151）

```
"Save durable facts: user preferences, environment details, tool quirks, stable conventions."
"Prioritize what reduces future user steering — the most valuable memory prevents
 the user from having to correct or remind you again."
"Do NOT save task progress, session outcomes, PR numbers, 'fixed bug X', anything
 stale in 7 days."
"Write memories as DECLARATIVE FACTS, not instructions: 'User prefers concise
 responses' ✓ / 'Always respond concisely' ✗."
"Procedures and workflows belong in SKILLS, not memory."
```

**画像写入三大原则**：
- **减少未来 steering 优先**（用户纠正过/提醒过的，一等信号）
- **声明式事实，非指令**（避免下个会话把画像误读为 directive）
- **技能/记忆分工**：谁（persona/desires/preferences）→ 记忆；怎么做（workflow/procedure）→ 技能

### 1.3 后验维护（background_review.py，核心机制）

```
每轮结束 → spawn_background_review_thread（fork 一个 AIAgent）
  ├─ _MEMORY_REVIEW_PROMPT：persona / desires / preferences / 行为期望
  │    → 用 memory 工具写入（target=user 或 memory）
  ├─ _SKILL_REVIEW_PROMPT：风格纠正 / 工作流纠正 / 技巧 → skill_manage patch
  │    "User-preference embedding: 偏好嵌入 SKILL.md body，不只存 memory。
  │     Memory captures WHO the user is; skills capture HOW to do this class
  │     of task FOR this user."
  └─ 工具白名单仅 memory + skill；危险命令 auto-deny；写元数据
      （write_origin=background_review / execution_context / session_id）
```

**这是"LLM 后验学习"的成熟落地**：不打断主对话（后台线程），fork 独立 agent 评估"这轮该学什么"，写画像/技能。对应我们公理 A6 后验学习 + 元认知周期扫描。

### 1.4 冷启动（onboarding.py）

```
首次消息 → profile_build_directive() 注入 system note：
  "OFFER — do not assume — to build a short profile"
  consent-gated：同意才问；外部查询前逐项征求同意；拒绝即停
  → memory 工具 target="user"，条目紧凑高信号
```

**对应我们的冷启动设计**（信息不足时 llm 模拟用户前瞻）——Hermes 用"主动询问 + consent gate"而非模拟。

### 1.5 周期触发（turn_context.py nudge）

```
_memory_nudge_interval = 10（可配置）
每用户轮 ++_turns_since_memory；≥10 时 should_review_memory=True 并清零
（turn_context.py:336-343；skill nudge 同理，counter 在 skill_manage 使用时重置）
```

### 1.6 大规模策展（curator.py，86KB）

```
run_curator_review → fork AIAgent（max_iterations=9999, quiet_mode）
  - 扫描数百候选技能：分类（active/archive/prune/merge/absorbed_into）
  - _MEMORY_REVIEW / _SKILL_REVIEW 双 prompt 驱动
  - 自动转换（apply_automatic_transitions）+ 结构化摘要 + 运行报告
  - 保护：bundled/hub 技能只读；pin 阻止删除但允许改进
```

### 1.7 学习图（learning_graph.py）

```
SkillNode（name/category/source/profile|base/use_count/state/pinned/related）
  + memory cards（MEMORY.md / USER.md 每 § 块 = 一个节点，source="profile"）
  + memory↔skill 边：token 交集 + 技能名包含匹配，top-4 连边
  → 桌面学习面板：profile 学习的技能 + 记忆块 + 连接关系
```

### 1.8 画像进上下文（context_breakdown.py + system_prompt.py）

```
build_system_prompt_parts：stable（skills 索引）/ context / volatile（memory + USER + 时间戳）
context_breakdown：memory 是独立分类（_chars_to_tokens），可见 memory 块占比
```

### 1.9 Hermes 的意图实况

```
❌ 无显式 intent parser / intent 分类器 / 意图状态机
✅ 意图处理 = LLM 原生决策（工具路由由模型自己完成）
✅ intent_ack_continuation = "用户说继续/接着做"的 continuation 机制（agent_runtime_helpers）
✅ 上下文参考（context_references.py）承担"找相关历史"职责，非意图分类
```

**结论**：Hermes 走了"LLM-first 无显式意图层"路线（与我们新包 Agent-Native 同向），画像则是"规则边界 + LLM 写入"的务实混合。

---

## 二、Pi（openclaw 核心）画像与意图实况

```
画像：
  ❌ 无 UserProfile / 画像持久化模块（编码 agent 场景弱需求）
  🟡 questionnaire.ts（examples/extensions）= L4 主动询问工具
     （单题选项列表 / 多题 tab 导航 / allowOther 自由输入）→ 画像获取的 UI 载体
  🟡 compaction（branch-summarization + compaction.ts）= 会话摘要压缩
     （非画像，是对话历史降维；cut 点选择 + 结构化摘要 prompt）
意图：
  ❌ 无显式意图分类；工具路由 = LLM 原生（与 Hermes 同）
  🟡 session tree（fork/回放）承担"上下文选择"，非意图
```

**结论**：Pi 是基础编码 agent，画像/意图都不是一等公民——它的价值在会话结构（tree/fork）与摘要压缩，可参考其 compaction 的"结构化摘要 prompt"设计。

---

## 三、snips-nlu 意图实现（经典 NLU，与旧 8 阶段同范式）

### 3.1 架构：双解析器串行（nlu_engine.py）

```
SnipsNLUEngine.parse →
  ① DeterministicIntentParser（保守规则：高精度低召回，简单模式即中）
  ② ProbabilisticIntentParser（机器学习兜底：LogReg 意图分类 + 每意图 CRF slot filler）
  → 第一个给出正输出的 parser 胜出
```

### 3.2 ProbabilisticIntentParser 两步（intent_parser/probabilistic_intent_parser.py）

```
fit：IntentClassifier.fit(dataset) + 每 intent 一个 SlotFiller.fit(dataset, intent)
parse：intent_classifier.get_intent(text) → 对应 slot_fillers[intent].get_slots(text)
  → 意图分类与槽位填充解耦（分类后只跑该意图的填充器，省算力）
```

### 3.3 LogReg 意图分类（intent_classifier/log_reg_classifier.py）

```
LogRegIntentClassifier（多分类逻辑回归）
  Featurizer = TF-IDF（intent_classifier/featurizer.py:241 TfidfVectorizer）
              + 词共现向量（_fit_cooccurrence_vectorizer）
  get_intents → softmax 概率分布；支持 intents_filter（意图白名单）
  log_best_features / log_activation_weights = 可解释性工具
```

### 3.4 与我们的对照

| snips-nlu | 我们（意图审计结论）|
|---|---|
| 确定性 parser 优先（高精度低召回）| layer0 Gate-0 硬规则 Fast Path（同思路，我们已有设计）|
| LogReg + TF-IDF/共现 | 旧 8 阶段规则（断链）；新包 LLM-first（未接）|
| 分类→每意图 slot filler（解耦省算力）| 旧版 Stage 规则流程（未解耦）|
| intents_filter 白名单 | 我们的 5 链验证 + fusion_decider（更复杂）|
| 可解释（best features 日志）| A18 白盒要求（我们设计有，实现无）|

---

## 四、三方对照总表

| 维度 | Hermes | Pi | snips-nlu | 我们的现状 |
|---|---|---|---|---|
| 画像本体 | USER.md 文本列表 | 无 | 无（槽位）| 三套分裂（OCEAN/行为侧/user_engine）|
| 画像预算 | 1375 chars 硬边界 | — | — | 无预算概念（to_llm_context 全量）|
| 画像写入 | LLM 工具调用（declarative facts）| — | — | OCEAN LLM 评分 EMA / 规则 EMA / 无写入规范 |
| 画像后验 | background_review fork agent（每轮）| — | — | 设计有（A6），实现无 |
| 画像冷启动 | onboarding consent-gated 询问 | questionnaire L4 | — | 设计有（llm 模拟前瞻），实现无 |
| 画像策展 | curator（大规模 LLM review）| — | — | 无（inertia_graph 设计类此，未喂数据）|
| 画像防护 | 注入扫描 + 快照冻结 + 防循环 | — | — | 无 |
| 意图范式 | LLM 原生（无显式层）| LLM 原生 | 确定性→概率两段式 | 三主线未收敛（规则/贝叶斯/Agent-Native）|
| 意图可解释 | — | — | best features 日志 | 设计有（白盒），实现无 |
| 记忆/技能分工 | 明确（who→memory, how→skill）| — | — | 未明确（画像/行为链/对话树边界待拍板）|

---

## 五、对我们的启示（画像内核拍板前必读）

### 5.1 画像本体建议（强吸收 Hermes）

1. **USER.md 式"画像=短文本事实列表"比 OCEAN 浮点更可操作**：OCEAN 10 维浮点对 LLM 是"模糊数字"，Hermes 的"用户偏好简洁回复"是"直接可用的事实"。建议画像内核 = **事实条目列表（bounded）+ 维度投影（OCEAN 作投影层）**，不是二选一。
2. **预算即边界 + LLM 自 consolidation**：1375 chars 硬上限，超了让 LLM 合并/删除——这是 A18 参数自适应的务实替代（比我们的权重注册表更简单有效）。
3. **写入规范必须显式注入**：declarative facts / 减少未来 steering / 7 天时效 / who-vs-how 分工——我们 200 篇设计里没有这么清晰的画像写入 prompt。
4. **后验 = background_review 模式**：fork agent 每轮后台评估"该学什么"，不阻塞主回复——直接对应我们 A6 后验 + 元认知周期扫描，且已含工具白名单/写元数据/危险命令 deny 等工程细节。

### 5.2 画像/意图边界建议

5. **记忆/技能分工语义可直接借用**："Memory captures who the user is; skills capture how to do this class of task for this user"——映射到我们：画像（who）+ 行为链/技能（how）明确分工，解决画像/行为链边界模糊问题。
6. **意图层选型证据**：Hermes/Pi 都走 LLM 原生无显式层；snips-nlu 证明"规则优先 + 概率兜底"在小意图集有效。我们的意图内核应确认：确定性边界（layer0 Gate-0）+ LLM 灰区（Agent-Native）混合 = 两者的综合，方向正确但需按 snips 的"分类→每意图处理器解耦"精简。
7. **注入防护进画像设计**：画像/记忆文件可能被污染（supply chain / 跨会话写），Hermes 的快照冻结 + 占位替换是白盒安全的具体模板（对应我们安全公理）。

### 5.3 不吸收项

8. Hermes 的"无显式意图层"不适合我们（我们有多链/子图/对话树协同，需要意图类别做路由输入）；但可吸收其"减少未来 steering"作为意图价值判据。
9. Pi 的 questionnaire（L4 主动询问）与我们的冷启动 llm 模拟互补：模拟（默认） + 询问（灰区）双轨。

---

## 六、吸收落地清单（画像内核拍板备料）

| # | 吸收项 | 落点 | 对应拍板项 |
|---|---|---|---|
| H1 | USER.md 事实列表 + 预算边界 + LLM consolidation | 画像本体重构（替换/并行 OCEAN 浮点）| 拍板 1（三套归一）|
| H2 | declarative-facts 写入规范 prompt | 画像写入引导（新 prompt）| 拍板 2 |
| H3 | background_review fork 后验模式 | 画像后验（A6 落地）| 拍板 4 |
| H4 | onboarding consent-gated 冷启动 | 画像冷启动（补模拟路径）| 拍板 5 |
| H5 | 注入扫描 + 快照冻结 + 防循环 | 画像存储安全（P12/安全公理）| 拍板 3 |
| H6 | who-vs-how 分工语义 | 画像/行为链/对话树边界 | 拍板 6 |
| S1 | 分类→每意图处理器解耦 | 意图内核精简（融合 L3）| 意图拍板 |
| S2 | best-features 可解释日志 | 意图白盒化（A18）| 意图拍板 |
| P1 | 结构化摘要 prompt（compaction）| 对话树摘要/温度系统 | 对话树拍板 |

---

*本文件是画像审计外部参考成果；与 AUDIT_ENTRY / IMPLEMENTATION_AUDIT / DESIGN_AUDIT 共同构成画像审计资产。来源均为本地源码精读（Hermes / Pi / snips-nlu）。*
