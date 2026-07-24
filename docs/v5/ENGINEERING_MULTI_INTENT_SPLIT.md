# 多意图拆分 — 工程方案

> 2026-07-24 · 设计解构: 设计文档 + 现有代码 → 工程落地方案
>
> 输入源:
>   docs/v5/DESIGN_DERIVATION_COMPRESSION_V2.md (发散→收敛压缩)
>   docs/BUSINESS_CHAIN_01_INTENT.md §Stage 3-5 (多意图+歧义)
>   docs/v5/DESIGN_ASSOCIATION_CHAIN_L1_L4.md §L4 (时序意图)
>
> 代码基:
>   core/agent/cognitive/derivation_compressor.py (273行)
>   core/agent/association/l3_intent.py (219行)
>   core/agent/association/l2_5_belief.py (249行)
>   core/agent/v4/cognitive/ocean_profile.py (265行)
>   core/agent/v4/cognitive/behavior_discovery.py (242行)
>   core/agent/v3_common/un_use/intent_parser.py (1209行, 已废弃)

---

## 零、现状诊断

### 已有能力

| 模块 | 能力 | 成熟度 |
|------|------|:------:|
| DerivationCompressor | 发散→收敛→启发链, 覆盖率生命周期 | ✅ 可用 |
| MultiPerspectiveValidator (L3) | 4方投票+LLM死锁裁决, 单意图 | ✅ 可用 |
| BayesianUpdater (L2.5) | 贝叶斯序贯更新, 7D信念, 轨迹审计 | ✅ 可用 |
| OCEANProfile | 10维画像 EMA 聚合, MBTI 映射 | ✅ 可用 |
| BehaviorDiscovery | 统计模式发现, A→B 行为链 | ✅ 可用 |
| SubgraphCompiler | 跨链上下文组装, 双视角 | ✅ 可用 |

### 已废弃 / 未实现

| 模块 | 问题 | 后果 |
|------|------|------|
| v3 `_split_multi_intent` | 仅正则切分连词, 无语义理解 | 无法识别隐含多意图 |
| v3 `_detect_ambiguities` | 硬编码 EntityType 枚举 | 无法泛化到新领域 |
| v3 `_resolve_ambiguities` | 仅跳过 auto_resolvable | 无真实消解逻辑 |
| L4 时序意图 | 设计完成, 代码为零 | 无意图转移预测能力 |

### 核心差距

```
v3 多意图拆分 = 正则切分("然后"|"接着"|"并且"|"同时") → 实体继承 × 0.8
  ❌ 不感知语义边界
  ❌ 不使用关联链证据
  ❌ 不调用画像/行为链
  ❌ 无歧义消解的 LLM 路径
  ❌ 无融合策略
```

---

## 一、多意图拆分组件设计

### 1.1 架构总览

```
                    ┌─────────────────────────────────────────┐
用户输入 ──────────→│     MultiIntentSplitter (新)            │
                    │                                         │
  PCR signals ─────→│  ┌─ Stage A: LiteralSplitter            │
                    │  │  连词+依存句法→候选拆分段            │
                    │  ├─ Stage B: ChainParallelVerifier       │
                    │  │  四条链路并行验证每个子意图           │
                    │  ├─ Stage C: FusionDecider               │
                    │  │  投票/加权/LLM → 最终子意图列表       │
                    │  ├─ Stage D: AmbiguityGate               │
                    │  │  歧义指标→触发消解 or 放行            │
                    │  └─ Stage E: AmbiguityResolver           │
                    │    上下文继承 / LLM补全 / ask_user       │
                    └─────────────────────────────────────────┘
                              ↓
                    List[SubIntent] → ContextMerger → TaskGraph
```

### 1.2 核心数据类

```python
@dataclass
class SubIntent:
    """拆分后的单条子意图"""
    id: str
    text: str                          # 原始文本片段
    category: str                      # 意图类别 (诊断/修复/探索/...)
    entities: List[Entity]             # 实体列表 (含继承标记)
    confidence: float                  # 综合置信度
    chain_votes: Dict[str, float]      # 四条链路各自的置信 {profile: 0.8, behavior: 0.6, ...}
    ambiguity_score: float             # 歧义评分 (0=明确, 1=完全歧义)
    needs_clarification: bool          # 是否需要用户澄清
    dependencies: List[str]            # 依赖的其他子意图 ID (时序依赖)

@dataclass  
class MultiIntentResult:
    """多意图拆分完整结果"""
    sub_intents: List[SubIntent]
    is_multi: bool                     # 是否确实包含多意图
    split_confidence: float            # 拆分本身的置信度
    fusion_method: str                 # "vote_consensus" | "weighted_mix" | "llm_adjudicate"
    ambiguities: List[Ambiguity]
    trace: Dict[str, Any]              # 全链路 trace
```

