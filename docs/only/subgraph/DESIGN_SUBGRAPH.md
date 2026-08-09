# DESIGN_SUBGRAPH.md — 子图新设计（施工主文档 v0.1）

> 状态: **v0.2 施工完成**（2026-08-01 P0-P1 全部落地 + 40 测试含对抗性）
> 来源: `SUBGRAPH_DESIGN_OVERVIEW.md`（设计梳理）+ `SUBGRAPH_DEEP_INVESTIGATION.md`（实现审计）
>        + v3 设计源（DESIGN_CROSS_DOMAIN_CONTEXT / DESIGN_V4_CONTEXT_ENGINEERING）
> 定位: 子图改造的设计主文档，实现时对照 §9 落点执行
> 拍板: 建完整 · v4 原基础改造 · 质量优先 · 先把现有设计实现到匹敌
> 完成度: §9.2 落点 11/11 ✅ · §9.5 执行顺序第 1-7 步完成 · 第 8 步（死代码归档）暂缓（§12）

---

## 0. 文档导览

| 章节 | 内容 |
|------|------|
| §1 定位与职责边界 | 子图是什么、干什么、不干什么 |
| §2 设计核心 | 视角/意图矩阵/cross_ref/预算/修剪/降落（v3 完全体） |
| §3 数据契约 | DomainEntry / SubgraphContext / ContextIR v2 / SubgraphPrior |
| §4 接口协议 | compile_dialogue / compile_meta / pull_prior |
| §5 与 PCR 协同 | domain_scope ↔ pull_prior ↔ X 轴先验 |
| §6 预算与配置 | alloc YAML + 三层预算 + Provider 自适应 |
| §7 结构修剪 | 四轮修剪 + 三步降落 |
| §8 验证基准 | 黄金样例 + 真实断言 |
| §9 改造落点 | P0/P1/P2 清单 + 执行顺序 |
| §10 糅合来源索引 | v3 设计源对照 |

---

## 1. 定位与职责边界

**一句话定位**: 子图是跨链通信的"认知编译引擎"——从共享数据池按当前意图
选择域组合，编译为带 cross_ref 指针的统一信息网络（Context IR），供 LLM
生成回复或元认知审核。**不是数据存储，不是 RAG 检索，是"构造局部世界"**。

### 1.1 职责边界表

| 做（子图职责） | 不做（交给其他模块） |
|---------------|----------------|
| 意图感知的域选择（矩阵） | 意图分类本身（PCR/IntentParser） |
| 跨域上下文抓取 + cross_ref 指针 | 数据源的内容生成（对话树/行为链各自维护） |
| 预算约束下的信息选择与结构修剪 | 最终回复生成（LLM） |
| 双视角编译（dialogue 窄深 / meta 宽浅） | 主题精切分（对话树/关联链） |
| 反哺先验（pull_prior）给 PCR | 全文检索（RAG） |

### 1.2 三条关键约束

1. **视角是本质**：同一数据池，不同视角不同分配——对话树子图（窄深）与元认知
   子图（宽浅）不可合并。
2. **结构完整性优先**：预算内修剪必须保 cross_ref 网络连通（betweenness 保护），
   不能像扁平文本一样截断。
3. **意图感知，非平均分配**：域选择按意图矩阵（主 60%/辅 25%/辅 15%），
   alloc 可配置不硬编码。

---

## 2. 设计核心（v3 完全体）

### 2.1 意图感知域选择矩阵

| 意图 | 主域 60% | 辅助1 25% | 辅助2 15% | 策略 |
|------|---------|----------|----------|------|
| task | E(工程) | B(行为) | P(画像) | 深度聚焦 |
| query | C(对话) | E(工程) | P(画像) | 话题锚定 |
| correction | B(行为) | E(工程) | K(因果) | 因果回溯 |
| discussion | P(画像) | C(对话) | E(工程) | 广度发散 |
| casual | C(对话) | P(画像) | — | 轻量组织 |
| topic_switch | C(全树) | B(行为) | P(画像) | 结构重建 |

