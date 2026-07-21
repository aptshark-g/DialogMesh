# DialogMesh v6 — 业务链设计 · 第一章：Intent Parser (意图解析器)

> 版本: v1.0 | 日期: 2026-07-21
> 
> 设计来源: design_layer1_intent_parser.md (v1.0, 532行) +
>          DESIGN_MULTI_TIER_PIPELINE.md + DESIGN_TIERED_ACTION_RESOLVER.md +
>          ENGINEERING_INTENT_PARSER.md +
>          代码: v3_common/intent_parser.py (1209行) + v4/tiered/ (1800行)
>
> 核心命题: 不是关键词匹配——是多层递进（规则→spaCy→LLM）的工业级解析引擎。
>          PCR 调控信号全程注入 8 阶段 Pipeline。80%+ 输入在规则层完成。

---

## 一、Intent Parser 在 10 链中的位置

```mermaid
graph TD
    PCR["PCR Output<br/>expectation/noise/complexity/cognitive"]

    subgraph INTENT["链01: Intent Parser"]
        direction TB
        S0["Stage 0: Preprocessor<br/>编码 · 全角/半角 · 地址规范"]
        S35["Pre-3.5: ReferenceResolver<br/>代词消解 (v2.2.1)"]
        S1["Stage 1: EntityExtractor<br/>规则+上下文补全"]
        S2["Stage 2: Classifier<br/>规则+置信度 · Tier0→Tier1→Tier2"]
        FP{"Fast Path?<br/>conf ≥ 0.95"}
        S3["Stage 3: Multi-Intent Split"]
        S4["Stage 4: AmbiguityDetector"]
        S5["Stage 5: AmbiguityResolver"]
        S6["Stage 6: ContextMerger"]
        S7["Stage 7: TaskGraphBuilder"]

        S0 --> S35 --> S1 --> S2
        S2 --> FP
        FP -->|"✅ 跳过"| S6
        FP -->|"❌ 继续"| S3
        S3 --> S4 --> S5 --> S6
        S6 --> S7
    end

    PCR -->|"expectation → extractor调控"| S1
    PCR -->|"noise → classifier阈值"| S2
    PCR -->|"complexity → max_sub_intents"| S3
    PCR -->|"noise+expectation → 歧义策略"| S4
    PCR -->|"noise_source → context_window"| S6

    S7 --> RESULT["ParseResult<br/>intent + task_graph + trace_log"]
    
    RESULT --> CH02["链02 LLM回复<br/>TaskGraph → 执行计划"]
    RESULT --> CH015["链1.5 Planning<br/>TaskGraph → Skill Matcher"]
```

---

## 二、Tier 架构 (Multi-Tier Pipeline)

```mermaid
graph TD
    INPUT["用户输入<br/>+ IntentContext (PCR)"]

    INPUT --> T0["Tier 0: 规则引擎<br/>0-5ms · 80%+ 命中<br/>Regex + Pattern + Entity"]
    T0 --> T0_OK{"conf ≥ 0.7?"}
    
    T0_OK -->|"✅"| DIRECT["直接返回 ParseResult"]
    
    T0_OK -->|"❌"| T1["Tier 1: 语义增强<br/>5-50ms · 15%<br/>jieba分词 · stanza依存 · BGE相似"]
    T1 --> T1_OK{"conf ≥ 0.7?"}
    
    T1_OK -->|"✅"| DIRECT
    
    T1_OK -->|"❌"| T2["Tier 2: LLM<br/>100-500ms · 5%<br/>intent_classifier prompt<br/>→ DeepSeek"]
    T2 --> DIRECT

    T0 -.->|"反馈"| CACHE["规则缓存<br/>Tier2结果→回写Tier0"]
    T1 -.->|"反馈"| CACHE
    T2 -.->|"反馈"| CACHE
```

---

## 三、8 阶段 Pipeline 详解

### Stage 0: Preprocessor (预处理)

```mermaid
graph LR
    RAW["原始输入: '读取 0x0040_0000 处 4 bytes'"] 
    --> NORM["规范化<br/>0x0040_0000→0x00400000<br/>全角→半角"]
    --> FILTER["过滤<br/>多余标点 · URL截断"]
    --> OUT["NormalizedText"]
```

**实现**: `v3_common/intent_parser.py` L632-710 `_preprocess()`  
**PCR 调控**: 无 (预处理不接受 PCR 信号, 纯文本操作)

### Stage 1: EntityExtractor (实体提取)

```mermaid
graph TD
    INPUT["NormalizedText"] --> RULES["规则提取器<br/>Regex/Keyword/Pattern"]
    RULES --> CTX["上下文补全<br/>ParseContext 已确认实体"]
    
    PCR["PCR expectation"] -->|"TOOL"| TOOL["只提取地址/数值"]
    PCR -->|"ADVISOR"| ADVISOR["额外提取条件/模块/函数名"]
    
    RULES --> CONF["confidence ≥ 阈值"]
    CTX --> CONF
    CONF --> ENTITIES["Entity[]<br/>{type, value, confidence, position}"]
```