### 1.3 Splitter 接口

```python
class MultiIntentSplitter:
    """多意图拆分器 — 替代 v3 的 _split_multi_intent()"""

    def __init__(
        self,
        llm_provider=None,
        profile: OCEANProfile = None,
        behavior_graph=None,
        association_chain=None,    # L1→L2→L2.5 关联链
        derivation_pool=None,      # DerivationCompressor 的启发池
    ): ...

    def split(
        self,
        text: str,
        entities: List[Entity],
        intent_context: IntentContext,   # PCR signals
        discourse_context: List[str],    # 近 N 轮话题
        parse_context: ParseContext,     # 历史上下文
    ) -> MultiIntentResult: ...
```

---

## 二、与 DerivationCompressor 的复用关系

### 2.1 复用模式

```
DerivationCompressor (发散→收敛→启发链) 的设计模式直接复用到多意图拆分:

  发散 (Diverge)           → 多意图拆分中的 "候选意图生成"
  收敛 (Converge)          → 多意图拆分中的 "四条链路验证"
  启发链 (HeuristicChain)  → 多意图拆分中的 "融合策略"

具体来说:
  ┌──────────────────────────┬─────────────────────────────────┐
  │ DerivationCompressor     │ MultiIntentSplitter             │
  ├──────────────────────────┼─────────────────────────────────┤
  │ extract(edges, traces)   │ Stage A: 从依存句法提取候选段   │
  │ diverge(transitions)     │ Stage B: LLM 无上下文生成候选   │
  │                          │   意图 (高 temperature)         │
  │ converge(transitions,    │ Stage B: 四条链路并行验证       │
  │   guesses, context)      │   (低 temperature, 有上下文)     │
  │ heuristic(transitions,   │ Stage C: 融合策略决定最终拆分   │
  │   verified)              │   → 产出 SubIntent 列表         │
  │ pool management          │ Stage D/E: 歧义池管理            │
  └──────────────────────────┴─────────────────────────────────┘
```

### 2.2 具体复用点

**复用 1: Diverge/Converge 双温度模式**

```python
# 多意图拆分也采用双温度:
#   Diverge: temperature=0.8, no_context → 生成候选子意图假设
#   Converge: temperature=0.1, with_context → 四条链路筛选
# 这直接复用 DerivationCompressor 的 DIVERGE_TEMPERATURE / CONVERGE_TEMPERATURE
```

**复用 2: 启发覆盖率 → 模板缓存**

```python
# DerivationCompressor.pool 存储 HeuristicChain, 按 coverage 淘汰
# MultiIntentSplitter 同样维护一个拆分模板池:
#   - 例如: "先X后Y" 模式 → 子意图 [诊断, 修复], dependency=sequential
#   - 覆盖率 < 阈值 → 重新发散→收敛 → 更新模板
```

**复用 3: HeuristicChain 数据结构**

```python
# 多意图拆分结果可编码为 HeuristicChain:
#   summary: "当用户说'先定位再修复'时，拆分为 [诊断→修复] 时序链"
#   conditions: ["含'先...再...'", "含因果连词", "实体跨越两个领域"]
#   counter_examples: ["仅含并列无时序", "实体在同一领域内"]
#   coverage: 启发覆盖率
```

**复用 4: StateTransition → IntentTransition**

```python
# DerivationCompressor.extract() 从 L2/L2.5 提取 StateTransition
# MultiIntentSplitter 从 L2.5 belief_trace 提取 IntentTransition:
#   P(intent_B | intent_A) = 从历史对话学习
#   用于判断两个子意图之间是否存在时序依赖
```

### 2.3 不要复用的部分

| DerivationCompressor 特性 | 原因 | 替代方案 |
|---------------------------|------|----------|
| `COMPRESSION_INTERVAL=5` 批量触发 | 多意图拆分必须每轮触发 | 实时 split, 不攒批 |
| `extract()` from entity edges | 拆分不需要实体边 | 用依存句法边替代 |
| `_transition_buffer` 缓冲 | 无需攒批 | 直接消费 |