- 矩阵是默认推荐，用户画像修正历史可覆盖（AdaptiveParameter 调权重）
- intent 类别输入来自 PCR/intent 解析（对齐 DESIGN_PCR §5）

### 2.2 cross_ref 指针网络

```
[E:MODULE] ModuleA
  status: monitor_missing, translation_ok
  ^ref: B.event_87 = 用户前3轮连续调整此模块
  ^ref: P.profile = 偏好可视化调试而非日志
```

- 每条 entry 带 `cross_refs: [{target_domain, target_event_id, note}]`
- cross_ref 双向，LLM 收到可导航子图网络，而非独立段落
- source_events + confidence + estimated_tokens 随 entry 记录

### 2.3 三层预算

| 层 | 预算 | 内容 |
|----|------|------|
| 必要层 | 200 | 用户消息，不可裁剪 |
| 策略层 | 300 | 跨域子图，意图感知分配（60/25/15） |
| 弹性层 | 200 | 溢出用，预算充足时启用 |

- Provider 自适应: DeepSeek 800-1000 / GPT-4 400-500 / 本地 1500+ / 默认 500-700
- 用户习惯推断 + 显式设置可覆盖（UserProfile 第九维）

### 2.4 编译策略

`primary_deep`（主域填满）/ `balanced`（均衡）/ `summary_fallback`（摘要降级）

### 2.5 四轮修剪

1. 电容排序（activation_count 后 30% 候选）
2. 结构保护（betweenness > 0.6 移出候选）
3. 时序修复（last_accessed < 3 轮移出候选）
4. 摘要压缩（按域类型降级：DiscourseBlock→L2 摘要 / ModuleState→状态标记）

保留优先级 = α·activation + β·recency + γ·betweenness（α/β/γ 挂意图类别）

### 2.6 三步降落（话题切换）

1. 旧话题 L2 摘要压缩（保留话题锚点 + cross_ref）
2. 结构保活（betweenness > 0.6 连接器不压缩）
3. 新话题展开（默认 2-3 跳；超预算则对新话题四轮修剪）

---

## 3. 数据契约

```python
@dataclass
class DomainEntry:
    domain: str            # D/K/E/B/R/P/F/V/M/I/Q 等
    content: str
    confidence: float
    source: str
    token_estimate: int = 0
    cross_refs: list = field(default_factory=list)   # [{target_domain, target_event_id, note}]
    source_events: list = field(default_factory=list)

@dataclass
class SubgraphContext:
    perspective: str       # "dialogue" | "meta"
    entries: List[DomainEntry]
    total_tokens: int
    budget: int
    domains: Dict[str, float]
    compile_strategy: str = "balanced"   # primary_deep | balanced | summary_fallback
    intent_category: str = "query"       # task|query|correction|discussion|casual|topic_switch

@dataclass
class SubgraphPrior:       # PCR §5 反哺契约
    domain_scope: Dict[str, float]       # 域 → 预算比例（PCR 定的口径）
    coordinate_bias: Dict[str, float]    # 预期上下文先验 → X/Y/Z 偏置
    expected_context: str                # 摘要级预期上下文
```

---

## 4. 接口协议

### 4.1 compile_dialogue（改造）

```python
def compile_dialogue(self, intent: str = "general_query", intent_category: str = "query",
                     extra_budget: int = 0, event_id: str = None) -> SubgraphContext
```

- intent_category 驱动域选择矩阵（2.1），替换硬编码 alloc
- 返回 SubgraphContext（含 compile_strategy + intent_category）
- cross_ref 由 Event ID 反向索引构建

### 4.2 compile_meta（改造）

```python
def compile_meta(self, review_target: str = "", extra_budget: int = 0) -> SubgraphContext
```

- 补 V 域（_vcs）、I 域（inertia 真实数据）、M 域（meta 历史）
- 同样带 cross_ref

### 4.3 pull_prior（新增，PCR §5）

