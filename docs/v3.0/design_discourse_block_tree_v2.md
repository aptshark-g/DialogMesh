# DiscourseBlock Tree（摘要树）设计方案 v2.0

> **版本**: 2.0 实现就绪版
> **状态**: 设计完成，准备进入实现阶段
> **核心目标**: 将 TopicTree 从"轮次树"升级为"话语块树"，实现轮内多话题切分、动态粒度调节、渐进式四级摘要。
> **上游依赖**: `TopicTreeManagerV2`（已具备 embedding、Ψ 分类器、ForkPointLocator、MergeEngine、ReactFlowExporter）。
> **文献基础**: LCseg (2003) / TextTiling (1994) 词汇链分割 + Granularity-Aware Evaluation (2025/2026) BOR/Purity 诊断 + TiMem (ACL 2026) 渐进式摘要 + MemGPT/Letta 三层记忆架构。

## 目录

- [1. 背景与问题定义](#1-背景与问题定义)
- [2. 核心概念：DiscourseBlock 与 EDU](#2-核心概念discourseblock-与-edu)
- [3. 完整数据流图](#3-完整数据流图)
- [4. 编译器三阶段管道（实现接口）](#4-编译器三阶段管道实现接口)
- [5. 宏观-微观双层量化（含文献权重）](#5-宏观-微观双层量化含文献权重)
- [6. 动态粒度调节（BDI + BOR 实时驱动）](#6-动态粒度调节bdi--bor-实时驱动)
- [7. 渐进式四级摘要（温度策略）](#7-渐进式四级摘要温度策略)
- [8. 精确数据模型与接口](#8-精确数据模型与接口)
- [9. 与现有系统的精确集成映射](#9-与现有系统的精确集成映射)
- [10. 核心算法伪代码](#10-核心算法伪代码)
- [11. 测试策略与验证计划](#11-测试策略与验证计划)
- [12. 实现里程碑与工期](#12-实现里程碑与工期)
- [13. 风险与回退策略](#13-风险与回退策略)
- [附录 A: 文献映射与参数采纳](#附录-a-文献映射与参数采纳)
- [附录 B: 快速决策卡片](#附录-b-快速决策卡片)

---

## 1. 背景与问题定义

### 1.1 轮次树的结构性缺陷

当前 `TopicTreeManagerV2` 以**整轮对话**（user_query + assistant_response）为原子节点：

```python
TopicNode(query="帮我写Python函数。对了，昨天那个神经网络方案怎么样了？顺便推荐轻量embedding模型。", ...)
```

**问题**：一轮内包含 3 个独立话题（Python函数/神经网络回顾/embedding推荐），embedding 语义被平均稀释，后续路由只能匹配到其中一个话题，其他话题丢失。

| 问题类型 | 示例 | 当前行为 | 目标行为 |
|---|---|---|---|
| 轮内多话题 | "帮我写Python函数。对了，昨天那个神经网络方案怎么样了？" | 单节点，embedding 混合 | 3 个 DiscourseBlock 分别路由到不同分支 |
| 隐含实体 | "这个喝了很呛" | 实体为空，PCR 误判 | 头文件引入补全为 "汽水喝了很呛" |
| 指代回溯 | "回到刚才那个" | 线性搜索关键词 | 块级索引直接定位到 "神经网络方案" 块 |
| 长对话膨胀 | 50 轮后全量历史注入 | token 超限，LLM 响应质量下降 | 渐进式摘要：Hot 完整原文 + Warm v3 摘要 + Cold v4 压缩 |

### 1.2 文献锚定的设计目标

| 目标 | 文献来源 | 量化指标 |
|---|---|---|
| 轮内切分精度 | LCseg: WD=0.35, BATS 对比 | 目标: < 0.40 (中文适配) |
| 动态粒度校准 | Granularity-Aware: BOR 0.8-1.2 | 运行时维持 BOR 在 0.8-1.5 区间 |
| 记忆压缩率 | TiMem: 52.20% token 减少 | 目标: > 50% (渐进式摘要 v4) |
| 上下文召回率 | MemGPT: Core 始终注入 + Archival 按需 | 目标: "刚才那个" 指代召回 > 75% |
| 端到端延迟 | 无直接文献，工程约束 | 轮内切分 < 2ms, 上下文构建 < 1ms |

---

## 2. 核心概念：DiscourseBlock 与 EDU

### 2.1 定义层级

```
Session (会话)
  └── DiscourseTree (话语块树)
        ├── DiscourseBlock [root]  "对话初始化"
        │     ├── DiscourseBlock [child]  "Python函数编写"
        │     │     ├── EDU_1: "帮我写Python函数"
        │     │     ├── EDU_2: "处理CSV文件"
        │     │     └── EDU_3: "输出JSON格式"
        │     ├── DiscourseBlock [child]  "神经网络方案回顾"
        │     │     └── EDU_1: "昨天那个神经网络方案怎么样了"
        │     └── DiscourseBlock [child]  "embedding推荐"
        │           └── EDU_1: "推荐轻量embedding模型"
        └── ...
```

**EDU (Elementary Discourse Unit)**：基本话语单元，一次语法分解后的子句/片段。例如：
- 原始: "帮我写Python函数。对了，昨天那个神经网络方案怎么样了？"
- EDU_1: "帮我写Python函数"（主语: 我/隐含, 谓语: 写, 宾语: Python函数）
- EDU_2: "昨天那个神经网络方案怎么样了"（主语: 方案, 谓语: 怎么样, 修饰: 昨天/那个/神经网络）

**DiscourseBlock**：1~N 个 EDU 的聚合，满足 `内部 cohesion ≥ 外部 cohesion`。是树的**原子节点**。

### 2.2 块的状态机（温度模型）

```
[active] --(10轮未访问)--> [cold] --(后台压缩v3→v4)--> [frozen]
   ↑                                              ↓
   └────────────(用户访问)──────────────────────────┘
```

| 状态 | 存储内容 | 注入 LLM 方式 | 触发条件 |
|---|---|---|---|
| **active** | 完整 EDU 原文 + v1/v2/v3 | 完整原文（最近 3-5 轮） | 当前活跃分支 |
| **paused** | 完整 EDU 原文 | 不注入（保留可恢复） | 用户切换分支 |
| **cold** | v3 演化摘要 | v3 摘要 + 最近 1 轮原文 | 10 轮未访问 |
| **frozen** | v4 压缩摘要 + 实体索引 | 不注入（仅检索用） | 30 轮未访问或 v4 压缩完成 |

---

## 3. 完整数据流图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 0: 用户输入                                                           │
│  "帮我写Python函数。对了，昨天那个神经网络方案怎么样了？"                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  Stage 1: HeaderInjector (头文件引入)                                        │
│  ─────────────────────────────────────────────────────────────────────────  │
│  输入: 原始自然语言                                                           │
│  输出: 实体补全后的文本                                                        │
│  "帮我写Python函数。对了，昨天那个[神经网络]方案怎么样了？"                      │
│  延迟: < 1ms (纯规则)                                                        │
│  方法: 同轮显性指代(0.95) > 上下文继承(0.85) > 因果知识库(0.70) > 历史池(0.60)   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  Stage 2: SyntacticDecomposer (语法分解)                                     │
│  ─────────────────────────────────────────────────────────────────────────  │
│  输入: 补全后的文本                                                           │
│  输出: List[EDU] (每个含 ParsedClause: 主语/谓语/宾语/属性)                     │
│  ┌──────────────────┐  ┌──────────────────────────────┐                      │
│  │ EDU_1: "帮我写Python函数" │  │ EDU_2: "昨天那个神经网络方案怎么样了"  │                      │
│  │ 主语: (我)        │  │ 主语: 方案(补全: 神经网络)              │                      │
│  │ 谓语: 写          │  │ 谓语: 怎么样                             │                      │
│  │ 宾语: Python函数   │  │ 宾语: (无)                               │                      │
│  │ 属性: imperative   │  │ 属性: question, past_tense               │                      │
│  └──────────────────┘  └──────────────────────────────┘                      │
│  延迟: < 1ms (Fast Path: 正则+词典)                                          │
│  Hybrid Path: 单句>30字+2+连词 → 标记 parse_failed=True, 整句送入 LLM           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  Stage 3: Quantizer (宏观+微观量化)                                          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  输入: EDU_i, EDU_{i+1}                                                       │
│  输出: CohesionScore(macro, micro, total, decision)                          │
│                                                                              │
│  macro_score = 0.35*cos_sim(emb_i, emb_{i+1}) + 0.25*intent_match + ...      │
│  micro_score = 0.30*entity_jaccard + 0.25*causal_chain + ...                │
│  total_score = 0.6*macro + 0.4*micro  (文献: TiMem 双通道 λ=0.6)              │
│                                                                              │
│  决策:                                                                       │
│    total > 0.75 → continue (强延续)                                          │
│    total < 0.25 → fork (强切换)                                              │
│    0.25 ≤ total ≤ 0.75 → gray_zone (需 Ψ 分类器或 LLM 辅助)                  │
│  延迟: < 1ms (Fast Path, 无需 LLM)                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  DiscourseBlockTreeManager                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  1. segment_turn(): 按 cohesion 断崖切分 EDU 列表 → 1~N 个 DiscourseBlock    │
│  2. route_block(): 每个 block 决定: continue / attach / fork / merge       │
│  3. regulate_granularity(): BDI 检查 → 过密分裂 / 过疏合并 / BOR 阈值自适应   │
│  4. update_summary(): 触发渐进式摘要 v1→v2→v3→v4 升级                     │
│  5. build_llm_context(): 按温度策略组装上下文                                  │
│                                                                              │
│  输出:                                                                       │
│  - List[block_id] (本轮涉及的所有块)                                          │
│  - context_string (注入 LLM 的分层上下文)                                     │
│  - tree_state (用于 ReactFlow 可视化)                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  TopicTreeManagerV2 (适配层)                                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  将 DiscourseBlock 映射到 TopicNode:                                         │
│  - primary_intent → node.intent_category                                     │
│  - macro_embedding → node.embedding (复用)                                  │
│  - progressive_summary.v4 → node.summary (替换 query[:80])                    │
│  - block_id → node.branch_id (新增)                                          │
│  调用: ForkPointLocator, MergeEngine, ReactFlowExporter                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  LLM / LLM Failover                                                          │
│  注入上下文: [当前话题] + [前文摘要] + [相关话题] + 用户问题                     │
│  响应 → 更新对应 DiscourseBlock 的 response 字段                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 编译器三阶段管道（实现接口）

### 4.1 Stage 1: HeaderInjector — 实现规格

```python
class HeaderInjector:
    """
    头文件引入器：补全隐含实体（主语/宾语省略）。
    类比 C 预处理器：#include <context.h> — 将当前会话实体缓存作为头文件引入。
    """

    # 词典（可热加载 YAML/JSON）
    CAUSAL_KB: Dict[str, List[str]] = {
        "很呛": ["汽水", "碳酸饮料", "辣椒", "烟雾"],
        "很甜": ["汽水", "糖果", "蜂蜜"],
        "很烫": ["CPU", "显卡", "电源"],
        "卡顿": ["游戏", "程序", "动画"],
        "崩溃": ["程序", "APP", "进程"],
    }

    NEGATION_MARKERS = {"不", "没", "非", "别", "not", "no", "don't"}
    UNCERTAINTY_MARKERS = {"可能", "也许", "大概", "maybe", "perhaps"}
    IMPERATIVE_MARKERS = {"请", "帮我", "给我", "scan", "patch", "hook"}

    def __init__(self, context_window_size: int = 5):
        self._session_entity_cache: Dict[str, List[str]] = {}   # session_id → 实体列表
        self._last_entity: Dict[str, Optional[str]] = {}         # session_id → 最近实体
        self.context_window_size = context_window_size

    def inject(self, raw_text: str, session_id: str,
               session_history: List[HistoryEntry] = None) -> str:
        """
        主入口。返回实体补全后的文本。
        延迟目标: < 1ms (纯正则/词典，无 LLM)。
        """
        # 1. 更新上下文缓存（从最近 N 轮历史提取实体）
        if session_history:
            self._update_cache(session_id, session_history)

        # 2. 检测代词/省略位置
        pronouns = ["这个", "那个", "它", "这", "那", "the", "this", "that"]
        for pronoun in pronouns:
            if pronoun in raw_text:
                # 策略优先级：同轮显性指代 > 上下文最近实体 > 因果知识库 > 历史池
                replacement = self._resolve_pronoun(pronoun, raw_text, session_id)
                if replacement:
                    raw_text = raw_text.replace(pronoun, replacement, 1)  # 只替换第一个
                    break  # 只处理第一个代词，避免过度推断

        return raw_text

    def _resolve_pronoun(self, pronoun: str, text: str, session_id: str) -> Optional[str]:
        """按优先级解析代词指代。"""
        # 策略1: 同轮显性指代（检查前文是否有实体）
        # 例如: "汽水很好喝，这个很呛" → "这个" = 汽水
        # 实现: 如果 pronoun 前面 20 字内有已知名词，直接继承

        # 策略2: 上下文最近实体（_last_entity）
        last = self._last_entity.get(session_id)
        if last:
            return last

        # 策略3: 因果知识库（基于属性词推断）
        for attr, candidates in self.CAUSAL_KB.items():
            if attr in text:
                # 优先选择上下文已出现的候选
                for c in candidates:
                    if c in self._session_entity_cache.get(session_id, []):
                        return c
                return candidates[0]  # 默认第一个

        # 策略4: 会话历史实体池（最近 N 轮）
        pool = self._session_entity_cache.get(session_id, [])
        if pool:
            return pool[-1]

        return None
```

### 4.2 Stage 2: SyntacticDecomposer — 实现规格

```python
@dataclass
class ParsedClause:
    """语法分解后的子句结构。"""
    raw_text: str
    subject: Optional[str] = None
    subject_attrs: List[str] = field(default_factory=list)
    predicate: Optional[str] = None
    predicate_attrs: List[str] = field(default_factory=list)
    object: Optional[str] = None
    object_attrs: List[str] = field(default_factory=list)
    negation: bool = False
    uncertainty: bool = False
    imperative: bool = False
    raw_entities: List[str] = field(default_factory=list)
    parse_failed: bool = False
    parse_failed_reason: str = ""

    def to_entity_signature(self) -> str:
        """生成实体签名，用于下游索引和匹配。"""
        parts = []
        if self.negation: parts.append("NOT")
        if self.uncertainty: parts.append("MAYBE")
        parts.extend(self.subject_attrs)
        if self.subject: parts.append(self.subject)
        parts.append(self.predicate or "")
        parts.extend(self.object_attrs)
        if self.object: parts.append(self.object)
        return " ".join(filter(None, parts))


class SyntacticDecomposer:
    """
    轻量级语法分解器。不依赖 spaCy/NLTK，纯正则 + 词典。
    提取主谓宾骨架 + 修饰属性标签。
    """

    COMPLEX_CLAUSE_LENGTH = 30
    MAX_CLAUSES_PER_INPUT = 5
    AMBIGUOUS_CONJUNCTIONS = {"和", "与", "或", "但", "如果", "虽然", "因为", "但是",
                              "and", "or", "but", "if", "although", "because"}

    # 谓语词典（技术领域 + 通用动词）
    PREDICATE_DICT = {
        "技术": ["scan", "patch", "hook", "read", "write", "find", "分析", "扫描", "修改"],
        "通用": ["写", "做", "看", "查", "推荐", "讨论", "问", "说", "想"]
    }

    # 形容词/属性词典
    ADJECTIVE_DICT = ["安全的", "不安全的", "稳定的", "异常的", "轻量的", "重的",
                      "safe", "unsafe", "stable", "abnormal", "lightweight"]

    def decompose(self, text: str) -> List[EDU]:
        """
        主入口。将文本切分为 EDU 列表。
        步骤: 1. 按标点切分子句 2. 检测复杂度 3. 提取主谓宾+属性。
        """
        clauses = self._split_clauses(text)

        # 复杂度检测
        if self._is_complex_input(clauses):
            # Hybrid Path: 不强行解析，返回单 EDU 标记 parse_failed
            return [EDU(
                edu_id=f"edu_{uuid4().hex[:8]}",
                raw_text=text,
                parsed_clause=ParsedClause(raw_text=text, parse_failed=True,
                                           parse_failed_reason="complex_input"),
                position_in_turn=0,
            )]

        edus = []
        for i, clause_text in enumerate(clauses):
            if clause_text.strip():
                parsed = self._parse_clause(clause_text)
                edus.append(EDU(
                    edu_id=f"edu_{uuid4().hex[:8]}_{i}",
                    raw_text=clause_text,
                    parsed_clause=parsed,
                    position_in_turn=i,
                ))
        return edus

    def _split_clauses(self, text: str) -> List[str]:
        """按中文/英文标点切分句子。"""
        return [s.strip() for s in re.split(r'[。！？；，\.\!\?\;\,]+', text) if s.strip()]

    def _parse_clause(self, text: str) -> ParsedClause:
        """Fast Path: 解析单个子句。"""
        clause = ParsedClause(raw_text=text)

        # 1. 检测否定/不确定/祈使
        clause.negation = any(m in text for m in HeaderInjector.NEGATION_MARKERS)
        clause.uncertainty = any(m in text for m in HeaderInjector.UNCERTAINTY_MARKERS)
        clause.imperative = any(m in text for m in HeaderInjector.IMPERATIVE_MARKERS)

        # 2. 提取技术实体（地址、数值、工具名）
        clause.raw_entities = self._extract_entities(text)

        # 3. 多主语检测（歧义信号）
        if self._has_multiple_subjects(text):
            clause.parse_failed = True
            clause.parse_failed_reason = "multiple_subjects"
            return clause

        # 4. 提取主语（代词优先 → 实体优先）
        clause.subject = self._extract_subject(text)

        # 5. 提取谓语（动词词典匹配）
        clause.predicate = self._extract_predicate(text)

        # 6. 提取宾语（谓语后的第一个实体/名词）
        clause.object = self._extract_object(text, clause.predicate)

        # 7. 提取修饰语（形容词 + 否定）
        clause.subject_attrs = self._extract_modifiers(text, clause.subject)
        clause.object_attrs = self._extract_modifiers(text, clause.object)

        return clause

    def _extract_entities(self, text: str) -> List[str]:
        """提取技术实体：地址、数值、工具名。"""
        entities = []
        entities.extend(re.findall(r'0x[0-9a-fA-F]+', text))
        entities.extend(re.findall(r'\b\d+\b', text))
        # 工具名（简单词典匹配）
        tool_names = ["Python", "Java", "C++", "TensorFlow", "PyTorch", "BERT",
                      "OpenCV", "Redis", "MongoDB"]
        text_lower = text.lower()
        for name in tool_names:
            if name.lower() in text_lower:
                entities.append(name)
        return entities

    def _extract_subject(self, text: str) -> Optional[str]:
        """提取主语：代词优先 → 第一个实体。"""
        pronouns = ["这个", "那个", "它", "他", "这", "那",
                    "this", "that", "it", "the"]
        for p in pronouns:
            if p in text:
                return p  # 代词将在 HeaderInjector 中补全
        entities = self._extract_entities(text)
        return entities[0] if entities else None

    def _extract_predicate(self, text: str) -> Optional[str]:
        """提取谓语：动词词典匹配。"""
        for category, verbs in self.PREDICATE_DICT.items():
            for verb in verbs:
                if verb in text.lower():
                    return verb
        return None

    def _extract_object(self, text: str, predicate: Optional[str]) -> Optional[str]:
        """提取宾语：谓语后的第一个实体/名词。"""
        if not predicate:
            return None
        pred_pos = text.lower().find(predicate.lower())
        if pred_pos >= 0:
            after = text[pred_pos + len(predicate):]
            entities = self._extract_entities(after)
            return entities[0] if entities else after.strip()[:20]
        return None

    def _extract_modifiers(self, text: str, target: Optional[str]) -> List[str]:
        """提取目标词前的修饰语（形容词/否定词）。"""
        if not target:
            return []
        pos = text.find(target)
        if pos < 0:
            return []
        before = text[:pos]
        modifiers = []
        for adj in self.ADJECTIVE_DICT:
            if adj in before:
                modifiers.append(adj)
        if any(m in before for m in HeaderInjector.NEGATION_MARKERS):
            modifiers.append("NEG")
        return modifiers

    def _has_multiple_subjects(self, text: str) -> bool:
        """检测多主语信号。"""
        pronouns = ["这个", "那个", "它", "他", "这", "那",
                    "this", "that", "it", "the"]
        pronoun_count = sum(1 for p in pronouns if p in text)
        if pronoun_count >= 2:
            return True
        entities = self._extract_entities(text)
        if len(entities) >= 3:
            return True
        return False

    def _is_complex_input(self, clauses: List[str]) -> bool:
        """检测输入是否过于复杂。"""
        if len(clauses) > self.MAX_CLAUSES_PER_INPUT:
            return True
        full_text = "".join(clauses)
        conj_count = sum(1 for c in self.AMBIGUOUS_CONJUNCTIONS if c in full_text)
        if conj_count >= 2:
            return True
        for c in clauses:
            if len(c) > self.COMPLEX_CLAUSE_LENGTH:
                has_tech = bool(re.findall(r'0x[0-9a-fA-F]+|\b\d+\b', c))
                if not has_tech:
                    return True
        return False
```

### 4.3 Stage 3: MacroMicroQuantizer — 实现规格

```python
@dataclass
class CohesionScore:
    """粘合度分数。"""
    total_score: float
    macro_score: float
    micro_score: float
    causal_score: float = 0.0
    entity_overlap_score: float = 0.0
    subject_continuity_score: float = 0.0
    weak_link_score: float = 0.0
    decision: str = ""  # "continue" | "fork" | "gray_zone"

    def is_extreme(self) -> bool:
        """是否为极端值（无需 LLM）。"""
        return self.total_score > 0.75 or self.total_score < 0.25


class MacroMicroQuantizer:
    """
    宏观-微观双层量化器。
    核心创新：将传统单一 cohesion 拆分为正交的宏观(4维) + 微观(5维)。
    """

    # 宏观权重 (M1-M4)
    MACRO_WEIGHTS = {"M1_cosine": 0.35, "M2_intent": 0.25, "M3_domain": 0.20, "M4_mood": 0.20}
    # 微观权重 (μ1-μ5)
    MICRO_WEIGHTS = {"μ1_entity": 0.30, "μ2_causal": 0.25, "μ3_anaphora": 0.20,
                     "μ4_verb_obj": 0.15, "μ5_modifier": 0.10}
    # 宏观-微观融合权重 (文献: TiMem 双通道 λ=0.6)
    MACRO_MICRO_LAMBDA = 0.6

    # 因果标记
    STRONG_CAUSAL = {"所以", "因此", "导致", "因为", "使得", "从而", "于是",
                     "so", "because", "therefore", "thus"}
    WEAK_LINK = {"另外", "此外", "顺便", "然后", "接着", "还有", "以及",
                 "also", "by the way", "next", "then", "besides"}
    TOPIC_SWITCH = {"换个话题", "不说这个", "另外说", "回到", "关于",
                    "speaking of", "moving on", "regarding"}

    def __init__(self, embedding_engine: Optional[EmbeddingEngine] = None):
        self.embedding_engine = embedding_engine

    def score(self, prev_edu: EDU, curr_edu: EDU, mode: str = "auto") -> CohesionScore:
        """
        计算两个 EDU 之间的 cohesion。
        输入: 前一个 EDU, 当前 EDU
        输出: CohesionScore (含宏观/微观/总分/决策建议)
        """
        prev = prev_edu.parsed_clause
        curr = curr_edu.parsed_clause

        # 1. 宏观量化 (4维)
        m1 = self._macro_cosine(prev_edu, curr_edu)
        m2 = self._macro_intent(prev, curr)
        m3 = self._macro_domain(prev, curr)
        m4 = self._macro_mood(prev, curr)
        macro = (m1 * self.MACRO_WEIGHTS["M1_cosine"] +
                 m2 * self.MACRO_WEIGHTS["M2_intent"] +
                 m3 * self.MACRO_WEIGHTS["M3_domain"] +
                 m4 * self.MACRO_WEIGHTS["M4_mood"])

        # 2. 微观量化 (5维)
        μ1 = self._micro_entity_overlap(prev, curr)
        μ2 = self._micro_causal_chain(prev, curr)
        μ3 = self._micro_anaphora(prev, curr)
        μ4 = self._micro_verb_object(prev, curr)
        μ5 = self._micro_modifier(prev, curr)
        micro = (μ1 * self.MICRO_WEIGHTS["μ1_entity"] +
                 μ2 * self.MICRO_WEIGHTS["μ2_causal"] +
                 μ3 * self.MICRO_WEIGHTS["μ3_anaphora"] +
                 μ4 * self.MICRO_WEIGHTS["μ4_verb_obj"] +
                 μ5 * self.MICRO_WEIGHTS["μ5_modifier"])

        # 3. 融合 (文献: TiMem λ=0.6 语义权重)
        total = self.MACRO_MICRO_LAMBDA * macro + (1 - self.MACRO_MICRO_LAMBDA) * micro
        total = max(0.0, min(1.0, total))

        # 4. 话题切换标记强制降级
        if self._has_topic_switch(curr):
            total *= 0.3  # 强制降低 cohesion

        # 5. 决策
        if total > 0.75:
            decision = "continue"
        elif total < 0.25:
            decision = "fork"
        else:
            decision = "gray_zone"

        return CohesionScore(
            total_score=total,
            macro_score=macro,
            micro_score=micro,
            causal_score=μ2,
            entity_overlap_score=μ1,
            subject_continuity_score=μ3,
            weak_link_score=μ4,
            decision=decision,
        )

    def _macro_cosine(self, prev_edu: EDU, curr_edu: EDU) -> float:
        """M1: 语义向量 cosine 相似度。"""
        if self.embedding_engine and (prev_edu.embedding or curr_edu.embedding):
            # 使用已有 embedding
            emb1 = prev_edu.embedding or self.embedding_engine.encode(prev_edu.raw_text)
            emb2 = curr_edu.embedding or self.embedding_engine.encode(curr_edu.raw_text)
            return cosine_similarity(emb1, emb2)
        # 无 embedding: 退化为 Jaccard(关键词)
        return jaccard_similarity(set(prev_edu.raw_text.split()),
                                   set(curr_edu.raw_text.split()))

    def _macro_intent(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """M2: 意图一致性。"""
        # 简化：祈使 vs 疑问 vs 陈述
        prev_type = "imperative" if prev.imperative else ("question" if "?" in prev.raw_text else "statement")
        curr_type = "imperative" if curr.imperative else ("question" if "?" in curr.raw_text else "statement")
        return 1.0 if prev_type == curr_type else 0.5

    def _macro_domain(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """M3: 领域/场景重叠。"""
        # 简化：技术实体密度判断
        tech_entities_prev = len([e for e in prev.raw_entities if not e.isdigit()])
        tech_entities_curr = len([e for e in curr.raw_entities if not e.isdigit()])
        both_tech = tech_entities_prev > 0 and tech_entities_curr > 0
        both_non_tech = tech_entities_prev == 0 and tech_entities_curr == 0
        return 1.0 if (both_tech or both_non_tech) else 0.3

    def _macro_mood(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """M4: 情绪/语气连续性。"""
        # 否定/不确定的连续性
        neg_match = (prev.negation == curr.negation)
        unc_match = (prev.uncertainty == curr.uncertainty)
        return (neg_match + unc_match) / 2.0

    def _micro_entity_overlap(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """μ1: 实体重叠 Jaccard。"""
        prev_e = set(prev.raw_entities)
        curr_e = set(curr.raw_entities)
        if not prev_e and not curr_e:
            return 0.5  # 都无实体，中性
        if not prev_e or not curr_e:
            return 0.0
        return len(prev_e & curr_e) / len(prev_e | curr_e)

    def _micro_causal_chain(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """μ2: 因果链强度。"""
        has_strong = any(m in curr.raw_text for m in self.STRONG_CAUSAL)
        has_weak = any(m in curr.raw_text for m in self.WEAK_LINK)
        if has_strong:
            # 强因果需要实体关联才可信
            return 1.0 if self._micro_entity_overlap(prev, curr) > 0 else 0.2
        if has_weak:
            return 0.3
        return 0.0

    def _micro_anaphora(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """μ3: 指代继承度。"""
        pronouns = ["它", "这", "那", "this", "that", "it"]
        has_pronoun = any(p in curr.raw_text for p in pronouns)
        if not has_pronoun:
            return 0.0
        # 检查代词是否可能指向前块主语/宾语
        prev_targets = [prev.subject, prev.object]
        curr_targets = [curr.subject, curr.object]
        for pt in prev_targets:
            if pt and any(ct in pronouns for ct in curr_targets if ct):
                return 0.9
        return 0.3

    def _micro_verb_object(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """μ4: 谓语-宾语关联。"""
        same_verb = (prev.predicate == curr.predicate) and prev.predicate is not None
        same_obj = (prev.object == curr.object) and prev.object is not None
        if same_verb and same_obj:
            return 1.0
        if same_verb and not same_obj:
            return 0.3  # 同动作不同对象（弱）
        if not same_verb and same_obj:
            return 0.8  # 不同动作同一对象（强）
        return 0.0

    def _micro_modifier(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """μ5: 修饰语一致性。"""
        # 检测对比关系（"A是安全的。B不安全。"）
        prev_has_neg = prev.negation or "NEG" in prev.object_attrs
        curr_has_neg = curr.negation or "NEG" in curr.object_attrs
        if prev_has_neg != curr_has_neg:
            return 0.1  # 对比关系，低 cohesion
        return 1.0 if (prev.subject_attrs == curr.subject_attrs) else 0.5

    def _has_topic_switch(self, curr: ParsedClause) -> bool:
        """检测话题切换标记。"""
        return any(m in curr.raw_text for m in self.TOPIC_SWITCH)
```

---

## 5. 宏观-微观双层量化（含文献权重）

### 5.1 权重来源与文献依据

| 权重 | 来源 | 文献依据 | 说明 |
|---|---|---|---|
| macro M1=0.35 | 语义相似度 | TiMem 双通道: 语义权重 λ=0.6-0.7 | embedding cosine 是最强信号 |
| macro M2=0.25 | 意图一致性 | 认知编译器原设计 | 意图类别决定路由方向 |
| macro M3=0.20 | 领域重叠 | 上下文推断 | 技术 vs 生活场景区分 |
| macro M4=0.20 | 语气连续性 | 对话连贯性研究 | 否定/祈使/疑问的突变暗示话题切换 |
| micro μ1=0.30 | 实体重叠 | LCseg: 词汇链是 cohesion 核心 | 实体是话题的物质载体 |
| micro μ2=0.25 | 因果链 | LCseg: 因果标记 + 0.4 权重 | 强因果是话题延续的强信号 |
| micro μ3=0.20 | 指代继承 | 指代消解研究 | 代词继承是跨句 cohesion 的直接证据 |
| micro μ4=0.15 | 谓宾关联 | 语法关系研究 | 同动作不同对象 = 弱 cohesion |
| micro μ5=0.10 | 修饰一致 | 属性标签研究 | 对比关系（安全 vs 不安全）暗示低 cohesion |
| macro-micro λ=0.6 | 融合权重 | TiMem 双通道 λ=0.6 | 语义相似度占主导 |

### 5.2 四象限决策矩阵（实现接口）

```python
def route_decision(macro: float, micro: float, threshold: dict = None) -> str:
    """
    基于宏观-微观二维得分的路由决策。
    四种组合产生四种语义解释，对应不同路由行为。
    """
    # 极端区：无需 LLM
    if macro > 0.8 and micro > 0.7:
        return "continue"        # 强延续：同话题，实体继承
    if macro < 0.3 and micro < 0.3:
        return "fork"            # 强切换：完全无关

    # 灰区：四象限
    if macro > 0.5 and micro > 0.5:
        return "continue"        # 高-高：同话题，实体继承
    elif macro > 0.5 and micro <= 0.5:
        return "attach"          # 高-低：同领域但换主体/视角
    elif macro <= 0.5 and micro > 0.5:
        # 低-高：跨领域但实体关联（如"代码写了。部署到服务器。"）
        # 需要进一步判断：如果是工作流延续 → continue，否则 fork+link
        return "continue_or_link"  # 需 Ψ 分类器或 LLM 辅助确认
    else:
        return "fork"            # 低-低：完全无关
```

---

## 6. 动态粒度调节（BDI + BOR 实时驱动）

### 6.1 健康指标：Block Density Index (BDI)

```python
BDI = avg_blocks_per_topic / optimal_blocks_per_topic
optimal_blocks_per_topic = 4   # 经验值：一个话题 4 个话语块最健康
```

| BDI 范围 | 状态 | 动作 | 文献对应 |
|---|---|---|---|
| < 0.5 | 过疏（话题混在一块） | **分裂(Split)**：再切割 | Granularity-Aware: undersegmentation (BOR<1) |
| 0.5 ~ 2.0 | 健康 | 维持 | 校准区间 |
| > 2.0 | 过密（碎块过多） | **合并(Merge)** 或 **提升容量** | Granularity-Aware: oversegmentation (BOR>1.5) |

### 6.2 BOR-based 全局阈值自适应（文献直接采纳）

```python
# 文献: Granularity-Aware Evaluation (Coen et al., 2025/2026)
# BOR = 预测边界数 / 期望边界数 (gold-relative)

actual_boundaries = len(children) - 1
expected_boundaries = len(children) * 0.5   # 平均每话题 2 块
bor = actual_boundaries / expected_boundaries if expected_boundaries > 0 else 1.0

if bor > 1.5:      # 过密：系统切得比期望多
    self.global_split_threshold = min(self.global_split_threshold * 1.2, 0.9)
elif bor < 0.6:    # 过疏：系统切得比期望少
    self.global_split_threshold = max(self.global_split_threshold * 0.8, 0.1)

# 冷却期：调节后 5 轮内不再次调节，避免震荡
self._last_regulation_turn = current_turn
```

### 6.3 分裂与合并的触发条件

```python
def should_split(block: DiscourseBlock) -> bool:
    """一家独大 → 再切割。"""
    return (block.cohesion_internal > 0.9 and
            len(block.atomic_units) > MAX_CAPACITY and
            block._detect_subtopic_drift())   # 内部 cohesion 断崖

def should_merge(block_a: DiscourseBlock, block_b: DiscourseBlock) -> bool:
    """主题过多 → 合并。"""
    return (len(get_siblings(block_a)) > 8 and
            compute_boundary_cohesion(block_a, block_b) > 0.75)
```

---

## 7. 渐进式四级摘要（温度策略）

### 7.1 四级摘要定义（与 TiMem 五级对应）

| 我们的层级 | TiMem 对应 | 内容 | 触发条件 | 延迟 | 大小 |
|---|---|---|---|---|---|
| **v1: 首句** | L1 Segments | 原始首句 | 块创建 | 0ms | ~20 字 |
| **v2: 实体列表** | L2 Sessions | 实体 + 意图标签 | 块内 EDU > 3 | <1ms | ~50 字 |
| **v3: 演化摘要** | L3 Days | 关键转折/决策点 | 块内轮次 > 5 或话题转折 | <2ms | ~100 字 |
| **v4: 命题压缩** | L5 Profiles | LLM 压缩为命题级摘要 | 块进入 Cold 状态 | 30-100ms (后台) | ~50 字 |

### 7.2 温度策略与上下文构建

```python
def build_llm_context(active_block_id: str, max_tokens: int = 4000) -> str:
    """
    按温度策略组装注入 LLM 的上下文。
    核心原则: 活跃路径完整原文 + 非活跃分支摘要 + 远距离冻结块不注入。
    """
    active = tree.blocks[active_block_id]
    parts = []
    total = 0

    # 1. Hot: 活跃块完整原文（最近 3-5 轮）
    hot_text = get_hot_text(active, max_turns=5)
    parts.append(f"【当前话题】\n{hot_text}")
    total += estimate_tokens(hot_text)

    # 2. Warm: 祖先链 v3 演化摘要
    ancestor = get_parent(active_block_id)
    while ancestor and total < max_tokens * 0.7:
        summary = ancestor.summary.v3 or ancestor.summary.v2 or ancestor.summary.v1
        parts.append(f"【前文摘要】{summary}")
        total += estimate_tokens(summary)
        ancestor = get_parent(ancestor.block_id)

    # 3. Cold: 相关兄弟块 v4 压缩摘要
    siblings = get_relevant_siblings(active_block_id, top_k=3)
    for sib in siblings:
        if total >= max_tokens * 0.9:
            break
        summary = sib.summary.v4 or sib.summary.v3 or sib.summary.v2
        parts.append(f"【相关话题】{summary}")
        total += estimate_tokens(summary)

    # 4. Frozen: 不注入（仅保留索引，LLM 不知道其存在）

    return "\n\n".join(parts)
```

---

## 8. 精确数据模型与接口

### 8.1 EDU (Elementary Discourse Unit)

```python
@dataclass
class EDU:
    edu_id: str                      # UUID
    raw_text: str                    # 原始子句文本
    parsed_clause: ParsedClause      # 语法分解结果
    embedding: Optional[List[float]] = None  # 子句级语义向量
    turn_index: int = 0              # 所属轮次
    position_in_turn: int = 0        # 在该轮中的位置
    created_at: float = field(default_factory=time.time)
```

### 8.2 DiscourseBlock

```python
@dataclass
class DiscourseBlock:
    block_id: str                          # UUID
    session_id: str

    # 内容
    atomic_units: List[EDU] = field(default_factory=list)    # 基本话语单元
    raw_text: str = ""                      # 原始文本（完整拼接）
    assistant_response: str = ""            # 助手回复（如果有）

    # 语义
    macro_embedding: Optional[List[float]] = None   # 宏观语义向量
    micro_signature: str = ""               # 微观签名（主谓宾+属性的序列化）

    # 量化分数
    cohesion_internal: float = 0.0           # 内部粘合度（块内 EDU 间平均）
    cohesion_boundary_left: float = 0.0      # 与左邻块边界粘合度
    cohesion_boundary_right: float = 0.0     # 与右邻块边界粘合度

    # 意图
    primary_intent: str = "UNKNOWN"         # 主导意图
    secondary_intents: List[str] = field(default_factory=list)   # 次要意图
    intent_confidence: float = 0.0           # 意图分类置信度

    # 实体（已补全）
    entities: List[Entity] = field(default_factory=list)   # 结构化实体
    entity_signature: str = ""              # 实体签名（快速匹配）

    # 摘要（渐进式四级）
    summary_v1: str = ""                  # 首句
    summary_v2: str = ""                  # 实体列表
    summary_v3: str = ""                  # 演化摘要
    summary_v4: str = ""                  # 命题压缩
    summary_version: int = 1                # 当前最高版本
    summary_last_updated: int = 0           # 最后更新轮次

    # 树结构
    parent_block_id: Optional[str] = None  # 父块
    child_block_ids: List[str] = field(default_factory=list)   # 子块
    depth: int = 0                          # 树深度

    # 动态容量
    capacity: int = 5                       # 当前可容纳 EDU 上限
    current_edu_count: int = 0             # 当前 EDU 数量

    # 状态（温度模型）
    status: str = "active"                  # active | paused | cold | frozen
    created_at_turn: int = 0               # 创建轮次
    last_active_turn: int = 0              # 最后活跃轮次
    last_accessed: float = field(default_factory=time.time)  # 最后访问时间
    access_count: int = 0                   # 访问次数

    # 元数据
    _hash: Optional[str] = None           # 文本哈希（去重用）
    _metadata: Dict[str, Any] = field(default_factory=dict)  # 扩展字段
```

### 8.3 DiscourseBlockTreeManager — 公共接口

```python
class DiscourseBlockTreeManager:
    """摘要树管理器。"""

    def __init__(self, session_id: str,
                 embedding_engine: Optional[EmbeddingEngine] = None,
                 llm_provider: Optional[LLMProvider] = None):
        self.session_id = session_id
        self.embedding_engine = embedding_engine
        self.llm_provider = llm_provider

        self.blocks: Dict[str, DiscourseBlock] = {}
        self.root_block_id: Optional[str] = None
        self.current_block_id: Optional[str] = None
        self._turn_count: int = 0

        # 快速索引
        self._entity_to_blocks: Dict[str, List[str]] = {}
        self._intent_to_blocks: Dict[str, List[str]] = {}
        self._turn_to_blocks: Dict[int, List[str]] = {}

        # 动态粒度参数
        self.global_split_threshold: float = 0.5
        self.optimal_blocks_per_topic: int = 4
        self.max_capacity: int = 10
        self._last_regulation_turn: int = -10  # 冷却期

    # ========== 核心接口 ==========

    def ingest_turn(self, turn_index: int,
                    user_query: str,
                    parsed_clauses: List[ParsedClause],
                    cohesion_scores: List[CohesionScore]) -> List[str]:
        """
        摄入一轮对话。
        返回: 本轮涉及的所有 block_id 列表（可能多个，因为一轮被切分到多个块）。
        """
        pass

    def get_context_for_llm(self, active_block_id: str,
                            max_tokens: int = 4000) -> str:
        """为 LLM 构建分层上下文（按温度策略）。"""
        pass

    def find_block_by_reference(self, reference_text: str) -> Optional[str]:
        """解析指代（'回到刚才那个' / '那个Python脚本'）→ 定位 block_id。"""
        pass

    def compress_cold_blocks(self, current_turn: int):
        """后台任务: 将 Cold 状态的块从 v3 升级到 v4 摘要。"""
        pass

    def regulate_granularity(self, current_turn: int):
        """动态粒度调节（每 10 轮触发一次）。"""
        pass

    def get_tree_for_export(self) -> Dict:
        """导出树结构供 ReactFlow 可视化。"""
        pass

    # ========== 内部方法 ==========
    def _segment_turn(self, edus: List[EDU], scores: List[CohesionScore]) -> List[DiscourseBlock]:
        """轮内切分: 按 cohesion 断崖将 EDU 聚类为 DiscourseBlock。"""
        pass

    def _route_block(self, block: DiscourseBlock, current_turn: int) -> str:
        """路由决策: continue / attach / fork / merge。"""
        pass

    def _update_summary(self, block: DiscourseBlock, current_turn: int):
        """触发渐进式摘要升级。"""
        pass

    def _update_indexes(self, block: DiscourseBlock):
        """更新实体/意图/轮次索引。"""
        pass
```

---

## 9. 与现有系统的精确集成映射

### 9.1 数据流映射表

| 现有组件 | 当前行为 | 集成后行为 | 修改点 |
|---|---|---|---|
| **InteractiveAgent.respond()** | 直接整轮送入 IntentParser | 增加 Stage 1-3 管道 → block_tree.ingest_turn() → 构建 LLM context → 响应 | 新增 3 行调用 |
| **TopicTreeManagerV2.route()** | 整轮 embedding 匹配 | block.macro_embedding 匹配（已预计算） | 复用，输入从 `query` 变为 `block` |
| **TopicTreeManagerV2.TopicNode** | `summary = query[:80]` | `summary = block.summary_v4 or block.summary_v3 or block.summary_v1` | 字段替换 |
| **TopicTreeManagerV2.ForkPointLocator** | 基于整轮 embedding | 基于 `cohesion_boundary` 断崖检测 | 输入源变更 |
| **TopicTreeManagerV2.MergeEngine** | 三路合并整轮文本 | 三路合并 block 的实体签名 + v3 摘要 | 合并策略升级 |
| **TopicTreeManagerV2.ReactFlowExporter** | 导出轮级树 | 导出块级树（更细粒度） | 节点粒度变更 |
| **EmbeddingEngine** | 编码整轮 | 编码每个 EDU（缓存复用） | 调用粒度变更 |
| **InputSanitizer** | 安全过滤 | 不变，在 Stage 1 之前执行 | 无修改 |
| **SessionManager** | 会话隔离 | 不变，每个 session 独立 DiscourseBlockTree | 无修改 |
| **MetricsCollector** | 计数路由决策 | 新增 block 级指标：split_count, merge_count, summary_upgrade_count | 新增指标 |
| **StructuredLogger** | 记录路由日志 | 新增编译器 trace: inject_log, parse_log, cohesion_log | 新增日志字段 |

### 9.2 文件结构（新增/修改）

```
core/agent/
├── compiler/                          # 新增目录
│   ├── __init__.py
│   ├── header_injector.py             # Stage 1: 头文件引入
│   ├── syntactic_decomposer.py        # Stage 2: 语法分解
│   └── macro_micro_quantizer.py       # Stage 3: 宏观微观量化
│
├── discourse_block_tree/              # 新增目录
│   ├── __init__.py
│   ├── models.py                      # EDU, DiscourseBlock, Entity, ProgressiveSummary
│   ├── manager.py                     # DiscourseBlockTreeManager
│   ├── segmenter.py                   # 轮内切分算法
│   ├── granularity_regulator.py       # 动态粒度调节
│   ├── summary_engine.py              # 渐进式摘要引擎
│   ├── context_builder.py             # LLM 上下文构建
│   └── indexer.py                     # 实体/意图/轮次索引
│
├── topic_tree/
│   ├── manager_v2.py                  # 修改: 适配 DiscourseBlock 输入
│   └── models.py                      # 修改: TopicNode.summary 从截断改为 ProgressiveSummary
│
└── interactive_test.py                # 修改: 增加编译器管道调用
```

---

## 10. 核心算法伪代码

### 10.1 轮内切分算法（segment_turn）

```python
def segment_turn(self, edus: List[EDU], scores: List[CohesionScore]) -> List[DiscourseBlock]:
    """
    将 EDU 列表按 cohesion 断崖切分为 DiscourseBlock 列表。
    基于 LCseg / TextTiling 的局部最小值检测。
    """
    if not edus:
        return []

    # 1. 计算相邻 EDU 间 cohesion（已预计算在 scores 中）
    cohesion_values = [s.total_score for s in scores]

    # 2. 检测 cohesion 断崖（局部最小值 + 低于阈值）
    boundaries = []
    for i, score in enumerate(cohesion_values):
        left = cohesion_values[i-1] if i > 0 else 1.0
        right = cohesion_values[i+1] if i < len(cohesion_values)-1 else 1.0

        # 局部最小值: 比左右邻居都低
        is_local_min = score < left and score < right
        # 低于阈值
        is_below_threshold = score < self.global_split_threshold

        if is_local_min and is_below_threshold:
            boundaries.append(i)  # 在 i 和 i+1 之间切分

    # 3. 按边界聚类
    blocks = []
    start = 0
    for b in boundaries:
        block_edus = edus[start:b+1]
        blocks.append(self._create_block(block_edus))
        start = b + 1
    blocks.append(self._create_block(edus[start:]))

    # 4. 后处理: 合并孤块（避免单句成块）
    blocks = self._merge_isolated_blocks(blocks, min_size=2)

    return blocks
```

### 10.2 动态粒度调节（regulate_granularity）

```python
def regulate_granularity(self, current_turn: int):
    """每 10 轮触发一次。"""
    if current_turn - self._last_regulation_turn < 5:
        return  # 冷却期

    # 1. 计算全局 BDI
    all_blocks = list(self.blocks.values())
    if len(all_blocks) < 3:
        return

    avg_edus = sum(len(b.atomic_units) for b in all_blocks) / len(all_blocks)
    bdi = avg_edus / self.optimal_blocks_per_topic

    # 2. 过密检测: 一家独大（内部 cohesion 极高且 EDU 多）
    for block in all_blocks:
        if (block.cohesion_internal > 0.9 and
            len(block.atomic_units) > self.max_capacity):
            sub_blocks = self._split_block_internally(block)
            self._replace_block(block, sub_blocks)
            self._last_regulation_turn = current_turn
            return  # 一次只处理一个，避免震荡

    # 3. 过疏检测: 主题过多（子块数量 > 8）
    children_by_parent = self._group_by_parent()
    for parent_id, children in children_by_parent.items():
        if len(children) > 8:
            # 合并相邻高相关块
            for i in range(len(children) - 1):
                cohesion = self._compute_boundary_cohesion(children[i], children[i+1])
                if cohesion > 0.75:
                    merged = self._merge_blocks(children[i], children[i+1])
                    self._replace_blocks([children[i], children[i+1]], [merged])
                    self._last_regulation_turn = current_turn
                    return

    # 4. BOR-based 全局阈值自适应
    self._adapt_global_threshold(all_blocks, current_turn)
```

### 10.3 渐进式摘要升级（update_summary）

```python
def update_summary(self, block: DiscourseBlock, current_turn: int):
    """根据触发条件升级摘要版本。"""
    version = block.summary_version

    # v1 → v2: 块内 EDU > 3
    if version < 2 and len(block.atomic_units) > 3:
        entities_str = ", ".join([e.text for e in block.entities[:5]])
        block.summary_v2 = f"[{block.primary_intent}] {entities_str}"
        block.summary_version = 2
        block.summary_last_updated = current_turn

    # v2 → v3: 块内轮次 > 5 或话题转折
    if version < 3 and (current_turn - block.created_at_turn > 5):
        # 规则提取关键转折/决策点
        milestones = self._extract_milestones(block)
        block.summary_v3 = f"话题演化: {' → '.join(milestones[:3])}"
        block.summary_version = 3
        block.summary_last_updated = current_turn

    # v3 → v4: 块进入 Cold 状态（后台异步）
    if version < 4 and block.status == "cold" and self.llm_provider:
        # LLM 异步压缩为命题级摘要
        prompt = f"将以下对话压缩为不超过50字的命题摘要:\n{block.summary_v3}"
        block.summary_v4 = self.llm_provider.generate(prompt, max_tokens=100)
        block.summary_version = 4
        block.summary_last_updated = current_turn
```

---

## 11. 测试策略与验证计划

### 11.1 单元测试矩阵

| 组件 | 测试用例 | 期望输出 | 验证方法 |
|---|---|---|---|
| **HeaderInjector** | "这个喝了很呛" (上下文: 汽水) | "汽水喝了很呛" | 字符串匹配 |
| **HeaderInjector** | "那个API安全" (历史: PaymentGateway) | "PaymentGateway API安全" | 字符串匹配 |
| **SyntacticDecomposer** | "帮我写Python函数" | subject=None(祈使), predicate="写", object="Python函数" | 字段断言 |
| **SyntacticDecomposer** | "我不认为那个API安全" | negation=True, object="API", object_attrs=["NEG"] | 字段断言 |
| **MacroMicroQuantizer** | 同话题两句 (EDU1: "写Python函数", EDU2: "处理CSV") | total > 0.75, decision="continue" | 分数范围 |
| **MacroMicroQuantizer** | 跨话题两句 (EDU1: "写Python函数", EDU2: "昨天神经网络方案") | total < 0.25, decision="fork" | 分数范围 |
| **MacroMicroQuantizer** | 同领域换主体 (EDU1: "Python函数", EDU2: "Java函数") | macro > 0.5, micro < 0.5, decision="attach" | 四象限断言 |
| **segment_turn** | 3个EDU, cohesion=[0.9, 0.2, 0.9] | 2个Block (第1-2个EDU, 第3个EDU) | 长度断言 |
| **regulate_granularity** | 10个子块, 平均 cohesion_boundary=0.85 | 合并为5个块 | BDI 计算 |
| **build_llm_context** | active块 + 2祖先 + 1兄弟 | 包含【当前话题】+【前文摘要】+【相关话题】 | 字符串包含 |
| **find_block_by_reference** | "刚才那个神经网络方案" | 返回对应 block_id | ID匹配 |

### 11.2 集成测试场景

```python
# 场景1: 轮内多话题切分
user_input = "帮我写Python函数。对了，昨天那个神经网络方案怎么样了？顺便推荐轻量embedding模型。"
# 期望: 3个DiscourseBlock 分别路由到: "Python函数"分支, "神经网络方案"分支, "embedding推荐"分支

# 场景2: 隐含实体补全
history = [{"role": "user", "content": "我喜欢汽水"}]
user_input = "这个喝了很呛"
# 期望: 补全为 "汽水喝了很呛", 实体=["汽水"]

# 场景3: 指代回溯
# 轮1: "帮我写Python函数" → Block_A
# 轮2: "帮我写Java函数" → Block_B (fork)
# 轮3: "回到刚才那个Python函数" → attach到 Block_A
# 期望: 当前指针 = Block_A, 上下文包含 Block_A 的完整原文

# 场景4: 渐进式摘要
# 轮1-5: 在 Block_A 讨论Python函数
# 轮6-15: 在 Block_B 讨论Java函数
# 轮16: 回到 Block_A
# 期望: Block_A 注入 LLM 时包含完整原文(最近3轮), Block_B 只注入 v3/v4 摘要

# 场景5: 动态粒度调节
# 初始: 阈值=0.5, 10轮后产生 15个Block (BDI=3.0)
# 触发 regulate_granularity → 阈值提升至 0.6 → 后续切分更保守
# 期望: BOR 从 2.5 降至 1.2 区间
```

### 11.3 性能测试基准

| 指标 | 测试方法 | 目标 | 工具 |
|---|---|---|---|
| 轮内切分延迟 | 1000 次 decompose + score | < 2ms | time.perf_counter |
| 动态粒度调节 | 1000 轮对话后触发 | < 5ms | time.perf_counter |
| 上下文构建 | 100 个 Block 的树 | < 1ms | time.perf_counter |
| 渐进摘要 v4 | LLM 调用 10 次 | 30-100ms | 实测 |
| 内存占用 | 1000 轮对话 | < 10MB | sys.getsizeof |
| 端到端延迟 | 完整 pipeline 1000 次 | < 5ms (不含 LLM) | time.perf_counter |

---

## 12. 实现里程碑与工期

### 12.1 里程碑定义

| 里程碑 | 内容 | 工期 | 交付物 | 验收标准 |
|---|---|---|---|---|
| **M1** | 编译器三阶段（Stage 1-3） | 2-3 天 | `core/agent/compiler/` 目录 | 100% 单元测试通过，延迟 < 2ms |
| **M2** | 轮内切分 + 块创建 | 2-3 天 | `segmenter.py` + `models.py` | 3个集成场景测试通过 |
| **M3** | 宏观微观量化 + 路由决策 | 2-3 天 | `macro_micro_quantizer.py` | 四象限决策矩阵 100% 覆盖 |
| **M4** | 动态粒度调节（BDI/BOR） | 2-3 天 | `granularity_regulator.py` | BOR 稳定在 0.8-1.5 区间 |
| **M5** | 渐进式摘要（v1-v4） | 2-3 天 | `summary_engine.py` | 压缩率 > 50%, 实体保留 > 80% |
| **M6** | 上下文构建 + 指代回溯 | 2-3 天 | `context_builder.py` + `indexer.py` | 指代召回 > 75% |
| **M7** | 与 TopicTreeV2 集成 | 1-2 天 | `manager_v2.py` 适配 | 现有 78 测试全部通过 |
| **M8** | 可视化升级（ReactFlow 块级） | 1-2 天 | `ReactFlowExporter` 升级 | 导出 JSON 正确渲染 |
| **M9** | 端到端测试 + 性能调优 | 2-3 天 | 完整测试报告 | 延迟 < 5ms, 内存 < 10MB |
| **M10** | 文档 + 代码审查 | 1-2 天 | 更新文档 + 代码清理 | 覆盖率 > 80% |

**总工期**: 17-27 天（串行，假设 1 人全职）。
**建议并行**: M1-M3 可串行（编译器→切分→量化），M4-M6 可并行（粒度/摘要/上下文互不依赖），M7-M10 串行。

### 12.2 最小可行路径（MVP，7天）

如果希望快速验证核心价值，先做 MVP：

| 天 | 内容 | 验证点 |
|---|---|---|
| 1-2 | Stage 1-2（HeaderInjector + SyntacticDecomposer） | 隐含实体补全率 > 80% |
| 3-4 | Stage 3（MacroQuantizer only，只做 M1-M4，不做微观）+ 轮内切分 | 切分精度人工验证 10 组对话 |
| 5-6 | 上下文构建（Hot 完整 + Warm 截断，不做 v3/v4）+ 与 TopicTreeV2 集成 | 长对话 token 减少 > 30% |
| 7 | 端到端测试 + 调参 | 3 个集成场景通过 |

MVP 不做：微观量化（μ1-μ5）、动态粒度调节（BDI/BOR）、渐进式 v3/v4、指代回溯索引。

---

## 13. 风险与回退策略

| 风险 | 影响 | 缓解策略 | 回退方案 |
|---|---|---|---|
| 轮内切分误切（一个话题切成两块） | Purity 下降，用户体验断裂 | 阈值保守（默认 0.5），引入冷却期 | 关闭轮内切分，退化为整轮树（现有行为） |
| 微观量化依赖实体提取质量 | 主谓宾提取错误 → 微观失真 | Fast Path 失败时 fallback 到整句 embedding | 只使用宏观量化（M1-M4），关闭微观 |
| 渐进摘要 v4 的 LLM 调用成本 | 后台异步可缓解，但长会话累积 | 仅对 Cold 块触发，Hot 块永不调用 | 关闭 v4，只保留 v1-v3（规则摘要） |
| 动态粒度震荡（反复分裂-合并） | 树结构不稳定，缓存失效 | 冷却期 5 轮，一次只处理一个块 | 关闭动态调节，固定阈值 0.5 |
| 与现有 V2 代码的兼容性 | 数据结构变更导致测试失败 | `DiscourseBlock` 作为 `TopicNode` 内部字段 | 关闭 Block 模式，只使用轮级模式 |
| 中文语法分解精度不足 | 主谓宾提取错误率高 | 增加 Hybrid Path 触发条件，复杂句走 LLM | 所有输入都走 LLM 轻量解析（延迟增加） |

---

## 附录 A: 文献映射与参数采纳

| 参数 | 文献来源 | 原始值 | 我们的取值 | 调整原因 |
|---|---|---|---|---|
| 窗口大小 $k$ | LCseg / BATS | 2 | **2** | 直接采纳，适用于 EDU 级比较 |
| 词汇链断裂 hiatus | LCseg | 11 句子 | **5 个 EDU** | 对话更紧凑，阈值降低 |
| 边界概率 $p_{limit}$ | LCseg | 0.1 | **0.5** | 更保守，避免过度切分 |
| 语义权重 λ | TiMem 双通道 | 0.6-0.7 | **0.6** | 直接采纳 |
| BOR 健康区间 | Granularity-Aware | 0.8-1.2 | **0.8-1.5** | 允许稍高 BOR（我们支持更细粒度） |
| Purity 目标 | Granularity-Aware | 0.85-0.96 | **> 0.85** | 对齐文献 |
| 压缩率目标 | TiMem | 52.20% | **> 50%** | 对齐 SOTA |
| 记忆层级 | MemGPT/Letta | 3-tier | **4-tier** | 增加 Frozen 层（只保留索引） |
| 切分算法 | LCseg / TextTiling | 局部最小值+深度 | **局部最小值+阈值** | 简化实现，保留核心思想 |

---

## 附录 B: 快速决策卡片

```python
# 何时启用 DiscourseBlockTree?
ENABLE_BLOCK_TREE = True  # 建议始终启用，Fast Path 无额外延迟

# 一句话: 何时分裂?
if block.cohesion_internal > 0.9 and len(block.atomic_units) > 10:
    split_block(block)

# 一句话: 何时合并?
if len(siblings) > 8 and boundary_cohesion(sibling_i, sibling_{i+1}) > 0.75:
    merge_blocks(sibling_i, sibling_{i+1})

# 一句话: 何时升级摘要?
if len(block.atomic_units) > 3 and block.summary_version < 2:
    upgrade_v2(block)      # 实体列表
if current_turn - block.created_at_turn > 5 and block.summary_version < 3:
    upgrade_v3(block)      # 演化摘要
if block.status == "cold" and block.summary_version < 4:
    upgrade_v4(block)      # LLM 异步压缩

# 一句话: 构建 LLM 上下文
context = hot_text(full, 5轮) + warm_summary(v3, 祖先链) + cold_summary(v4, 兄弟top3) + frozen(exclude)

# 回退开关（紧急时一键关闭）
ENABLE_INTRA_TURN_SPLIT = True      # 关闭 → 整轮一个 Block
ENABLE_MICRO_QUANTIZATION = True     # 关闭 → 只用宏观量化
ENABLE_DYNAMIC_GRANULARITY = True    # 关闭 → 固定阈值 0.5
ENABLE_PROGRESSIVE_SUMMARY = True   # 关闭 → 只用 v1 首句
ENABLE_V4_LLM_COMPRESSION = True    # 关闭 → 只到 v3
```