---

## 三、五条链路并行设计 (LLM-dominant)

### 3.0 设计原则

```
每条链路: LLM 主导 verify, 算法做前置过滤
并行执行: 5 链路无依赖, 可并发
融合: 5 链路投票 → 加权 → LLM 裁决 (cost-adaptive)
```

### 3.1 五链路定义

```
          用户输入: "先定位哪个模块延迟, 然后帮我看看怎么修,
                    顺便评估一下影响范围, 我需要用gdb去调"

  ┌──────────────────────────────────────────────────────────────────┐
  │                    五条链路并行验证 (LLM-dominant)                 │
  │                                                                  │
  │  链路1 — 画像链 (Profile Chain)                                   │
  │    数据源: OCEANProfile.prefs + CognitiveStyle                    │
  │    算法层: 过滤: 高N→吐槽场景提权, 高C→结构化拆分提权               │
  │    LLM层:  "该用户画像是否支持拆分出'{candidate}'子意图?"           │
  │    输出:   {confidence, reason}                                   │
  │                                                                  │
  │  链路2 — 关联链 (Association Chain)                                │
  │    数据源: L1 modifier + L1.5 completer + L2 substrate + 行为模式  │
  │    算法层: 过滤: 实体overlap>0.7→不应拆分; SVO完整→可拆分          │
  │    LLM层:  "关联链证据是否支持将'{segment}'识别为独立子意图?"       │
  │    输出:   {confidence, evidence_entities, behavior_pattern}      │
  │                                                                  │
  │  链路3 — 话语链 (Discourse Chain)                                  │
  │    数据源: DiscourseBlockTree topic history + Block cohesion      │
  │    算法层: 过滤: topic漂移检测; 跨block实体不连续→拆分             │
  │    LLM层:  "对话历史上文中是否有支持此拆分的先例或语境?"            │
  │    输出:   {confidence, topic_match, cohesion_delta}              │
  │                                                                  │
  │  链路4 — 字面链 (Literal Chain)                                    │
  │    数据源: 依存句法 + 连词标记 + 标点结构                          │
  │    算法层: 切分: Stanza依存树→候选段; 连词检测→拆分类型            │
  │    LLM层:  "字面标记'{先...然后...顺便}'的拆分方案是否合理?"        │
  │    输出:   {confidence, split_points, marker_type}                │
  │                                                                  │
  │  链路5 — 工程链 (Engineering Chain) [接口]                         │
  │    数据源: tools_available, env_state, resource_constraints       │
  │    算法层: 过滤: 工具能力⊇子意图需求→可行; 资源充足→可并行         │
  │    LLM层:  "当前工程环境是否支持完成'{sub_intent}'?" (未实现)      │
  │    输出:   {confidence, feasible, blocking_resources}             │
  │    状态:   📋 接口定义完成, 实现待工程链模块完善                   │
  └──────────────────────────────────────────────────────────────────┘
```

### 3.2 并行执行框架

```python
class ChainParallelVerifier:
    """五链路并行验证 — LLM-dominant, 算法做前置过滤"""

    def __init__(self, profile, association, discourse, literal, engineering=None):
        self.chains = {
            "profile":      ProfileChainVerifier(profile),
            "association":  AssociationChainVerifier(association),
            "discourse":    DiscourseChainVerifier(discourse),
            "literal":      LiteralChainVerifier(literal),
            "engineering":  EngineeringChainVerifier(engineering),  # nullable
        }

    def verify(self, candidate: SubIntent, context: VerifyContext) -> ChainVotes:
        """并行验证。LLM 调用在 subagent 层并发。"""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                name: pool.submit(chain.verify, candidate, context)
                for name, chain in self.chains.items()
                if chain.is_ready()  # engineering链未就绪时跳过
            }
            votes = {
                name: f.result()
                for name, f in futures.items()
            }
        return ChainVotes(votes=votes)
```

### 3.3 LLM-dominant 链路实现