```python
def pull_prior(self, domain_scope: Dict[str, float]) -> SubgraphPrior
```

- PCR 传 domain_scope（它定的域口径）→ 子图回 expected_context + coordinate_bias
- 同轮只拉一次 + 超时降级（拉不到 → PCR 结构兜底，不阻塞）

### 4.4 intent_category 来源桥接（PCR zone ↔ 意图矩阵，2026-08-01 讨论定案）

**断点**: 意图矩阵输入是 `intent_category`（task/query/...），但 PCR 输出的是
`zone`（PSYCHE/ATOMIC/...）——两个分类体系，PCR 不产出 intent_category。
设计原话"intent 类别输入来自 PCR/intent 解析"含糊，需明确来源与兜底。

**两体系定位（正交，不 1:1 硬映射）**:

| 体系 | 分类 | 回答的问题 | 产出方 |
|------|------|-----------|--------|
| PCR zone | ATOMIC/PRECISION/EXPLORE/ABYSS/PSYCHE/MIXED | **怎么答**（执行策略/认知负载） | PCR |
| intent_category | task/query/correction/discussion/casual/topic_switch | **用什么答**（域选择/内容来源） | 意图解析/关联链 |

**分层桥接（不硬映射，降级才映射）**:

```
主路径（正确）: 意图解析/关联链产出 intent_category → 驱动域矩阵
降级路径（兜底）: PCR zone → intent_category 映射表（仅无意图解析时）
交叉校验（可选）: zone 与 intent_category 冲突 → 记录 conflict（复用双视图思想）
```

**zone → intent_category 兜底映射表**（降级用，非主路径）:

| PCR zone | intent_category | 说明 |
|----------|----------------|------|
| ATOMIC | task / casual | 原子指令=task；简短问候（无工程实体）=casual |
| PRECISION | task | 复杂任务 |
| EXPLORE | query | 探索性查询 |
| ABYSS | discussion | 深域开放，域选择放宽 |
| PSYCHE | discussion（域弱化） | 情绪主导——应减少域抓取（宽而浅） |
| MIXED | query（默认兜底） | 混合，取默认 |

**关键约束**:
1. 映射表是**降级默认**不是真理——主路径永远是意图解析给 intent_category
2. PSYCHE 语义: 情绪场景应**少抓域**（宽而浅）——域矩阵需支持"弱化"模式
3. 冲突记录复用 PCR 双视图 `conflicts` 思想: 两体系冲突不硬裁决，记录供后验

**落地位置**:
- 映射表放 `config/subgraph_dimensions.yaml`（`zone_fallback` 段）
- `compile_dialogue` 增加 `zone: str = None` 参数: 有 intent_category 用之；
  无则用 zone 查兜底表；两者都有且冲突 → 记入 SubgraphContext（新增 conflicts 字段）

---

## 5. 与 PCR 协同（DESIGN_PCR §5 双向）

```
PCR(粗) --domain_scope--> Subgraph.pull_prior() --coordinate_bias--> PCR X轴
  ▲                                                              │
  └──────────── 预期上下文先验（X 轴真实参照）──────────────────────┘
```

- PCR 定域口径（意图矩阵输出）→ 子图回预期上下文先验
- X 轴 = 1 - cos(query, prior)，prior 是真实子图向量（非任意文本）
- 同轮单次拉取 + 超时降级

---

## 6. 预算与配置（YAML）