**实现**: `v3_common/intent_parser.py` L710-784 `_extract_entities()`  
**PCR 调控**: ✅ 设计中已定义, 代码待接 (当前 entity extractor 不读 PCR)

### Stage 2: Classifier (意图分类)

```mermaid
graph TD
    ENTITIES["Entity[]"] --> RAW["_classify_raw()<br/>pattern match + entity组合打分"]
    RAW --> CANDIDATES["候选意图列表<br/>[(IntentCategory, confidence, rule)]"]
    
    PCR_NOISE["PCR noise_level"] -->|"高噪声"| LOW["min_confidence↓<br/>更多LLM fallback"]
    PCR_NOISE -->|"低噪声"| HIGH["严格匹配<br/>减少误触发"]
    
    CANDIDATES --> CONF["置信度聚合"]
    LOW --> CONF
    HIGH --> CONF
    
    CONF --> INTENT["Intent<br/>{category, confidence, matched_rule}"]
```

**实现**: `v3_common/intent_parser.py` L818-867 `_classify_raw()` + L867-908 `_classify()`  
**PCR 调控**: ❌ 代码存在但 `_classify()` 不接收 `intent_context.noise_level`

### Pre-3.5: ReferenceResolver (代词消解)

```mermaid
graph TD
    TEXT["文本含 '这个地址'/'刚才那个值'"] 
    --> DETECT["扫描指代词<br/>这个/那个/刚才/它"]
    --> BACKTRACK["回溯 ParseContext.history<br/>高置信度实体 (≥0.8)"]
    --> REPLACE["替换文本<br/>+标记 inherited_entities"]
    --> OUT["消解后文本"]
```

**实现**: `v3_common/intent_parser.py` L552-632 `_resolve_references()`  
**设计来源**: v2.2.1 修正 — 在 Entity Extractor 之前执行

### Stage 3: Multi-Intent Split (多意图拆分)

```mermaid
graph TD
    INTENT["Intent"] --> DETECT["连词检测<br/>and then / 先...再... / 同时"]
    DETECT --> SPLIT["实体分布切分<br/>sub_intent_1: {entities}, sub_intent_2: {entities}"]
    
    PCR_COMPLEX["PCR complexity"] -->|">0.8"| MAX["max_sub_intents ↑"]
    PCR_COMPLEX -->|"<0.2"| MIN["单意图 · 不拆分"]
    
    SPLIT --> SUBS["Intent[] (1-N)"]
```

**实现**: `v3_common/intent_parser.py` L908-964 `_split_multi_intent()`  
**PCR 调控**: ⚠️ `complexity→max_sub_intents` 映射在 PCR `rule_based.py` L1111-1116 已实现, 但 `_split_multi_intent` 不读 `intent_context.complexity_level`

### Stage 4: AmbiguityDetector (歧义检测)

```mermaid
graph TD
    INTENT["Intent + Entities"] --> TYPES["5种歧义类型<br/>缺失实体/歧义实体/冲突实体<br/>模糊范围/不支持操作"]
    
    PCR["PCR noise + expectation"] -->|"高噪声+TOOL"| CONSERVATIVE["立即 ask_user<br/>保守策略"]
    PCR -->|"低噪声+ADVISOR"| RELAXED["放宽阈值<br/>允许自动推断"]
    
    TYPES --> AMBIGUITIES["Ambiguity[]"]
```

**实现**: `v3_common/intent_parser.py` L964-1026 `_detect_ambiguities()`  
**PCR 调控**: ❌ 当前不接收 noise_source 分类

### Stage 5: AmbiguityResolver (歧义消解)

```
3 种消解策略:
  自动消解:    上下文继承 · 默认值 · 高置信度推断
  延迟消解:    保留 Ambiguity · 标记 NEEDS_CLARIFICATION
  快速失败:    歧义过多 → 生成 clarification_message → ask_user
```

**实现**: `v3_common/intent_parser.py` L1026-1039 `_resolve_ambiguities()`

### Stage 6: ContextMerger (上下文合并)

```
跨轮实体继承 · 进程上下文继承 · 同义词归一化
受 PCR stability 调控: 稳定性 < 0.5 → 去除模糊词
```

### Stage 7: TaskGraphBuilder (任务图构建)

```mermaid
graph TD
    INTENT["Intent"] --> ATOMIC["原子意图映射<br/>单节点"]
    INTENT --> COMPOUND["复合意图分解<br/>多节点 + 依赖边"]
    
    PCR_EXP["PCR expectation"] -->|"TOOL"| SIMPLE["简化为单节点<br/>跳过分解"]
    PCR_EXP -->|"ADVISOR"| FULL["全量分解<br/>+自动追加解释性节点"]
    PCR_EXP -->|"COMPANION"| APPEND["末尾追加 ask_user 节点"]
    
    ATOMIC --> DAG["TaskGraph DAG<br/>{nodes, edges, dependencies}"]
    COMPOUND --> DAG
```

**实现**: `v3_common/intent_parser.py` L1080-1209 `_build_task_graph()`  
**PCR 调控**: ⚠️ expectation→graph策略 设计中已定义, 代码待接

---

## 四、PCR → IntentParser 完整调控表