```python
class LLMDrivenChain:
    """LLM主导的链路基类 — 算法层做前置过滤, LLM做核心验证"""

    def __init__(self, llm, data_source, name: str):
        self.llm = llm
        self.data = data_source
        self.name = name

    def verify(self, candidate: SubIntent, context: VerifyContext) -> ChainVote:
        # Step 1: 算法层快速过滤 (零成本)
        pre_check = self._algorithm_filter(candidate, context)
        if pre_check == "reject":
            return ChainVote(chain=self.name, confidence=0.1, decision="reject",
                           reason=pre_check.reason)
        if pre_check == "accept":
            return ChainVote(chain=self.name, confidence=0.9, decision="accept",
                           reason=pre_check.reason)

        # Step 2: LLM 核心验证 (中延迟, 高质量)
        prompt = self._build_llm_prompt(candidate, context, pre_check.hints)
        response = self.llm.generate(prompt, max_tokens=150, temperature=0.1)
        return self._parse_llm_response(response)

    def _algorithm_filter(self, candidate, context) -> FilterResult:
        """子类实现: 算法前置过滤逻辑"""
        raise NotImplementedError

    def _build_llm_prompt(self, candidate, context, hints) -> str:
        """子类实现: 构建LLM验证提示词"""
        raise NotImplementedError
```

### 3.4 工程链接口 (预留)

```python
@dataclass
class EngineeringContext:
    """工程链上下文 — 接口定义, 实现待工程链模块完善"""
    tools_available: List[str] = field(default_factory=list)
    env_state: Dict[str, str] = field(default_factory=dict)
    resource_constraints: Dict[str, bool] = field(default_factory=dict)

class EngineeringChainVerifier(LLMDrivenChain):
    """工程链验证器 — is_ready()=False 时跳过此链路"""

    def __init__(self, engineering=None):
        super().__init__(llm=None, data_source=engineering, name="engineering")
        self._ready = engineering is not None

    def is_ready(self) -> bool:
        return self._ready

    def _algorithm_filter(self, candidate, context) -> FilterResult:
        if not self._ready:
            return FilterResult("skip", "工程链未就绪")
        # 工具能力 ⊇ 子意图需求
        if context.engineering and context.engineering.tools_available:
            return FilterResult("pass")
        return FilterResult("skip", "无工程上下文")

    def _build_llm_prompt(self, candidate, context, hints) -> str:
        return ""  # 未实现, 预留
```

---

## 四、融合策略

### 4.1 三种策略对比

```
┌─────────────────┬──────────────────┬──────────────────┬──────────────────┐
│                 │ 投票共识          │ 加权混合          │ LLM 裁决          │
│                 │ (Vote Consensus)  │ (Weighted Mix)   │ (LLM Adjudicate)  │
├─────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ 适用场景         │ 链路分歧小时      │ 链路置信度分散时  │ 链路严重分歧时    │
│ 触发条件         │ max - min < 0.3   │ 0.3 ≤ std ≤ 0.5 │ std > 0.5         │
│ 延迟             │ ~0ms              │ ~0ms              │ ~100-300ms        │
│ LLM 消耗         │ 0                 │ 0                 │ 1 call            │
│ 可解释性         │ 高 (投票明细)     │ 中 (权重可查)     │ 中 (LLM reasoning)│
│ 准确率(预期)     │ 70-80%            │ 75-85%            │ 85-95%            │
└─────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

### 4.2 自动策略选择

```python
class FusionDecider:
    """根据链路分歧程度自动选择融合策略"""

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def decide(self, votes: ChainVotes, candidates: List[SubIntent]) -> MultiIntentResult:
        confidences = list(votes.votes.values())
        std_dev = self._std(confidences)
        mean_conf = sum(confidences) / len(confidences)

        if std_dev < 0.3:
            # 链路高度一致 → 投票共识 (零成本)
            return self._vote_consensus(votes, candidates)
        elif std_dev < 0.5 and mean_conf > 0.5:
            # 中等分歧 → 加权混合 (零成本但有配置权重)
            return self._weighted_mix(votes, candidates)
        else:
            # 严重分歧 → LLM 裁决 (高质量但慢)
            if self.llm:
                return self._llm_adjudicate(votes, candidates)
            else:
                # LLM 不可用 → 降级到加权混合
                return self._weighted_mix(votes, candidates)

    def _vote_consensus(self, votes, candidates):
        """投票共识: 每条链路投 accept/reject, 多数决"""
        # 类似 l3_intent.py 的 MultiPerspectiveValidator,
        # 但粒度从"意图验证"变为"拆分方案验证"
        accepts = sum(1 for v in votes.votes.values() if v > 0.6)
        rejects = sum(1 for v in votes.votes.values() if v < 0.4)
        return MultiIntentResult(
            sub_intents=candidates if accepts >= 3 else [],
            is_multi=accepts >= 3,
            split_confidence=accepts / 4,
            fusion_method="vote_consensus",
        )

    def _weighted_mix(self, votes, candidates):
        """加权混合: 链路的配置权重 × 链路置信度"""
        # 权重来自 config/multi_intent_config.json:
        #   profile_weight=0.2, behavior_weight=0.2,
        #   discourse_weight=0.35, literal_weight=0.25
        weights = self._config_weights()
        weighted = sum(votes.votes[ch] * weights[ch] for ch in votes.votes)
        return MultiIntentResult(
            sub_intents=candidates if weighted > 0.55 else [],
            is_multi=weighted > 0.55,
            split_confidence=weighted,
            fusion_method="weighted_mix",
        )

    def _llm_adjudicate(self, votes, candidates):
        """LLM 裁决: 输入 4 链路投票详情 + 候选拆分, LLM 输出最终判断"""
        # 直接复用 l3_intent._llm_deadlock() 的模式:
        #   prompt = 投票详情 + 候选拆分 + belief state
        #   → LLM 返回 {decision, reasoning, confidence}
        ...