```yaml
# config/subgraph_dimensions.yaml
subgraph:
  budget:
    mode: auto                  # auto | manual | provider_default
    manual_limit: 800
    default: 500
    provider: { deepseek: 1000, openai: 500, local: 1500, default: 600 }
  domains:
    dialogue: { D: 0.40, K: 0.20, E: 0.05, B: 0.15, R: 0.10, P: 0.10, F: 0.05 }
    meta:     { V: 0.25, E: 0.30, M: 0.15, I: 0.15, P: 0.10, Q: 0.05 }
  intent_matrix:
    task: { primary: E, aux1: B, aux2: P }
    query: { primary: C, aux1: E, aux2: P }
    correction: { primary: B, aux1: E, aux2: K }
    discussion: { primary: P, aux1: C, aux2: E }
    casual: { primary: C, aux1: P, aux2: null }
    topic_switch: { primary: C, aux1: B, aux2: P }
  trim:
    alpha: { task: 0.3, discussion: 0.2, correction: 0.5, topic_switch: 0.1, casual: 0.4, query: 0.3 }
    beta:  { task: 0.2, discussion: 0.5, correction: 0.3, topic_switch: 0.6, casual: 0.4, query: 0.3 }
    gamma: { task: 0.5, discussion: 0.3, correction: 0.2, topic_switch: 0.3, casual: 0.2, query: 0.4 }
    betweenness_threshold: 0.6
    recency_window: 3
    candidate_ratio: 0.3
```

---

## 7. 结构修剪（实现要点）

- `_trim(ctx, intent_category)`：超预算时触发四轮修剪（§2.5）
- `_topic_switch_rebuild(old_ctx, new_ctx)`：三步降落（§2.6）
- 修剪与 ColdIndexer 回升共用 importance/activation/recency 评分体系（镜像）

---

## 8. 验证基准

- 黄金样例：对话树子图（生成回复视角）+ 元认知子图（审核视角），各 5-8 条
- 断言：域选择符合意图矩阵、cross_ref 双向完整、预算内 total_tokens ≤ 上限、
  修剪后子图连通（无孤立入口节点）
- 回归：现有消费方（context_assembly / unified_context）不破

---

## 9. 改造落点（对齐拍板：建完整，v4 原基础改造）

### 9.1 P0 接线（让子图首次真实进入生产路径）

| # | 文件 | 改动 |
|---|------|------|
| 1 | `cli/subsystem_registrations.py` | 补注册 subgraph（对齐 registry.py:340 同路径） |
| 2 | `cli/commands/subgraph_cmd.py` | show/expand 改调 compile_dialogue/compile_meta |

### 9.2 P1 设计落地（v3 要素补齐）

| # | 文件 | 改动 |
|---|------|------|
| 3 | `v4/cognitive/subgraph_compiler.py` | DomainEntry 加 cross_refs/source_events |
| 4 | 同文件 | SubgraphContext 加 compile_strategy/intent_category |
| 5 | 同文件 | intent_category → 域选择矩阵（替代硬编码 alloc） |
| 6 | 同文件 | Event ID 反向索引 → cross_ref 构建 |
| 7 | 同文件 | alloc 读 YAML（config/subgraph_dimensions.yaml） |
| 8 | 同文件 | compile_meta 补 V 域（_vcs）+ I 域真实数据 |
| 9 | 同文件 | `_trim()` 四轮修剪 + `_topic_switch_rebuild()` 三步降落 |
| 10 | 同文件 | `pull_prior(domain_scope)` 新增 |

### 9.3 P2 测试重写

| # | 文件 | 改动 |
|---|------|------|
| 11 | `tests/test_subgraph_*.py` | 意图矩阵/cross_ref/修剪/预算真实断言 |

### 9.4 不改（明确排除）

- `compiler/subgraph_compiler.py`（v3 水波）— 归档候选
- `engine/deep_modules.py` 的第三个 SubgraphCompiler — 归档候选
- RAG/ContentIndex 路径 — 不混淆职责

### 9.5 执行顺序

```
第 1 步: P0 接线（2 处）→ 子图首次真实运行
第 2 步: 数据契约扩展（#3/#4）→ 编译策略 + cross_ref 字段就位
第 3 步: 意图矩阵 + alloc YAML（#5/#7）→ 域选择真实化
第 4 步: cross_ref 构建 + V/I 域补全（#6/#8）
第 5 步: 四轮修剪 + 三步降落（#9）
第 6 步: pull_prior（#10）→ 打通 PCR §5
第 7 步: P2 测试 + 黄金样例回归
第 8 步: 死代码归档（compiler/subgraph + deep_modules）
```