```mermaid
graph LR
    subgraph PCR["PCR Output"]
        E["expectation"]
        N["noise_level"]
        C["complexity"]
        NS["noise_source"]
        P["prompt_style"]
    end

    subgraph IP["IntentParser 8 Stage"]
        S1["EntityExtractor"]
        S2["Classifier"]
        S3["Multi-Intent Split"]
        S4["AmbiguityDetector"]
        S6["ContextMerger"]
        S7["TaskGraphBuilder"]
    end

    E -->|"TOOL: 只地址/数值<br/>ADVISOR: +条件/函数"| S1
    E -->|"TOOL: 简化DAG<br/>ADVISOR: 全量+解释<br/>COMPANION: +ask_user"| S7

    N -->|"高→min_confidence↓<br/>低→严格匹配"| S2

    C -->|">0.8→max_sub_intents↑<br/><0.2→拆分跳过"| S3

    N -->|"高+TOOL→立即ask_user<br/>低+ADVISOR→放宽阈值"| S4

    NS -->|"context_break→<br/>context_window=20"| S6

    P -->|"BRIEF/EXPLANATORY<br/>→内容策略选择"| S6
```

---

## 五、意图类型体系

```mermaid
graph TD
    ROOT["IntentCategory"]

    ROOT --> C["C (Command)<br/>直接操作"]
    ROOT --> CR["CR (Create/Read)<br/>文件操作"]
    ROOT --> CRUD["CRUD<br/>完整数据操作"]
    ROOT --> QUERY["QUERY<br/>信息查询"]
    ROOT --> EXPLAIN["EXPLAIN<br/>解释说明"]
    ROOT --> ANALYZE["ANALYZE<br/>分析评估"]
    ROOT --> DEBUG["DEBUG<br/>调试排错"]
    ROOT --> SUGGEST["SUGGEST<br/>建议推荐"]
    ROOT --> CONFIRM["CONFIRM<br/>确认验证"]
    ROOT --> CLARIFY["CLARIFY<br/>澄清追问"]
    ROOT --> UNKNOWN["UNKNOWN<br/>无法分类"]

    C --> SUB_C["scan/read/write/patch/attach"]
    CR --> SUB_CR["create_file/read_file/list_dir"]
    QUERY --> SUB_Q["how/why/what/where"]
```

**实现**: `v3_common/intent_rule_registry.py` (304行) — 规则注册中心, 每种意图有 pattern + entity 组合规则

---

## 六、代码 ↔ 设计映射

```mermaid
graph TD
    subgraph DESIGN["设计文档"]
        D1["design_layer1_intent_parser.md<br/>532行 · v1.0"]
        D2["DESIGN_MULTI_TIER_PIPELINE.md<br/>多层递进"]
        D3["DESIGN_TIERED_ACTION_RESOLVER.md<br/>分级解析内核"]
        D4["ENGINEERING_INTENT_PARSER.md<br/>工程实现 · 端点"]
        D5["RECURSIVE-CONVERGENCE-MATCH.md<br/>递归收敛快匹配"]
    end

    subgraph CODE["代码实现"]
        C1["v3_common/intent_parser.py<br/>1209行 · 8阶段Pipeline"]
        C2["v3_common/intent_rule_registry.py<br/>304行 · 规则注册"]
        C3["v4/tiered/intent_parser.py<br/>112行 · TieredIntentParser"]
        C4["v4/tiered/pipeline.py<br/>137行 · MultiTierPipeline"]
        C5["v4/tiered/fusion.py<br/>111行 · 多源融合"]
        C6["v4/tiered/jieba_parser.py<br/>38行 · SVO提取"]
        C7["v4/tiered/stanza_parser.py<br/>117行 · 依存解析"]
    end

    D1 --> C1
    D2 --> C3
    D2 --> C4
    D3 -->|"共享内核模式"| C5
    D5 -->|"替代Tier0"| C5
```

---

## 七、接入 Engine 计划

```mermaid
gantt
    title IntentParser 接入路线
    dateFormat  YYYY-MM-DD
    section P0 核心
    接入 TieredIntentParser 到 on_event      :p0a, 2026-07-21, 1d
    8阶段 Pipeline 全部串联                    :p0b, after p0a, 1d
    section P1 PCR调控
    expectation→EntityExtractor 调控           :p1a, after p0b, 1d
    noise→Classifier 阈值调控                  :p1b, after p1a, 1d
    complexity→Multi-Intent Split 调控          :p1c, after p1b, 1d
    section P2 递归收敛
    递归收敛快匹配替代Tier0 正则               :p2a, after p1c, 2d
    反馈闭环 (Tier2→Tier0 缓存回写)           :p2b, after p2a, 1d
```

---

## 八、当前状态

```
✅ 代码: v3_common 1209行 + v4/tiered 1800行 = ~3000行
✅ 设计: 5篇核心文档
✅ 测试: v3_common 测试通过

❌ 接入 on_event: 0% — 未被调用
❌ PCR 调控: 0% — 8阶段不接收 PCR 信号
❌ 递归收敛快匹配: 0% — Tier0 仍用正则关键词
❌ 反馈闭环: 0% — Tier2 fallback 结果不回写 Tier0
```