```

### 4.3 PCR 调控融合策略

```python
# PCR complexity 影响融合策略选择:
#   complexity > 0.8 → 强制 LLM 裁决 (最高质量)
#   complexity < 0.2 → 允许投票共识 (最快路径)
#   noise > 0.7      → 增加 literal 链路权重 (噪声环境下句法不可靠)

def _pcr_override(self, std_dev, pcr: IntentContext):
    if pcr.complexity_level > 0.8:
        return "llm_adjudicate"  # 复杂场景强制 LLM
    if pcr.noise_level > 0.7:
        # 高噪声 → 增加字面链权重, 降低话语链权重
        self._weights["literal"] *= 1.5
        self._weights["discourse"] *= 0.7
    return None  # 使用自动策略
```

---

## 五、歧义检测指标

### 5.1 歧义量化

```
歧义不是二值的 (有/无), 而是一个连续信号:

  ambiguity_score = f(entity_gap, intent_conflict, context_mismatch, seq_ambiguity)

  其中:
    entity_gap:        子意图间缺少的实体 / 期望实体总数
    intent_conflict:   子意图间互斥的意图类别数 / 子意图总数
    context_mismatch:  1 - (子意图实体 ∩ 上下文继承实体) / 子意图实体
    seq_ambiguity:     是否存在多种排序方案 (并行 vs 时序 vs 条件)
```

### 5.2 触发条件 (何时触发歧义消解)

```python
class AmbiguityGate:
    """歧义门控 — 决定: 放行 / 自动消解 / 请求用户"""

    # 触发条件 (AND/OR 组合)
    TRIGGERS = {
        "missing_entity": {
            "condition": lambda s: s.entity_gap > 0.3,
            "action": "auto_resolve",  # 尝试上下文继承
            "fallback": "ask_user",
        },
        "intent_conflict": {
            "condition": lambda s: s.intent_conflict > 0.5,
            "action": "llm_resolve",   # LLM 裁决
            "fallback": "ask_user",
        },
        "low_confidence": {
            "condition": lambda s: s.confidence < 0.4,
            "action": "ask_user",      # 直接请求澄清
        },
        "seq_ambiguous": {
            "condition": lambda s: s.seq_ambiguity > 0.6,
            "action": "auto_resolve",  # 行为链推断
            "fallback": "llm_resolve",
        },
        "pcr_noise_spike": {
            "condition": lambda s, pcr: pcr.noise_level > 0.8 and s.ambiguity_score > 0.3,
            "action": "ask_user",      # 高噪声下保守
        },
    }

    def evaluate(self, sub_intent: SubIntent, pcr: IntentContext) -> AmbiguityDecision:
        """评估单条子意图 → 决定如何处理"""
        score = self._compute_score(sub_intent)

        for trigger_name, trigger in self.TRIGGERS.items():
            if trigger["condition"](sub_intent):
                return AmbiguityDecision(
                    trigger=trigger_name,
                    score=score,
                    action=trigger["action"],
                    fallback=trigger["fallback"],
                )

        # 低歧义 → 直接放行
        if score < 0.3:
            return AmbiguityDecision(action="pass", score=score)

        # 中等歧义 → 自动消解
        return AmbiguityDecision(action="auto_resolve", score=score)