---

## 10. 糅合来源索引

| 设计要素 | 来源 |
|---------|------|
| 意图感知域选择矩阵 | DESIGN_CROSS_DOMAIN_CONTEXT §4 |
| cross_ref 指针网络 | DESIGN_CROSS_DOMAIN_CONTEXT §6 |
| 三层预算 + Provider 自适应 | DESIGN_CROSS_DOMAIN_CONTEXT §5/§10 |
| Context IR v2 / compile_strategy | DESIGN_CROSS_DOMAIN_CONTEXT §7 |
| 四轮修剪 / 三步降落 | DESIGN_CROSS_DOMAIN_CONTEXT §11 |
| 双视角（dialogue/meta） | BUSINESS_CHAIN_10 + DESIGN_SYNTHESIS §五 |
| 三级召回 | merge/DESIGN_02_CONTEXT_AND_MEMORY §4.6 |
| pull_prior（PCR §5 反哺） | DESIGN_PCR §5 + 审计 §5.4 |

---

## 11. 子图溯源专题（跨模块，待立项，2026-08-01 讨论记录）

> 触发扩展（从 event_id 反向索引多跳）需要各模块携带溯源锚点。
> 核查结论：**这是跨模块系统工程，不是子图单模块职责**。

### 11.1 溯源锚点核查（实测）

| 模块 | 溯源锚点（event_id/trace_id） | 备注 |
|------|:---:|------|
| EventLog | ✅ | event_id 主键 + trace_id 列（api_event_log.py） |
| 行为链 adapter | ✅ | `record_event(event: EventIR)`（adapter.py:174） |
| 对话树 feed | ❌ | `feed(text, session_id, history)` 无 event_id |
| 画像 update | ❌ | `update(ratings)` 无 event_id |
| 关联链 | ❌ | 零命中 |
| EventBus.publish | ❌ | `publish(kind, payload)` 不带 trace_id |
| StateMachine / RuntimeEngine | ❌ | 零 event_id 生成 |

**含义**: v3 设计 §3 的"从 Event Chain 出发，沿 Event ID 多跳扩展"，
前提是各链写入时都携带同一 event_id/trace_id。当前只有行为链做到。

### 11.2 分层决策（已拍板）

```
子图侧（消费端）: 先做 _expand_from_event(event_id)
  → 从 EventLog 按 event_id 查 payload + trace_id
  → 沿 trace_id 找同链路事件（能查多少是多少，子图职责内）

共享层（溯源地基）: EventBus.publish 加 trace_id 贯穿
  → 对话树/画像/关联链 feed/update 加 event_id 参数
  → 跨模块签名变更，独立立项，不做在子图施工里
```

### 11.3 顺序

1. 子图消费端 `_expand_from_event` 先落地（可独立测试）
2. 溯源贯通（EventBus trace_id + 各链 event_id 参数）排到
   行为链/关联链施工时统一做——多条链接口变更，避免反复动签名

### 11.4 关联范式

- A17（git 式记录/可追溯）：溯源贯通 = 可追溯性的实现地基
- A24（逆动力学，可逆推）：事件溯源让"反向推出内容来源"成为可能
- 子图溯源是这两个公理在跨链层面的落地载体

---

## 12. 归档核查结论（暂缓归档，2026-08-01 记录）

> 曾计划归档 v3 水波（compiler/subgraph_compiler.py）和 deep_modules 的
> SubgraphCompiler。归档前核查发现：**两个实现的功能路径都比预想复杂，
> 直接归档会误伤活代码或丢未接线能力。决定暂缓归档，先记录结论。**

### 12.1 compiler/subgraph_compiler.py（v3 水波）— "被绕过的旧壳"

```
水波逻辑（find_seeds/expand）已在 graph_source.py 的 ConceptGraph 重新实现：
  content_index.py:107 find_seeds → :111 expand_subgraph（走 graph，不走此壳）
ConceptGraph / ContentIndex 本身是活的：
  runtime/engine.py 挂 ContentIndex + IndexSource
  cli/main.py 构建知识图（build_from_pool）
  semantic_path.py / context/graph_source.py 依赖
判定: 此文件是旧壳可归档（功能已被 graph_source 覆盖），
      但 ConceptGraph/ContentIndex 不是死代码 —— v4 图扩展可复用
```

### 12.2 deep_modules.py 的 SubgraphCompiler — "同文件混着活代码"

```
同一文件内的 FormatEngine / MemoryCompiler / ContextAssembler / EventLogDB
  均被 registry.py:369-378 或 batch4_cmd.py 引用（活的）
仅 SubgraphCompiler 类（expand/set_hop/set_weight/set_budget/set_strategy）
  零真实调用
判定: 不能整个文件归档；若归档只能删文件内 SubgraphCompiler 类
```

### 12.3 v4 是否完整覆盖？— 否，缺"图扩展"能力

```
v4 = 域抓取（engine 对象取 D/K/E/B/P/F）+ 意图矩阵 + cross_ref + 修剪
v3/ConceptGraph = 图扩展（种子 → 边类型优先级 → 水波）
两条路线 v4 只做了前者；图扩展依赖 ConceptGraph 有数据
  （cli/main.py 才构建，生产路径未接）
判定: 当前归档不丢"可运行功能"，但丢"未接线的图扩展能力"
```

### 12.4 决策（用户拍板）

```
暂缓归档。先把子图功能做完（施工优先），归档排到功能稳定后。
归档前置条件（未来做时）:
  ① v4 加 expand_from_graph()（委托 ConceptGraph 种子+水波，
     图可用则用，不可用降级域抓取）—— 先糅合再归档
  ② 归档 compiler/subgraph_compiler.py 到 un_use
  ③ deep_modules 只删 SubgraphCompiler 类（FormatEngine 等保留）
```

---

## 13. 共享检索原语 + 前瞻预热（2026-08-01 讨论记录）

> 洞察：ConceptGraph 的"锚点定位 + 图扩展"是**混合 RAG 的检索侧**——
> 多维信号（keyword 快 + semantic/BGE 准）定位锚点，再沿边类型优先级
> 水波抓内容。这不只是子图的抓取手段，而是**多个模块可复用的检索原语**。

### 13.1 确认：混合 RAG 检索侧

```
ConceptGraph.find_seeds（多维锚点定位）:
  Tier1 keyword（免费、常跑） + Tier2 semantic/BGE（准）
  → weighted merge → 种子节点
ConceptGraph.expand_subgraph（图扩展抓取）:
  边类型优先级 → 水波 → 节点+边集合
= 向量/频率等多维信号定位锚点 → 图搜索抓内容
```

### 13.2 前瞻预热场景（用户提出，价值放大器）

```
PCR + 行为链协同预测"下次内容主题"
  → 对话树当前未命中该主题
  → 提前到持久化空间做锚点定位（find_seeds）
  → 预取子图入热区
  → 后续命中时快速抓取（不现场跑检索）
```

对应范式公理：
- A18 温度系统（热/冷分层）——预热 = 冷数据按预测提前加热
- A25 召回 = 重建上下文——预取让"重建"更快
- 前瞻记忆——行为链预测驱动预取

### 13.3 分层方案（已讨论，未实施）

```
① 检索原语共享化:
   expand_from_graph 做成独立可复用方法
   （context/graph_source.py 或新 retrieval/ 层）
   消费方: 子图 / PCR / 行为链
② 子图先接入（§12.4 归档前置）:
   v4 compile_dialogue 有图走图扩展，无图降级域抓取
③ 前瞻预热闭环（新能力，单独立项）:
   行为链预测 → 预取锚点 → 热区加热 → 快速命中
```

### 13.4 状态

- §13.1/13.2 已确认记录
- §13.3 ① ② 待实施（①是子图 expand_from_graph 的落地形态）
- §13.3 ③ 前瞻预热闭环为独立任务，待立项