```

### 5.3 消解策略矩阵

```
┌──────────────────┬──────────────┬──────────────┬──────────────┐
│ 消解策略           │ 触发歧义类型  │ 成本           │ 成功率(预期)  │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ 上下文继承         │ 缺失实体      │ ~0ms          │ 60-80%       │
│ (从 ParseContext  │ 低置信实体    │               │              │
│  history 自动补全) │              │               │              │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ 行为链推断         │ 时序歧义      │ ~5ms          │ 50-70%       │
│ (BehaviorDiscovery │              │               │              │
│  A→B 模式补全)     │              │               │              │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ 画像推断           │ 意图冲突      │ ~5ms          │ 40-60%       │
│ (OCEAN 倾向补全)   │              │               │              │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ LLM 消解           │ 意图冲突      │ ~200ms        │ 80-95%       │
│ (DeepSeek 裁决)    │ 多重歧义      │               │              │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ ask_user          │ 不可自动消解  │ ∞ (阻塞等待)  │ 100%         │
│ (生成澄清问题)     │ 低置信+高噪声 │               │              │
└──────────────────┴──────────────┴──────────────┴──────────────┘
```

### 5.4 消解策略优先级

```python
class AmbiguityResolver:
    """歧义消解 — 按成本由低到高依次尝试"""

    def resolve(self, sub_intents: List[SubIntent],
                context: ResolveContext) -> List[SubIntent]:
        resolved = []
        for si in sub_intents:
            amb = self.gate.evaluate(si, context.pcr)

            if amb.action == "pass":
                resolved.append(si)
                continue

            # 策略1: 上下文继承 (零成本)
            if amb.action == "auto_resolve":
                si = self._context_inherit(si, context.parse_context)
                if si.confidence >= 0.6:
                    resolved.append(si)
                    continue

            # 策略2: 行为链推断 (低延迟)
            si = self._behavior_infer(si, context.behavior_history)
            if si.confidence >= 0.6:
                resolved.append(si)
                continue

            # 策略3: 画像推断 (低延迟)
            si = self._profile_infer(si, context.profile)
            if si.confidence >= 0.6:
                resolved.append(si)
                continue

            # 策略4: LLM 消解 (中延迟)
            if context.llm:
                si = self._llm_resolve(si, context)
                if si.confidence >= 0.5:
                    resolved.append(si)
                    continue

            # 策略5: ask_user (阻塞)
            si.needs_clarification = True
            si.clarification_question = self._generate_clarification(si)
            resolved.append(si)

        return resolved
```

---

## 六、文件清单

### 6.1 新增文件 (优先级 P0)

```
core/agent/intent/                           # 新包: 多意图拆分模块
├── __init__.py
├── multi_intent_splitter.py                 # 主拆分器 (MultiIntentSplitter)
├── chain_verifier.py                        # 五链路并行验证 (ChainParallelVerifier)
│   ├── LLMDrivenChain                       # LLM主导基类
│   ├── ProfileChainVerifier                 # 画像链
│   ├── AssociationChainVerifier             # 关联链 (合并原 Behavior)
│   ├── DiscourseChainVerifier               # 话语链
│   ├── LiteralChainVerifier                 # 字面链
│   └── EngineeringChainVerifier             # 工程链 (接口预留)
├── fusion_decider.py                        # 融合策略 (FusionDecider)
├── ambiguity_gate.py                        # 歧义门控 (AmbiguityGate)
├── ambiguity_resolver.py                    # 歧义消解 (AmbiguityResolver)
└── models.py                                # 数据模型 (SubIntent, MultiIntentResult, ChainVote, etc.)

config/
├── multi_intent_config.json                 # 多意图拆分配置
│   ├── chain_weights: {profile, association, discourse, literal, engineering}
│   ├── fusion_thresholds: {vote, weighted, llm}
│   ├── ambiguity_triggers: {entity_gap, intent_conflict, ...}
│   └── pcr_overrides: {complexity→strategy, noise→weights}
└── l2_config.json                           # 已有, 需要扩展:
    └── l3_behavior_map → l3_intent_profiles

├── test_chain_verifier.py                   # 四条链路独立测试
├── test_fusion_decider.py                   # 融合策略测试
├── test_ambiguity.py                        # 歧义检测+消解测试
└── test_data_multi_intent.json              # 测试数据 (场景驱动)
```

### 6.2 修改文件 (已有文件, 需改动)

```
core/agent/v4/cognitive/derivation_compressor.py
  改动: 添加 IntentTransition 数据类, 暴露 compression_interval 为配置

core/agent/association/l3_intent.py
  改动: MultiPerspectiveValidator 从"单意图验证"扩展为"拆分方案验证",
        新增 validate_split() 方法, 输入从 intent_hypothesis 改为 sub_intents list

core/agent/association/l2_5_belief.py
  改动: BayesianUpdater 新增 intent_transition_likelihood() 方法,
        从 likelihood_matrix 查询 P(intent_B | intent_A)

core/agent/v4/cognitive/ocean_profile.py
  改动: OCEANProfile 新增 intent_preference() 方法,
        返回 profile 对每种意图类别的偏好权重

core/agent/v4/cognitive/behavior_discovery.py
  改动: BehaviorDiscovery 新增 query_transition(intent_a, intent_b) 方法,
        返回从统计行为链查到的转移概率

core/agent/v4/cognitive/subgraph_compiler.py
  改动: 新增 intent_split 域, 预算分配 10%

config/l2_config.json
  改动: 新增 profile_intent_weights 段, l3_multi_intent 段
```

### 6.3 废弃文件 (不再维护)

```
core/agent/v3_common/intent_parser.py            # 已是 shim, 保持不变
core/agent/v3_common/un_use/intent_parser.py      # 已废弃, 不移除但标记
  → _split_multi_intent() 被 MultiIntentSplitter 替代
  → _detect_ambiguities() 被 AmbiguityGate 替代
  → _resolve_ambiguities() 被 AmbiguityResolver 替代
```

---

## 七、实施路线

```
Phase 1: 数据模型 + 字面链路 (最小可用)
  [ ] models.py — SubIntent, MultiIntentResult, AmbiguityDecision
  [ ] multi_intent_splitter.py — Stage A: LiteralSplitter (依存句法拆分)
  [ ] chain_verifier.py — LiteralChainVerifier (字面标记)
  [ ] 测试: test_multi_intent_split.py (3-5 场景)
  预计: 1-2 天

Phase 2: 四条链路并行
  [ ] chain_verifier.py — Profile/Behavior/Discourse 链路实现
  [ ] fusion_decider.py — 投票共识 + 加权混合 (纯规则, 无LLM)
  [ ] 修改 ocean_profile.py, behavior_discovery.py (暴露查询接口)
  [ ] 测试: test_chain_verifier.py (每条链路独立)
  预计: 2-3 天

Phase 3: 融合 + LLM 裁决
  [ ] fusion_decider.py — LLM 裁决路径
  [ ] 修改 l3_intent.py — 扩展 validate_split()
  [ ] 测试: test_fusion_decider.py (3种策略 × 4链路)
  预计: 1-2 天

Phase 4: 歧义门控 + 消解
  [ ] ambiguity_gate.py — 5 种触发条件
  [ ] ambiguity_resolver.py — 5 级消解策略
  [ ] 测试: test_ambiguity.py (每种触发 × 每种消解)
  预计: 1-2 天

Phase 5: 集成 + PCR 调控
  [ ] 接入 v6 engine on_event()
  [ ] PCR complexity/noise → 策略选择
  [ ] DerivationCompressor 启发池接入拆分模板缓存
  [ ] 测试: test_integration_multi_intent.py (端到端)
  预计: 2-3 天
```

总计: **7-12 天**

---

## 八、设计决策记录

| 决策 | 选项 A | 选项 B | 选择 | 原因 |
|------|--------|--------|:----:|------|
| 拆分器粒度 | 单一大类 | 5 Stage 流水线 | B | 与 v3 8-stage pipeline 一致; 每阶段可独立测试/替换 |
| 链路验证方式 | 规则驱动 | LLM 驱动 | 规则为主 | 80%+ 情况字面+行为链可判断, LLM 仅用于严重分歧 |
| 融合默认策略 | 投票共识 | 加权混合 | 加权混合 | 画像链在"探索"场景下应降低权重, 不可简单多数决 |
| 歧义消解序列 | 先快后慢 | 统一 LLM | 先快后慢 | 上下文继承/行为链推断在 60%+ 场景可消解, 无需 LLM |
| HeuristicChain 复用 | 完全复用 | 仅复用模式 | 仅复用模式 | 拆分模板池 ≠ 启发池, 但 diverge/converge 双温度模式完全适用 |
