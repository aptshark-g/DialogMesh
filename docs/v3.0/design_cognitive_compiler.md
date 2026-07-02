# 认知编译器（Cognitive Compiler）设计方案 v1.0

> 本文档定义意图识别引擎的前置认知编译层，将“意图分类”升维为“认知解析”。通过语法分解、头文件引入（隐式实体补全）、粘合度计算与双结构建模，在用户输入进入 PCR 之前完成**脏数据清洗、结构预构建、话题边界预判**，解决当前系统直接对自然语言做分类时面临的**指代缺失、修饰语丢失、话题漂移误判**三大工程痛点。
>
> 认知编译器是**跨层组件**：它上游对接原始用户输入，下游为 PCR、话题树、窗口管理提供**已解析的、实体补全的、粘合度标注的**结构化输入。

## 目录

- [1. 背景与问题](#1-背景与问题)
- [2. 设计目标](#2-设计目标)
- [3. 核心架构：编译器前端](#3-核心架构编译器前端)
- [4. 关键组件](#4-关键组件)
- [5. 数据模型](#5-数据模型)
- [6. 算法详解](#6-算法详解)
- [7. 与现有系统集成](#7-与现有系统集成)
- [8. 三级模式与现有 Gate 的对应](#8-三级模式与现有-gate-的对应)
- [9. 测试策略](#9-测试策略)
- [10. 实现计划](#10-实现计划)
- [11. 风险与回退](#11-风险与回退)
- [12. 设计文档体系](#12-设计文档体系)

---

## 1. 背景与问题

### 当前系统的隐性假设

```python
# 现有 PCR 流程的隐含假设：输入是干净的、实体完整的、话题连续的
pcr_input = PCRInput_v1(
    query=user_input,  # ← 假设：这里已经包含完整实体、无指代、无省略
    session_history=history,
)
```

**实际用户输入的真实形态**：

| 输入示例 | 表面内容 | 隐含信息 | 当前系统行为 | 期望行为 |
|---|---|---|---|---|
| "这个喝了很呛" | 无实体 | 隐含"汽水/碳酸饮料"（上下文推断） | 实体为空，PCR 误判为 TOOL 无操作数 | 头文件引入后：`"汽水喝了很呛"` |
| "我不认为这个**不安全的**API是可以调用的" | 主谓宾：API + 调用 | 否定修饰 + 安全属性丢失 | 提取 `API` + `调用` → 意图 `CALL_API`（危险） | 属性标签保留：`NOT(unsafe) API CALL` → 意图 `ADVISOR` |
| "说说牛奶的好处，然后奶牛怎么产奶" | 两个话题：牛奶/奶牛 | 主题相似但逻辑层级不同（消费 vs 生产） | 话题树误判为同一分支，实体混合 | 粘合度低（0.3）→ 话题分叉 |
| "回到刚才那个" | 代词"那个" | 指代 10 轮前的某个实体 | 线性搜索失败，PCR 输出 `UNKNOWN` | 双结构时空视图定位 + 树型结构回溯 |

### 根本原因：从“分类”到“解析”的缺口

| 能力 | 工业级 NLP 流水线 | 当前系统 | 缺失层 |
|---|---|---|---|
| 词法/句法分析 | Tokenizer → POS → Dependency Parse | ❌ 无 | 语法分解器 |
| 隐式实体补全 | Coreference Resolution + KB Lookup | ❌ 无 | 头文件引入器 |
| 篇章连贯性 | Coherence / Discourse Parser | ❌ 无（仅噪声估算） | 粘合度计算器 |
| 语义结构建模 | RST Tree / Discourse Graph | ❌ 无（线性历史） | 双结构管理器 |

**认知编译器的定位**：在 PCR 之前插入一个**轻量级解析层**，用**工程化规则**（+ 可选 LLM 辅助）补齐上述缺口，而非引入 spaCy/NLTK 等重型 NLP 库。

---

## 2. 设计目标

### 功能目标

| ID | 目标 | 优先级 | 验收标准 |
|---|---|---|---|
| CC-1 | 隐式实体补全（头文件引入） | P0 | 技术领域常见省略（地址/数值/工具名）补全率 > 80% |
| CC-2 | 语法分解不丢失修饰语 | P0 | 否定、形容词、副词作为属性标签保留，不丢失 |
| CC-3 | 粘合度量化（话题边界检测） | P0 | 两句话粘合度 0-1 分，与人工判断一致率 > 75% |
| CC-4 | 双结构一致性维护 | P1 | 树型逻辑父节点与时空时序冲突时，自动标记虚拟因果边 |
| CC-5 | 三级模式切换（规则/辅助/全 LLM） | P1 | 灰区（0.3~0.7）自动触发 LLM 辅助，极端区纯规则 |
| CC-6 | 零外部 NLP 依赖 | P1 | 不依赖 spaCy/NLTK/Jieba，纯 Python + 可选 LLM |

### 非功能目标

| ID | 目标 | 指标 |
|---|---|---|
| N-1 | 编译延迟 | 规则模式 < 2ms / 轮；LLM 辅助模式 < 30ms / 轮 |
| N-2 | 内存占用 | 语法分解缓存 < 100KB / 会话 |
| N-3 | 向后兼容 | 关闭认知编译器时，系统行为与现有代码完全一致 |
| N-4 | 可调试 | 每轮输出 `compiler_trace`（头文件命中、粘合度分解、双结构状态） |
| N-5 | 可扩展 | 新领域的头文件词典、粘合度规则可热加载（YAML/JSON） |

---

## 3. 核心架构：编译器前端

```
┌─────────────────────────────────────────────────────────────────┐
│  用户输入（原始自然语言）                                         │
│  "这个喝了很呛，我不认为那个API安全"                               │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  阶段 1：语法分解（Syntactic Decomposition）                    │
│  ─────────────────────────────────────────────────────────────  │
│  输出：List[ParsedClause]                                        │
│  • 主语："这个" → 未解析（待头文件引入）                          │
│  • 谓语："喝了" / "认为"                                        │
│  • 宾语："很呛" / "API安全"                                     │
│  • 属性：否定(NOT) / 形容词(unsafe)                              │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  阶段 2：头文件引入（Header Injection / 隐式实体补全）            │
│  ─────────────────────────────────────────────────────────────  │
│  输入：ParsedClause + 上下文实体缓存 + 领域知识库                  │
│  规则："很呛" → 关联实体：["汽水", "碳酸饮料", "辣椒"]            │
│        上下文已有"汽水" → 补全主语："汽水"                         │
│  输出：补全后的 ParsedClause（主语明确）                         │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  阶段 3：粘合度计算（Cohesion Scoring）                          │
│  ─────────────────────────────────────────────────────────────  │
│  输入：当前句 vs 前一句（或当前话题节点）                         │
│  维度：                                                           │
│    • 因果标记（所以/因此/导致）→ +0.4                             │
│    • 实体重叠（0x401000）→ +0.3 * overlap_ratio                  │
│    • 主语连续性（同一主语）→ +0.3                               │
│    • 弱关联标记（另外/顺便）→ +0.2                               │
│  输出：cohesion_score ∈ [0, 1]                                   │
│  决策：score > 0.75 → continue；score < 0.25 → fork；          │
│         0.25 ≤ score ≤ 0.75 → 灰区（进入三级模式决策）           │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  阶段 4：话题路由（Topic Routing）                                │
│  ─────────────────────────────────────────────────────────────  │
│  输入：compiled_query + cohesion_score + 当前话题树状态            │
│  决策：                                                           │
│    • cohesion_score > 0.75 → continue（当前话题延续）             │
│    • cohesion_score < 0.25 → fork（新建话题分支）                 │
│    • 0.25 ≤ score ≤ 0.75 → 灰区（TopicTree 综合历史相似度判断）  │
│  输出：target_node_id + route_action（continue/fork/attach）     │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  阶段 5：双结构写入（Dual Structure Commit）                     │
│  ─────────────────────────────────────────────────────────────  │
│  树型结构（逻辑视图）：                                           │
│    基于话题路由结果挂节点：continue/fork/attach                   │
│  时空结构（事实视图）：                                           │
│    事件 E+1 追加到 timeline_queue（严格时序）                    │
│  一致性校验：如果逻辑父节点时间 > 子节点时间，打虚拟因果边          │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  输出：CompiledInput（下游 PCR 的标准输入）                      │
│  ─────────────────────────────────────────────────────────────  │
│  • query: 补全后的自然语言（"汽水喝了很呛，我不认为那个API安全"）    │
│  • preprocessed_entities: ["汽水", "API", "unsafe"]             │
│  • cohesion_score: 0.82（第一句）/ 0.15（第二句，话题切换）       │
│  • topic_boundary: [0.82, 0.15]  ← 每子句一个粘合度              │
│  • topic_node_id: 路由后的目标话题节点                             │
│  • route_action: "continue" | "fork" | "attach"                 │
│  • compiler_trace: 头文件命中、分解详情、路由决策日志               │
│  • dual_structure_state: 树型节点指针 + 时空事件索引              │
└─────────────────────────────────────────────────────────────────┘
```

### 与 PCR 的边界

| 层级 | 职责 | 输入 | 输出 |
|---|---|---|---|
| **认知编译器** | 解析、补全、结构预判 | 原始自然语言 | `CompiledInput`（实体补全、话题边界标注） |
| **PCR** | 意图分类、噪声估算 | `CompiledInput.query` + 历史上下文 | `PCROutput`（expectation、confidence） |

**关键原则**：认知编译器**不判断意图**，它只把输入变得“更容易被正确分类”。

---

## 4. 关键组件

### 4.1 SyntacticDecomposer（语法分解器）

```python
# core/agent/compiler/syntactic_decomposer.py
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class ParsedClause:
    """
    语法分解后的子句结构。
    保留主谓宾 + 修饰属性（否定、形容词、副词），不丢失语义。
    """
    raw_text: str                    # 原始子句文本
    
    # 核心成分
    subject: Optional[str] = None   # 主语（可能为空，待头文件引入）
    subject_attrs: List[str] = field(default_factory=list)  # 主语修饰语
    predicate: Optional[str] = None  # 谓语/动词
    predicate_attrs: List[str] = field(default_factory=list) # 谓语修饰（副词）
    object: Optional[str] = None     # 宾语
    object_attrs: List[str] = field(default_factory=list)   # 宾语修饰语
    
    # 语义属性
    negation: bool = False           # 是否含否定词
    uncertainty: bool = False        # 是否含不确定（可能/也许/大概）
    imperative: bool = False          # 是否祈使句（命令语气）
    
    # 提取的实体（原始提取，未经过头文件补全）
    raw_entities: List[str] = field(default_factory=list)
    
    # 解析状态：复杂句标记（正则无法可靠解析时）
    parse_failed: bool = False
    parse_failed_reason: str = ""  # "complex_input" | "multiple_subjects" | ...
    
    def to_entity_signature(self) -> str:
        """生成包含属性的实体签名，用于下游意图解析。"""
        parts = []
        if self.negation:
            parts.append("NOT")
        if self.uncertainty:
            parts.append("MAYBE")
        parts.extend(self.subject_attrs)
        if self.subject:
            parts.append(self.subject)
        parts.append(self.predicate or "")
        parts.extend(self.object_attrs)
        if self.object:
            parts.append(self.object)
        return " ".join(filter(None, parts))
    
    def to_compact(self) -> str:
        """压缩表示，用于调试日志。"""
        attrs = f"[{'NOT ' if self.negation else ''}{','.join(self.subject_attrs)}]" if self.subject_attrs else ""
        return f"({attrs}{self.subject}) {self.predicate} ({self.object})"


class SyntacticDecomposer:
    """
    轻量级语法分解器。
    不依赖外部 NLP 库，基于规则 + 领域词典实现。
    
    设计原则：
    1. 按标点（逗号、句号、分号）切分句子为子句
    2. 在每个子句中识别主语、谓语、宾语
    3. 提取修饰语（否定、形容词、副词）作为属性标签
    4. 提取技术实体（地址、数值、工具名）
    
    关键约束：
    - FAST 路径：只处理极简指令（1-2个关键词，技术实体明确）。正则在此场景极其稳定。
    - HYBRID 路径：一旦检测到歧义（多主语、多连词、嵌套从句、长句>30字），
      不强行正则解析，直接标记 parse_failed 并转交小模型二分类。
    """
    
    # 歧义检测阈值：超过此值的句子视为"复杂句"，走 hybrid 路径
    COMPLEX_CLAUSE_LENGTH = 30      # 单个子句超过 30 字视为复杂
    MAX_CLAUSES_PER_INPUT = 5        # 输入超过 5 个子句视为复杂
    AMBIGUOUS_CONJUNCTIONS = {"和", "与", "或", "但", "如果", "虽然", "因为", "但是",
                               "and", "or", "but", "if", "although", "because"}
    
    # 否定词词典
    NEGATION_MARKERS = {"不", "没", "无", "非", "别", "不要", "不会",
                        "not", "no", "don't", "won't", "can't", "never"}
    
    # 不确定词词典
    UNCERTAINTY_MARKERS = {"可能", "也许", "大概", "应该", "或许",
                           "maybe", "perhaps", "probably", "might"}
    
    # 祈使词（命令语气）
    IMPERATIVE_MARKERS = {"请", "给我", "帮我", "扫描", "读取", "修改",
                          "scan", "read", "patch", "hook", "find", "write"}
    
    # 谓语/动词词典（技术领域常用）
    PREDICATE_MARKERS = {"scan", "patch", "hook", "read", "write", "find",
                         "分析", "扫描", "修改", "读取", "写入", "查找",
                         "看看", "检查", "确认", "执行", "调用"}
    
    # 形容词/修饰词（常见技术属性）
    ADJECTIVE_MARKERS = {"安全的", "不安全的", "稳定的", "异常的", "正常的",
                         "大端", "小端", "只读", "可写", "静态", "动态",
                         "safe", "unsafe", "stable", "abnormal", "readonly"}
    
    def decompose(self, text: str) -> List[ParsedClause]:
        """
        分解输入文本为多个 ParsedClause。
        
        步骤：
        1. 按标点切分句子
        2. 检测歧义：如果输入过于复杂，标记 parse_failed，不强行解析
        3. 对每个子句提取成分（fast 路径）或返回原始子句（hybrid 路径）
        4. 返回列表（每个子句一个 ParsedClause）
        """
        clauses = self._split_clauses(text)
        
        # 歧义检测：输入过于复杂 → 标记但不抛异常，让编译器主控决定走 hybrid
        if self._is_complex_input(clauses):
            # 复杂输入：每个子句标记 parse_failed，但保留原始文本
            return [ParsedClause(
                raw_text=text,
                parse_failed=True,
                parse_failed_reason="complex_input",
            )]
        
        parsed = []
        for clause_text in clauses:
            if clause_text.strip():
                parsed_clause = self._parse_clause(clause_text)
                parsed.append(parsed_clause)
        
        return parsed
    
    def _is_complex_input(self, clauses: List[str]) -> bool:
        """检测输入是否过于复杂（正则无法可靠解析）。"""
        # 1. 子句数量过多
        if len(clauses) > self.MAX_CLAUSES_PER_INPUT:
            return True
        
        # 2. 存在歧义连词（嵌套从句信号）
        full_text = "".join(clauses)
        conj_count = sum(1 for c in self.AMBIGUOUS_CONJUNCTIONS if c in full_text)
        if conj_count >= 2:  # 2+ 个连词视为复杂
            return True
        
        # 3. 单个子句过长（非技术指令，更像自然语言叙述）
        for c in clauses:
            if len(c) > self.COMPLEX_CLAUSE_LENGTH:
                # 如果超长但含明确技术实体，仍走 fast
                has_tech_entity = bool(re.findall(r'0x[0-9a-fA-F]+|\b\d+\b', c))
                if not has_tech_entity:
                    return True
        
        return False
    
    def _split_clauses(self, text: str) -> List[str]:
        """按中文/英文标点切分句子。"""
        # 支持：。！？；, . ! ? ;
        import re
        return [s.strip() for s in re.split(r'[。！？；，\.\!\?\;\,]+', text) if s.strip()]
    
    def _parse_clause(self, text: str) -> ParsedClause:
        """解析单个子句（fast 路径：只处理明确的技术指令）。"""
        clause = ParsedClause(raw_text=text)
        
        # 1. 检测否定和不确定
        clause.negation = any(m in text for m in self.NEGATION_MARKERS)
        clause.uncertainty = any(m in text for m in self.UNCERTAINTY_MARKERS)
        clause.imperative = any(m in text for m in self.IMPERATIVE_MARKERS)
        
        # 2. 提取技术实体（地址、数值、工具名）
        clause.raw_entities = self._extract_entities(text)
        
        # 3. 子句内部歧义检测：多主语信号（多个代词或多个名词）
        if self._has_multiple_subjects(text):
            clause.parse_failed = True
            clause.parse_failed_reason = "multiple_subjects"
            return clause  # 歧义子句，保留原始文本，不强行解析成分
        
        # 4. 提取主语（简化版：第一个名词性短语，或代词）
        clause.subject = self._extract_subject(text)
        
        # 5. 提取谓语（动词匹配）
        clause.predicate = self._extract_predicate(text)
        
        # 6. 提取宾语（谓语后的实体或名词短语）
        clause.object = self._extract_object(text, clause.predicate)
        
        # 7. 提取修饰语（形容词 + 否定）
        clause.subject_attrs = self._extract_modifiers(text, clause.subject)
        clause.object_attrs = self._extract_modifiers(text, clause.object)
        
        return clause
    
    def _has_multiple_subjects(self, text: str) -> bool:
        """检测子句是否包含多个主语（歧义信号）。"""
        # 代词计数（多个代词 = 可能指代不同对象）
        pronouns = ["这个", "那个", "它", "他", "这", "那",
                    "this", "that", "it", "the"]
        pronoun_count = sum(1 for p in pronouns if p in text)
        if pronoun_count >= 2:
            return True
        
        # 实体计数（多个不同实体 = 多主语）
        entities = self._extract_entities(text)
        if len(entities) >= 3:  # 3+ 个不同实体，可能多主语
            return True
        
        return False
    
    def _extract_entities(self, text: str) -> List[str]:
        """提取技术实体：地址、数值、工具名。"""
        entities = []
        # 地址
        entities.extend(re.findall(r'0x[0-9a-fA-F]+', text))
        # 数值
        entities.extend(re.findall(r'\b\d+\b', text))
        # 工具名（简单词典匹配）
        tool_names = ["scan", "patch", "hook", "bp", "breakpoint", "disasm",
                      "MessageBox", "VirtualProtect", "ReadProcessMemory"]
        for name in tool_names:
            if name.lower() in text.lower():
                entities.append(name)
        return entities
    
    def _extract_subject(self, text: str) -> Optional[str]:
        """提取主语（简化版：第一个代词或名词短语）。"""
        # 代词优先
        pronouns = ["这个", "那个", "它", "他", "这", "那",
                    "this", "that", "it", "the"]
        for p in pronouns:
            if p in text:
                return p
        # 否则取第一个实体
        entities = self._extract_entities(text)
        return entities[0] if entities else None
    
    def _extract_predicate(self, text: str) -> Optional[str]:
        """提取谓语（动词匹配）。"""
        for verb in self.PREDICATE_MARKERS:
            if verb in text.lower():
                return verb
        return None
    
    def _extract_object(self, text: str, predicate: Optional[str]) -> Optional[str]:
        """提取宾语（谓语后的实体或名词）。"""
        if not predicate:
            return None
        # 找到谓语位置，取后面的第一个实体
        pred_pos = text.lower().find(predicate.lower())
        if pred_pos >= 0:
            after = text[pred_pos + len(predicate):]
            entities = self._extract_entities(after)
            return entities[0] if entities else after.strip()[:20]
        return None
    
    def _extract_modifiers(self, text: str, target: Optional[str]) -> List[str]:
        """提取目标词的修饰语（前面的形容词/否定词）。"""
        if not target:
            return []
        pos = text.find(target)
        if pos < 0:
            return []
        before = text[:pos]
        modifiers = []
        for adj in self.ADJECTIVE_MARKERS:
            if adj in before:
                modifiers.append(adj)
        # 否定词也作为修饰
        if any(m in before for m in self.NEGATION_MARKERS):
            modifiers.append("NEG")
        return modifiers
```

### 4.2 HeaderInjector（头文件引入器 / 隐式实体补全）

```python
# core/agent/compiler/header_injector.py
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
import time


@dataclass
class EntityCandidate:
    """隐式实体候选。"""
    entity: str                # 实体名（如 "汽水"）
    source: str                # 来源："context" / "kb" / "inference"
    confidence: float          # 置信度 [0, 1]
    reason: str                # 推断原因（如 "上下文最近实体" / "因果关联：呛→汽水"）


class HeaderInjector:
    """
    头文件引入器（隐式实体补全）。
    
    核心机制：
    1. 上下文实体缓存：从 session_history 中最近 5 轮提取的实体池
    2. 领域知识库：技术术语的因果/关联映射（如 "呛" → ["汽水", "辣椒", "烟雾"]）
    3. 推断规则：基于谓语、属性、上下文的推断
    
    命名来源：类比 C 语言的头文件（#include），这里"引入"的是
    自然语言中省略的、但在上下文或知识库中可推断的实体。
    
    知识库管理：
    - 知识库从 YAML/JSON 文件热加载，不硬编码在代码中
    - 支持多领域知识库（通过 domain 参数切换）
    - 提供离线蒸馏脚本：利用 LLM 对历史对话日志做离线分析，
      每周自动生成新的关联项更新到 YAML 文件（小模型的"离线蒸馏"辅助 KB 扩充）
    """
    
    # 默认知识库路径
    DEFAULT_KB_PATH = "~/.memorygraph/kb/causal_kb.yaml"
    
    def __init__(self, 
                 context_window_size: int = 5,
                 kb_path: str = None,
                 domain: str = "default"):
        self.context_window_size = context_window_size
        self.domain = domain
        self.kb_path = Path(kb_path or self.DEFAULT_KB_PATH).expanduser()
        
        # 加载知识库（热加载支持）
        self._causal_kb: Dict[str, List[str]] = {}
        self._default_object_kb: Dict[str, List[str]] = {}
        self._load_kb()
        
        # 会话级缓存
        self._session_entity_cache: Dict[str, List[str]] = {}  # session_id -> 实体列表
        self._session_last_entities: Dict[str, str] = {}        # session_id -> 最近实体
    
    def _load_kb(self):
        """从 YAML/JSON 加载知识库。支持热加载（调用即重新读取）。"""
        import json
        
        if not self.kb_path.exists():
            # 首次使用：创建默认知识库文件
            self._create_default_kb()
        
        # 支持 YAML 和 JSON
        if self.kb_path.suffix in ('.yaml', '.yml'):
            try:
                import yaml
                with open(self.kb_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            except ImportError:
                # 无 PyYAML 时退化为 JSON
                json_path = self.kb_path.with_suffix('.json')
                if json_path.exists():
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                else:
                    data = self._get_default_kb_data()
        else:
            with open(self.kb_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        # 按 domain 提取
        domain_data = data.get(self.domain, data.get("default", {}))
        self._causal_kb = domain_data.get("causal_kb", {})
        self._default_object_kb = domain_data.get("default_object_kb", {})
    
    def reload_kb(self):
        """热加载知识库（运行时调用，无需重启）。"""
        self._load_kb()
    
    def _create_default_kb(self):
        """创建默认知识库文件（首次使用）。"""
        self.kb_path.parent.mkdir(parents=True, exist_ok=True)
        
        default_data = {
            "default": self._get_default_kb_data(),
            "kernel_reverse": {
                "causal_kb": {
                    "蓝屏": ["驱动", "内核", "内存", "IRQ"],
                    "死机": ["内核", "驱动", "硬件", "中断"],
                    "权限不足": ["Ring0", "驱动签名", "UAC", "管理员"],
                    "断点失效": ["硬件断点", "INT3", "反调试", "CRC校验"],
                },
                "default_object_kb": {
                    "hook": ["SSDT", "IRP", "APC", "DPC"],
                    "read": ["物理内存", "虚拟地址", "CR3", "页表"],
                    "write": ["物理内存", "虚拟地址", "CR3", "页表"],
                }
            },
            "game_reverse": {
                "causal_kb": {
                    "透视": ["渲染管线", "D3D", "OpenGL", "Shader"],
                    "无敌": ["HP", "伤害计算", "碰撞检测", "服务端校验"],
                    "加速": ["移动速度", "帧率", "Tick", "网络同步"],
                },
                "default_object_kb": {
                    "scan": ["内存区域", "模块基址", "代码段", "数据段"],
                    "patch": ["指令", "数值", "校验和", "CRC"],
                }
            }
        }
        
        import json
        with open(self.kb_path.with_suffix('.json'), 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)
    
    def _get_default_kb_data(self) -> Dict:
        """默认知识库数据（代码内 fallback，实际从文件加载）。"""
        return {
            "causal_kb": {
                "很呛": ["汽水", "碳酸饮料", "辣椒", "烟雾"],
                "很甜": ["汽水", "糖果", "蜂蜜"],
                "很苦": ["咖啡", "茶", "药"],
                "崩溃": ["程序", "游戏", "进程"],
                "卡顿": ["游戏", "程序", "动画"],
                "闪退": ["APP", "游戏", "进程"],
                "很烫": ["CPU", "显卡", "电源"],
                "很慢": ["硬盘", "网络", "查询"],
                "不安全": ["API", "函数", "调用", "链接"],
                "只读": ["内存页", "寄存器", "文件"],
            },
            "default_object_kb": {
                "scan": ["内存", "地址空间", "进程"],
                "patch": ["数值", "地址", "代码"],
                "hook": ["函数", "API", "消息"],
                "read": ["内存", "寄存器", "文件"],
                "write": ["内存", "寄存器", "文件"],
            }
        }
    
    def inject(self, 
               clauses: List[ParsedClause], 
               session_id: str,
               session_history: List[HistoryEntry] = None) -> List[ParsedClause]:
        """
        对 ParsedClause 列表进行头文件引入（实体补全）。
        
        流程：
        1. 从 session_history 更新上下文实体缓存
        2. 对每个 clause，如果主语为空（代词/省略），尝试补全
        3. 如果宾语为空，尝试基于谓语补全默认宾语
        4. 返回补全后的 clauses
        """
        # 更新上下文缓存
        if session_history:
            self._update_context_cache(session_id, session_history)
        
        # 实体缓存（用于当前轮补全）
        context_entities = self._session_entity_cache.get(session_id, [])
        last_entity = self._session_last_entities.get(session_id)
        
        injected = []
        for clause in clauses:
            new_clause = self._inject_clause(clause, context_entities, last_entity)
            injected.append(new_clause)
            # 更新 last_entity（如果当前 clause 有实体）
            if new_clause.raw_entities:
                self._session_last_entities[session_id] = new_clause.raw_entities[-1]
        
        return injected
    
    def _inject_clause(self, 
                       clause: ParsedClause, 
                       context_entities: List[str],
                       last_entity: Optional[str]) -> ParsedClause:
        """对单个子句进行实体补全。"""
        # 如果主语是代词/空，尝试补全
        if not clause.subject or clause.subject in ["这个", "那个", "它", "这", "那", "the", "this", "that"]:
            # 策略 1：上下文最近实体（最优先）
            if last_entity:
                clause.subject = last_entity
                clause.subject_attrs.append("[上下文引入]")
            # 策略 2：从因果 KB 推断（基于宾语属性）
            elif clause.object_attrs:
                inferred = self._infer_from_attributes(clause.object_attrs)
                if inferred:
                    clause.subject = inferred[0].entity
                    clause.subject_attrs.append(f"[KB推断:{inferred[0].reason}]")
            # 策略 3：从上下文实体池匹配
            elif context_entities:
                clause.subject = context_entities[-1]
                clause.subject_attrs.append("[上下文引入]")
        
        # 如果宾语为空，尝试基于谓语补全
        if not clause.object and clause.predicate:
            default_objs = self._default_object_kb.get(clause.predicate.lower())
            if default_objs:
                clause.object = default_objs[0]
                clause.object_attrs.append("[默认宾语]")
        
        # 如果属性词（如"很呛"）在因果 KB 中，补全隐含实体
        for attr in list(clause.subject_attrs) + list(clause.object_attrs):
            if attr in self._causal_kb and not clause.subject:
                candidates = self._causal_kb[attr]
                # 优先选择上下文已出现的
                for c in candidates:
                    if c in context_entities:
                        clause.subject = c
                        clause.subject_attrs.append(f"[因果推断:{attr}→{c}]")
                        break
                else:
                    clause.subject = candidates[0]
                    clause.subject_attrs.append(f"[因果推断:{attr}→{candidates[0]}]")
        
        return clause
    
    def _update_context_cache(self, session_id: str, history: List[HistoryEntry]):
        """从最近 N 轮历史提取实体，更新缓存。"""
        recent = history[-self.context_window_size:]
        entities = []
        for entry in recent:
            # 复用 SyntacticDecomposer 的实体提取
            entities.extend(self._extract_entities_from_text(entry.content))
        self._session_entity_cache[session_id] = entities
    
    def _extract_entities_from_text(self, text: str) -> List[str]:
        """从文本提取技术实体（简化版，与 SyntacticDecomposer 一致）。"""
        import re
        entities = []
        entities.extend(re.findall(r'0x[0-9a-fA-F]+', text))
        entities.extend(re.findall(r'\b\d+\b', text))
        return entities
    
    def _infer_from_attributes(self, attrs: List[str]) -> List[EntityCandidate]:
        """从属性词推断实体。"""
        candidates = []
        for attr in attrs:
            if attr in self._causal_kb:
                for entity in self._causal_kb[attr]:
                    candidates.append(EntityCandidate(
                        entity=entity,
                        source="kb",
                        confidence=0.7,
                        reason=f"属性'{attr}'的因果关联"
                    ))
        return candidates
```

### 4.3 CohesionScorer（粘合度计算器）

```python
# core/agent/compiler/cohesion_scorer.py
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class CohesionScore:
    """粘合度分数与分解。"""
    total_score: float              # 总粘合度 [0, 1]
    
    # 分解维度（用于调试和灰区决策）
    causal_score: float = 0.0       # 因果标记维度
    entity_overlap_score: float = 0.0  # 实体重叠维度
    subject_continuity_score: float = 0.0  # 主语连续性维度
    weak_link_score: float = 0.0    # 弱关联标记维度
    
    # 灰区决策建议
    decision: str = ""               # "continue" | "fork" | "gray_zone"
    
    def is_extreme(self) -> bool:
        """是否为极端值（无需 LLM）。"""
        return self.total_score > 0.75 or self.total_score < 0.25


class CohesionScorer:
    """
    粘合度计算器。
    
    衡量两句话（或当前输入与话题节点）之间的篇章连贯性。
    粘合度由四个维度加权组成，最终映射到 0-1 区间。
    
    粘合度阈值：
    - > 0.75：强粘合（继续当前话题）
    - 0.25 ~ 0.75：灰区（需进一步判断，进入三级模式）
    - < 0.25：弱粘合（话题分叉或切换）
    """
    
    # 因果标记（强关联）
    STRONG_CAUSAL_MARKERS = {
        "所以", "因此", "导致", "因为", "使得", "从而", "于是", "结果",
        "so", "because", "therefore", "thus", "as a result", "since",
    }
    
    # 弱关联标记（过渡/并列）
    WEAK_LINK_MARKERS = {
        "另外", "此外", "顺便", "然后", "接着", "还有", "以及",
        "also", "by the way", "next", "then", "and", "besides",
    }
    
    # 话题切换标记（强制低粘合度）
    TOPIC_SWITCH_MARKERS = {
        "换个话题", "不说这个", "另外说", "回到", "关于",
        "speaking of", "by the way", "moving on", "regarding",
    }
    
    # 维度权重（可调，支持 YAML 热加载）
    WEIGHTS = {
        "causal": 0.40,
        "entity_overlap": 0.30,
        "subject_continuity": 0.20,
        "weak_link": 0.10,
    }
    
    def score(self, 
              prev_clauses: List[ParsedClause], 
              curr_clauses: List[ParsedClause],
              mode: str = "auto") -> CohesionScore:
        """
        计算前一个话轮（prev）与当前话轮（curr）之间的粘合度。
        
        Args:
            prev_clauses: 前一轮的 ParsedClause 列表
            curr_clauses: 当前轮的 ParsedClause 列表
            mode: "auto" | "fast" | "hybrid" | "full"
        
        Returns:
            CohesionScore
        """
        if not prev_clauses or not curr_clauses:
            return CohesionScore(total_score=0.0, decision="fork")
        
        # 取最后一个 prev 子句与第一个 curr 子句比较（边界检测）
        prev = prev_clauses[-1]
        curr = curr_clauses[0]
        
        # 1. 因果标记维度
        causal = self._causal_score(prev, curr)
        
        # 2. 实体重叠维度
        entity_overlap = self._entity_overlap_score(prev, curr)
        
        # 3. 主语连续性维度
        subject_cont = self._subject_continuity_score(prev, curr)
        
        # 4. 弱关联维度
        weak_link = self._weak_link_score(prev, curr)
        
        # 5. 话题切换标记（强制降级）
        if self._has_topic_switch_markers(curr):
            causal = 0.0
            weak_link = 0.0
        
        # 加权求和
        total = (
            causal * self.WEIGHTS["causal"] +
            entity_overlap * self.WEIGHTS["entity_overlap"] +
            subject_cont * self.WEIGHTS["subject_continuity"] +
            weak_link * self.WEIGHTS["weak_link"]
        )
        total = max(0.0, min(1.0, total))
        
        # 决策建议
        if total > 0.75:
            decision = "continue"
        elif total < 0.25:
            decision = "fork"
        else:
            decision = "gray_zone"
        
        return CohesionScore(
            total_score=total,
            causal_score=causal,
            entity_overlap_score=entity_overlap,
            subject_continuity_score=subject_cont,
            weak_link_score=weak_link,
            decision=decision,
        )
    
    def _causal_score(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """因果标记维度：当前句是否含因果词，且主语/实体与前句相关。"""
        has_causal = any(m in curr.raw_text for m in self.STRONG_CAUSAL_MARKERS)
        if not has_causal:
            return 0.0
        
        # 如果有因果词，但主语/实体与前句完全不重叠，可能是伪因果
        entity_overlap = self._entity_overlap_score(prev, curr)
        if entity_overlap == 0 and not self._subject_continuity_score(prev, curr):
            return 0.2  # 低置信因果（如"所以天气很好"——与主句无关）
        
        return 1.0
    
    def _entity_overlap_score(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """实体重叠维度：Jaccard 相似度。"""
        prev_entities = set(prev.raw_entities)
        curr_entities = set(curr.raw_entities)
        if not prev_entities and not curr_entities:
            return 0.5  # 都无实体，中性
        if not prev_entities or not curr_entities:
            return 0.0
        intersection = len(prev_entities & curr_entities)
        union = len(prev_entities | curr_entities)
        return intersection / union if union > 0 else 0.0
    
    def _subject_continuity_score(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """主语连续性：主语相同或存在包含关系。"""
        if not prev.subject or not curr.subject:
            return 0.0
        if prev.subject == curr.subject:
            return 1.0
        if prev.subject in curr.subject or curr.subject in prev.subject:
            return 0.8
        # 代词继承（前句主语，后句代词）
        if curr.subject in ["它", "这", "那", "this", "that", "it"]:
            return 0.9
        return 0.0
    
    def _weak_link_score(self, prev: ParsedClause, curr: ParsedClause) -> float:
        """弱关联：含弱关联标记，但实体不重叠。"""
        has_weak = any(m in curr.raw_text for m in self.WEAK_LINK_MARKERS)
        if not has_weak:
            return 0.0
        entity_overlap = self._entity_overlap_score(prev, curr)
        if entity_overlap > 0.3:
            return 0.3  # 弱关联但实体相关
        return 0.1  # 弱关联且实体无关（可能话题切换）
    
    def _has_topic_switch_markers(self, curr: ParsedClause) -> bool:
        """检测话题切换标记。"""
        return any(m in curr.raw_text for m in self.TOPIC_SWITCH_MARKERS)
```

### 4.4 DualStructureManager（双结构管理器）

```python
# core/agent/compiler/dual_structure.py
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import time


class VirtualEdgeType(Enum):
    TEMPORAL_INVERSION = "temporal_inversion"  # 时序冲突：逻辑父时间 > 子时间
    CAUSAL_INFERENCE = "causal_inference"        # 推断因果（非显式）
    COREFERENCE = "coreference"                  # 共指关联


@dataclass
class TimelineEvent:
    """时空结构（事实视图）中的事件。"""
    event_id: str
    turn_index: int
    timestamp: float
    clause_signatures: List[str]   # 子句的实体签名列表
    node_id: Optional[str] = None  # 关联的树型节点（逻辑归属）
    flags: Set[str] = field(default_factory=set)  # 标记：TEMPORAL_INVERSION 等


@dataclass
class VirtualEdge:
    """虚拟边：树型结构与时空结构冲突时的补丁边。"""
    edge_id: str
    from_node: str
    to_node: str
    edge_type: VirtualEdgeType
    reason: str
    actual_timestamp: float
    turn_index: int


class DualStructureManager:
    """
    双结构管理器。
    
    维护两套结构：
    1. 树型结构（逻辑视图）：由 TopicTreeManager 维护，表达话题的层级/因果/从属关系
    2. 时空结构（事实视图）：严格的时间序列，不可篡改
    
    核心职责：
    - 新事件写入时，同时更新树型节点和时空队列
    - 校验一致性：如果逻辑父节点的时间 > 子节点时间，生成虚拟边
    - 提供查询：按时间查（事实）、按话题查（逻辑）、按实体跨话题查（图）
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        
        # 时空结构：严格时序队列
        self.timeline: List[TimelineEvent] = []
        
        # 虚拟边：树型与时空冲突时的补丁
        self.virtual_edges: List[VirtualEdge] = []
        
        # 索引
        self._turn_to_event: Dict[int, str] = {}  # turn_index -> event_id
        self._entity_to_events: Dict[str, List[str]] = {}  # entity -> [event_id, ...]
        
        # O(1) 缓存：node_id -> 最新 event_id（避免 _find_parent_event 线性遍历）
        self._node_to_latest_event: Dict[str, str] = {}
        self._event_cache: Dict[str, TimelineEvent] = {}  # event_id -> event
    
    def commit(self, 
               turn_index: int,
               clauses: List[ParsedClause],
               topic_node_id: Optional[str] = None,
               logical_parent_id: Optional[str] = None) -> TimelineEvent:
        """
        提交一个新事件到双结构。
        
        Args:
            turn_index: 当前轮次
            clauses: 语法分解后的子句列表
            topic_node_id: 关联的话题树节点（逻辑归属）
            logical_parent_id: 逻辑父节点（用于一致性校验）
        
        Returns:
            TimelineEvent
        """
        event_id = f"evt_{self.session_id}_{turn_index}"
        timestamp = time.time()
        
        # 1. 创建时空事件
        event = TimelineEvent(
            event_id=event_id,
            turn_index=turn_index,
            timestamp=timestamp,
            clause_signatures=[c.to_entity_signature() for c in clauses],
            node_id=topic_node_id,
        )
        
        # 2. 一致性校验（如果提供了逻辑父节点）
        if logical_parent_id:
            parent_event = self._find_parent_event(logical_parent_id)
            if parent_event and parent_event.timestamp > timestamp:
                # 冲突：逻辑父节点在时间上发生在子节点之后
                event.flags.add("TEMPORAL_INVERSION")
                self._create_virtual_edge(
                    from_node=logical_parent_id,
                    to_node=topic_node_id or event_id,
                    edge_type=VirtualEdgeType.TEMPORAL_INVERSION,
                    reason=f"逻辑父节点时间({parent_event.timestamp}) > 当前时间({timestamp})",
                    actual_timestamp=timestamp,
                    turn_index=turn_index,
                )
        
        # 3. 写入时空队列 + 更新 O(1) 缓存
        self.timeline.append(event)
        self._turn_to_event[turn_index] = event_id
        self._event_cache[event_id] = event
        if topic_node_id:
            self._node_to_latest_event[topic_node_id] = event_id
        
        # 4. 更新实体索引
        for clause in clauses:
            for entity in clause.raw_entities:
                self._entity_to_events.setdefault(entity, []).append(event_id)
        
        return event
    
    def get_events_by_time_range(self, start_turn: int, end_turn: int) -> List[TimelineEvent]:
        """按时间范围查询事件（事实视图）。"""
        return [e for e in self.timeline if start_turn <= e.turn_index <= end_turn]
    
    def get_events_by_entity(self, entity: str) -> List[TimelineEvent]:
        """按实体查询跨话题事件（图查询）。"""
        event_ids = self._entity_to_events.get(entity, [])
        return [self._event_cache[eid] for eid in event_ids if eid in self._event_cache]
    
    def get_logical_path(self, event_id: str) -> List[TimelineEvent]:
        """获取事件的逻辑路径（沿树型结构向上）。"""
        # 需要 TopicTreeManager 提供祖先查询，此处预留接口
        event = self._find_event(event_id)
        if not event or not event.node_id:
            return [event] if event else []
        # 委托给 TopicTreeManager 获取祖先节点链
        # 然后映射回 TimelineEvent
        return [event]  # 简化版，实际实现需集成 TopicTreeManager
    
    def _find_event(self, event_id: str) -> Optional[TimelineEvent]:
        """按 ID 查找事件（O(1) 缓存查找）。"""
        return self._event_cache.get(event_id)
    
    def _find_parent_event(self, logical_parent_id: str) -> Optional[TimelineEvent]:
        """查找逻辑父节点对应的最新事件（O(1) 缓存查找）。"""
        # 使用 node_to_latest_event 缓存，避免线性遍历 timeline
        latest_event_id = self._node_to_latest_event.get(logical_parent_id)
        if latest_event_id:
            return self._event_cache.get(latest_event_id)
        return None
    
    def _create_virtual_edge(self, **kwargs):
        """创建虚拟边。"""
        edge = VirtualEdge(
            edge_id=f"vedge_{len(self.virtual_edges)}",
            **kwargs
        )
        self.virtual_edges.append(edge)
```

### 4.5 CognitiveCompiler（认知编译器主控）

```python
# core/agent/compiler/compiler.py
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field


@dataclass
class CompiledInput:
    """
    认知编译器的输出，即 PCR 的增强输入。
    """
    # 原始输入（头文件补全后）
    query: str
    
    # 语法分解结果
    clauses: List[ParsedClause]
    
    # 粘合度信息
    cohesion_score: CohesionScore
    topic_boundary: List[float]  # 每个子句与前一句的粘合度
    
    # 实体信息（已补全）
    preprocessed_entities: List[str]
    entity_sources: Dict[str, str]  # entity -> "original" / "injected" / "inferred"
    
    # 双结构状态
    timeline_event_id: Optional[str] = None
    topic_node_id: Optional[str] = None
    
    # 编译器追踪（用于调试和可观测性）
    compiler_trace: Dict[str, Any] = field(default_factory=dict)
    
    # 向后兼容：当未启用编译器时，可直接传入 PCR
    def to_pcr_input(self, 
                     session_history: List[HistoryEntry] = None,
                     **pcr_kwargs) -> PCRInput_v1:
        """转换为标准 PCRInput_v1。"""
        # 将编译器信息注入 metadata 字段（不破坏现有 PCR 接口）
        metadata = pcr_kwargs.pop("metadata", {})
        metadata.update({
            "cognitive_compiler": {
                "cohesion_score": self.cohesion_score.total_score,
                "cohesion_decision": self.cohesion_score.decision,
                "preprocessed_entities": self.preprocessed_entities,
                "entity_sources": self.entity_sources,
                "clause_count": len(self.clauses),
            }
        })
        
        return PCRInput_v1(
            query=self.query,  # 使用补全后的 query
            session_history=session_history or [],
            metadata=metadata,
            **pcr_kwargs,
        )


class CognitiveCompiler:
    """
    认知编译器主控。
    
    编排：语法分解 → 头文件引入 → 粘合度计算 → 双结构写入 → 输出 CompiledInput。
    """
    
    def __init__(self,
                 session_id: str,
                 decomposer: SyntacticDecomposer = None,
                 injector: HeaderInjector = None,
                 scorer: CohesionScorer = None,
                 llm_provider: Optional[LLMProvider] = None,
                 mode: str = "auto"):
        self.session_id = session_id
        self.decomposer = decomposer or SyntacticDecomposer()
        self.injector = injector or HeaderInjector()
        self.scorer = scorer or CohesionScorer()
        self.llm = llm_provider
        self.mode = mode  # "auto" | "fast" | "hybrid" | "full"
    
    def compile(self, 
                user_input: str,
                turn_index: int,
                session_history: List[HistoryEntry] = None) -> CompiledInput:
        """
        编译用户输入。
        
        返回 CompiledInput，可直接转换为 PCRInput_v1。
        """
        trace = {"steps": []}
        
        # Step 1: 语法分解
        clauses = self.decomposer.decompose(user_input)
        trace["steps"].append({"step": "decompose", "clauses": [c.to_compact() for c in clauses]})
        
        # Step 2: 头文件引入（隐式实体补全）
        injected_clauses = self.injector.inject(
            clauses, self.session_id, session_history
        )
        trace["steps"].append({"step": "inject", 
                               "before": [c.subject for c in clauses],
                               "after": [c.subject for c in injected_clauses]})
        
        # 生成补全后的 query（把代词替换为实体）
        compiled_query = self._rebuild_query(injected_clauses)
        
        # 提取所有实体（原始 + 引入）
        all_entities = []
        entity_sources = {}
        for c in injected_clauses:
            for e in c.raw_entities:
                if e not in entity_sources:
                    all_entities.append(e)
                    entity_sources[e] = "original"
            # 引入的实体（主语/宾语被替换后）
            if c.subject and c.subject not in entity_sources and "[上下文引入]" in c.subject_attrs:
                all_entities.append(c.subject)
                entity_sources[c.subject] = "injected"
        
        # Step 3: 粘合度计算（与上一轮比较）
        cohesion = CohesionScore(total_score=0.5, decision="gray_zone")  # 默认中性
        topic_boundary = []
        if session_history and turn_index > 0:
            # 提取前一轮的 clauses（从历史的 metadata 中恢复，或重新分解）
            prev_entry = session_history[-1]
            prev_clauses = self.decomposer.decompose(prev_entry.content)
            cohesion = self.scorer.score(prev_clauses, injected_clauses, mode=self.mode)
            topic_boundary = [cohesion.total_score]
            
            # 灰区处理：三级模式
            if cohesion.decision == "gray_zone" and self.mode in ("auto", "hybrid", "full"):
                cohesion = self._resolve_gray_zone(prev_clauses, injected_clauses, cohesion)
        
        trace["steps"].append({"step": "cohesion", "score": cohesion.total_score, 
                               "decision": cohesion.decision})
        
        # 注意：话题路由和双结构写入**不在编译器内部执行**
        # 正确数据流：compile() → 输出 cohesion_score → 调用方执行 topic_tree.route() → dual_manager.commit()
        # 原因：TopicTree 的路由决策依赖于编译器输出的 cohesion_score，编译器不应自己调用下游组件
        
        return CompiledInput(
            query=compiled_query,
            clauses=injected_clauses,
            cohesion_score=cohesion,
            topic_boundary=topic_boundary,
            preprocessed_entities=all_entities,
            entity_sources=entity_sources,
            timeline_event_id=None,   # ← 由调用方 dual_manager.commit() 后填入
            topic_node_id=None,      # ← 由调用方 topic_tree.route() 后填入
            compiler_trace=trace,
        )
    
    def _rebuild_query(self, clauses: List[ParsedClause]) -> str:
        """从 ParsedClause 重建补全后的 query。"""
        # 简化版：直接拼接子句的文本（主语已补全）
        return "。".join(c.raw_text for c in clauses) + "。"
    
    def _resolve_gray_zone(self, 
                          prev_clauses: List[ParsedClause], 
                          curr_clauses: List[ParsedClause],
                          base_score: CohesionScore) -> CohesionScore:
        """
        灰区决策：三级模式。
        
        - fast: 直接返回 base_score（保守 continue）
        - hybrid: 调用 1.5B LLM 做二分类（因果/关联？Yes/No）
        - full: 调用 LLM 做完整分析（不推荐，仅用于调试）
        """
        if self.mode == "fast" or not self.llm:
            # 保守策略：偏向 continue（避免过度分叉）
            base_score.total_score = 0.76  # 略高于 fork 阈值
            base_score.decision = "continue"
            return base_score
        
        if self.mode == "hybrid":
            # 极简二分类 prompt
            prev_text = prev_clauses[-1].raw_text[:30] if prev_clauses else ""
            curr_text = curr_clauses[0].raw_text[:30] if curr_clauses else ""
            prompt = f"A: {prev_text}\nB: {curr_text}\nRelated? Y/N"
            
            try:
                result = self.llm.generate(prompt, max_tokens=1, temperature=0.0)
                is_related = "Y" in result.upper() or "Yes" in result
                if is_related:
                    base_score.total_score = 0.76
                    base_score.decision = "continue"
                else:
                    base_score.total_score = 0.24
                    base_score.decision = "fork"
            except Exception:
                # LLM 失败，回退到保守策略
                base_score.total_score = 0.76
                base_score.decision = "continue"
            
            return base_score
        
        # full mode：完整 LLM 分析（占位，实际实现更复杂）
        return base_score
```

---

## 5. 数据模型

### 5.1 核心数据结构关系

```
CompiledInput
├── query: str                    # 补全后的自然语言（送入 PCR）
├── clauses: List[ParsedClause]
│   ├── raw_text: str
│   ├── subject: str (+ attrs, negation, uncertainty)
│   ├── predicate: str
│   ├── object: str (+ attrs)
│   └── raw_entities: List[str]
├── cohesion_score: CohesionScore
│   ├── total_score: float [0,1]
│   ├── causal_score: float
│   ├── entity_overlap_score: float
│   ├── subject_continuity_score: float
│   └── decision: str
├── preprocessed_entities: List[str]      # 头文件补全后的完整实体
├── entity_sources: Dict[str, str]         # 实体来源追踪
├── timeline_event_id: str                 # 时空结构事件 ID
├── topic_node_id: str                     # 树型结构节点 ID
└── compiler_trace: Dict                   # 调试追踪
```

### 5.2 与现有数据模型的兼容

| 现有模型 | 新增字段 | 兼容方式 |
|---|---|---|
| `PCRInput_v1` | `metadata["cognitive_compiler"]` | 不破坏 frozen 接口，通过 metadata 透传 |
| `HistoryEntry` | `metadata["parsed_clauses"]` | 语法分解结果可持久化，用于下一轮粘合度计算 |
| `TopicNode` | `timeline_event_ids` | 树型节点关联时空事件（支持双结构查询） |
| `DecisionLogEntry` | `cohesion_score`, `compiler_steps` | 可观测性追踪编译器行为 |

---

## 6. 算法详解

### 6.1 粘合度计算公式

```
cohesion_score = Σ (dimension_score_i × weight_i)

dimensions:
  1. causal_score        ∈ [0, 1]  weight = 0.40
  2. entity_overlap_score ∈ [0, 1]  weight = 0.30
  3. subject_continuity_score ∈ [0, 1]  weight = 0.20
  4. weak_link_score     ∈ [0, 1]  weight = 0.10

decision:
  score > 0.75  → continue (继续当前话题)
  score < 0.25  → fork (话题分叉)
  0.25 ≤ score ≤ 0.75 → gray_zone (进入三级模式)
```

### 6.2 头文件引入优先级

```
当主语为空（代词/省略）时：
  1. 上下文最近实体（最近 1 轮，最高优先级）
  2. 因果 KB 推断（基于属性词如"很呛"）
  3. 上下文实体池（最近 5 轮）
  4. 谓语默认宾语（当宾语也为空时）

当宾语为空时：
  1. 谓语默认宾语映射（scan → 内存/地址空间）
  2. 上下文最近实体（继承）
```

### 6.3 双结构冲突校验规则

```
commit(turn_index, clauses, topic_node_id, logical_parent_id):
  event = TimelineEvent(...)
  
  if logical_parent_id:
    parent_event = find_latest_event(node_id = logical_parent_id)
    if parent_event.timestamp > event.timestamp:
      # 时序冲突：逻辑父发生在子之后
      event.flags.add("TEMPORAL_INVERSION")
      create_virtual_edge(
        from = logical_parent_id,
        to = topic_node_id,
        type = TEMPORAL_INVERSION,
        reason = "逻辑父时间 > 子时间"
      )
  
  append(timeline, event)
```

---

## 7. 与现有系统集成

### 7.1 集成位置：PCR 之前

```python
# intent_trace_cli.py / IntentTraceRunner

def run_intent_trace_with_compiler(
    query: str,
    session_id: str,
    turn_index: int,
    compiler: CognitiveCompiler,       # ← 新增：认知编译器
    topic_tree: TopicTreeManager,      # ← 新增：话题树（利用编译器输出做路由）
    window_manager: ContextWindowManager,  # ← 新增：窗口管理（话题过滤后压缩）
    persistence: CLISessionPersistence = None,
    provider: LLMProvider = None,
) -> Dict[str, Any]:
    
    # 1. 加载历史（用于头文件引入和粘合度计算）
    history = persistence.get_history(session_id) if persistence else []
    
    # 2. 认知编译（计算补全实体 + 粘合度 + 双结构状态）
    compiled = compiler.compile(
        user_input=query,
        turn_index=turn_index,
        session_history=history,
    )
    
    # 3. 话题路由（利用编译器输出的 cohesion_score 做决策）
    #    粘合度 > 0.75 → continue；< 0.25 → fork；灰区 → 综合历史相似度
    route_result = topic_tree.route(
        query=compiled.query,
        turn_index=turn_index,
        cohesion_score=compiled.cohesion_score,  # ← 关键：编译器输出驱动话题路由
    )
    
    # 4. 话题过滤后的窗口压缩（只加载当前话题 + 祖先的历史）
    topic_filtered_history = topic_tree.get_pcr_input_context(
        route_result.target_node_id,
        history
    )
    pcr_input = window_manager.build_pcr_input(
        query=compiled.query,
        history=topic_filtered_history,  # ← 只包含当前话题相关的历史
        session_profile=compiled.cohesion_score,  # 可选项：粘合度辅助压缩排序
    )
    
    # 5. 输出编译器追踪（verbose 模式）
    if verbose:
        print(f"[编译器] 粘合度: {compiled.cohesion_score.total_score:.2f} "
              f"({compiled.cohesion_score.decision})")
        print(f"[编译器] 话题路由: {route_result.action} → {route_result.target_node_id}")
        print(f"[编译器] 补全实体: {compiled.preprocessed_entities}")
    
    # 6. 转换为标准 PCR 输入（向后兼容）
    pcr_input = compiled.to_pcr_input(
        session_history=topic_filtered_history,  # ← 使用话题过滤后的历史
        session_id=session_id,
        turn_index=turn_index,
    )
    
    # 7. 执行 PCR（复用现有逻辑）
    pcr = RuleBasedPCR()
    pcr_output = pcr.evaluate(pcr_input)
    
    # 8. 后续流程（门控、意图解析、执行...）不变
    ...
    
    return result
```

### 7.2 与话题树的集成（数据流核心修正）

**正确顺序**：`Compiler.compile()` → `TopicTree.route(cohesion_score)` → `WindowManager.build_pcr_input()` → `PCR.evaluate()`

```python
# 在 CognitiveCompiler.compile() 中
# 话题路由现在由编译器主控调用，而非在 compile() 内部隐式执行

class CognitiveCompiler:
    def compile(self, user_input, turn_index, session_history):
        # Step 1-3: 语法分解、头文件引入、粘合度计算（同上）
        ...
        
        # 输出：CompiledInput（包含 cohesion_score，但**不包含话题路由结果**）
        # 话题路由由调用方（run_intent_trace_with_compiler）显式执行
        return CompiledInput(
            query=compiled_query,
            clauses=injected_clauses,
            cohesion_score=cohesion,  # ← 供 TopicTree.route() 使用
            ...
        )

# 在 TopicTreeManager.route() 中（修正后的接口）
class TopicTreeManager:
    def route(self, 
              query: str, 
              turn_index: int,
              cohesion_score: CohesionScore = None,  # ← 新增：编译器提供的粘合度
              pcr_preview: Any = None) -> TopicRouteResult:
        """
        话题路由：利用粘合度分数做快速决策，避免重复计算相似度。
        
        粘合度极端值（>0.75 或 <0.25）直接决定路由，无需再算历史相似度。
        只有灰区（0.25~0.75）才需要搜索历史话题匹配。
        """
        # 1. 粘合度极端值：直接决策（fast 路径）
        if cohesion_score and cohesion_score.is_extreme():
            if cohesion_score.total_score > 0.75:
                return TopicRouteResult(action="continue", ...)
            else:
                return TopicRouteResult(action="fork", ...)
        
        # 2. 灰区：综合历史相似度搜索（原有逻辑）
        # ... 搜索历史话题 ...
        
        # 3. 粘合度与相似度冲突时：优先粘合度（编译器更了解当前输入的上下文）
        if cohesion_score and cohesion_score.total_score < 0.25 and best_match_score > 0.7:
            # 场景：粘合度极低（当前输入与上轮无关），但话题树认为相似度高
            # 可能原因：话题树基于老旧历史误判（用户很久前提过类似词）
            # 决策：优先粘合度（短期上下文更可靠），强制 fork
            return TopicRouteResult(action="fork", ...)
```

话题树路由的增强：
- **粘合度 > 0.75**：直接 `continue`（跳过历史相似度计算，节省 O(N) 搜索）
- **粘合度 < 0.25**：直接 `fork`（跳过历史相似度计算）
- **粘合度灰区 + 话题树也灰区**：触发 LLM 辅助决策（原有逻辑）
- **粘合度与话题树冲突**：优先粘合度（编译器基于当前输入 vs 前一轮的实时比较，比话题树的历史相似度更可靠）

### 7.3 与窗口管理的集成

```python
# ContextWindowManager 的压缩策略增强

class ContextWindowManager:
    def build_pcr_input(self, ...):
        # ... 现有逻辑 ...
        
        # 新增：粘合度辅助排序（温窗口中优先保留粘合度高的轮次）
        if history and hasattr(history[0], 'metadata') and history[0].metadata:
            # 按粘合度排序温窗口（高粘合度优先保留）
            warm_sorted = sorted(warm, 
                key=lambda h: h.metadata.get('cohesion_score', 0.5), 
                reverse=True)
            warm = warm_sorted[:self.config.warm_size]
```

### 7.4 与可观测性的集成

```python
# DecisionLogEntry 新增字段
@dataclass
class DecisionLogEntry:
    # ... 现有字段 ...
    
    # 认知编译器追踪
    cohesion_score: Optional[float] = None
    cohesion_decision: Optional[str] = None
    compiler_steps: Optional[List[Dict]] = None
    preprocessed_entities: Optional[List[str]] = None
    entity_injected_count: int = 0
```

---

## 8. 三级模式与现有 Gate 的对应

```
┌─────────────────────────────────────────────────────────────────┐
│  用户输入                                                        │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  认知编译器三级模式                                               │
├─────────────────────────────────────────────────────────────────┤
│  Level 1: 无 LLM 快速（Fast）                                    │
│  ─────────────────────────────────────────────────────────────  │
│  触发：粘合度 > 0.75 或 < 0.25，且实体在字典中直接匹配            │
│  耗时：O(1) 查表，< 2ms                                          │
│  对应：Gate 0（PCR 规则） + 编译器规则层                         │
│  行为：直接输出 continue/fork，不调用 LLM                        │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  Level 2: LLM 辅助决策（Hybrid）                                 │
│  ─────────────────────────────────────────────────────────────  │
│  触发：粘合度 0.25 ~ 0.75（灰区），或上下文出现不确定指代          │
│  耗时：极简 Prompt（<20词）→ 1.5B 模型 → < 30ms                   │
│  对应：Gate 2（策略补全器）的变体，但用于编译器而非 PCR          │
│  行为：二分类（"两句话是否关联？Y/N"），结果修正粘合度            │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  Level 3: 全 LLM 模式（Full）                                    │
│  ─────────────────────────────────────────────────────────────  │
│  触发：粘合度极低且无法归入任何话题，含大量隐喻/抽象概念          │
│  耗时：完整分析 Prompt → 完整 LLM 生成 → 100ms+                  │
│  对应：Gate 3（LLM 完整解析）                                    │
│  行为：LLM 生成话题结构建议，编译器采纳或修正                     │
│                         ↓                                        │
├─────────────────────────────────────────────────────────────────┤
│  PCR 输入（CompiledInput → PCRInput_v1）                         │
│  下游：现有 Gate 0/1/2/3 体系不变                               │
└─────────────────────────────────────────────────────────────────┘
```

**关键设计**：认知编译器的三级模式是**PCR 之前的前置过滤**，不改变现有 Gate 体系。PCR 接收的是已经**话题边界清晰、实体补全**的干净输入。

---

## 9. 测试策略

### 9.1 单元测试

```python
class TestSyntacticDecomposer(unittest.TestCase):
    
    def test_negation_detection(self):
        """否定词检测。"""
        d = SyntacticDecomposer()
        clauses = d.decompose("我不认为这个API安全")
        self.assertTrue(clauses[0].negation)
        self.assertEqual(clauses[0].subject, "这个")
        self.assertEqual(clauses[0].predicate, "认为")
    
    def test_imperative_detection(self):
        """祈使句检测。"""
        d = SyntacticDecomposer()
        clauses = d.decompose("扫描 0x401000")
        self.assertTrue(clauses[0].imperative)
        self.assertEqual(clauses[0].predicate, "scan")
    
    def test_entity_extraction(self):
        """实体提取。"""
        d = SyntacticDecomposer()
        clauses = d.decompose("patch 0x2000 to 90")
        self.assertIn("0x2000", clauses[0].raw_entities)
        self.assertIn("90", clauses[0].raw_entities)


class TestHeaderInjector(unittest.TestCase):
    
    def test_context_entity_injection(self):
        """上下文实体补全。"""
        injector = HeaderInjector()
        history = [
            HistoryEntry(role="user", content="scan 0x401000"),
        ]
        
        clauses = [ParsedClause(raw_text="读取这个地址", subject="这个")]
        injected = injector.inject(clauses, "session_1", history)
        
        self.assertEqual(injected[0].subject, "0x401000")
        self.assertIn("[上下文引入]", injected[0].subject_attrs)
    
    def test_causal_kb_injection(self):
        """因果 KB 推断。"""
        injector = HeaderInjector()
        clauses = [ParsedClause(raw_text="喝了很呛", subject=None, object_attrs=["很呛"])]
        injected = injector.inject(clauses, "session_2")
        
        # 基于"很呛"推断主语可能是"汽水"
        self.assertEqual(injected[0].subject, "汽水")
        self.assertIn("[因果推断", injected[0].subject_attrs[0])


class TestCohesionScorer(unittest.TestCase):
    
    def test_strong_causal(self):
        """强因果：高粘合度。"""
        s = CohesionScorer()
        prev = [ParsedClause(raw_text="scan 0x401000", raw_entities=["0x401000"])]
        curr = [ParsedClause(raw_text="所以数值是 90", raw_entities=["90"], 
                             subject="数值")]
        score = s.score(prev, curr)
        
        self.assertGreater(score.total_score, 0.75)
        self.assertEqual(score.decision, "continue")
    
    def test_topic_switch(self):
        """话题切换：低粘合度。"""
        s = CohesionScorer()
        prev = [ParsedClause(raw_text="scan 0x401000")]
        curr = [ParsedClause(raw_text="另外说说牛奶怎么产奶")]
        score = s.score(prev, curr)
        
        self.assertLess(score.total_score, 0.25)
        self.assertEqual(score.decision, "fork")
    
    def test_gray_zone(self):
        """灰区：弱关联，实体不重叠。"""
        s = CohesionScorer()
        prev = [ParsedClause(raw_text="scan 0x401000")]
        curr = [ParsedClause(raw_text="然后看看别的")]
        score = s.score(prev, curr)
        
        self.assertGreaterEqual(score.total_score, 0.25)
        self.assertLessEqual(score.total_score, 0.75)
        self.assertEqual(score.decision, "gray_zone")


class TestDualStructureManager(unittest.TestCase):
    
    def test_temporal_inversion_detection(self):
        """时序冲突检测。"""
        dsm = DualStructureManager("test")
        
        # 第一轮：父节点
        event1 = dsm.commit(0, [ParsedClause(raw_text="scan 0x401000")], "node_A")
        
        # 第二轮：子节点，但逻辑父时间 > 子时间（模拟异常）
        # 实际中通过 topic_tree 提供 logical_parent_id
        # 此处简化：手动触发校验
        event2 = dsm.commit(1, [ParsedClause(raw_text="patch 90")], "node_B", "node_A")
        
        # 校验：由于时间单调递增，实际不会冲突
        # 测试用例需 mock 时间或手动构造
        self.assertEqual(len(dsm.timeline), 2)
    
    def test_entity_cross_query(self):
        """跨话题实体查询。"""
        dsm = DualStructureManager("test")
        dsm.commit(0, [ParsedClause(raw_text="scan 0x401000", raw_entities=["0x401000"])], "node_A")
        dsm.commit(1, [ParsedClause(raw_text="hook 0x401000", raw_entities=["0x401000"])], "node_B")
        
        events = dsm.get_events_by_entity("0x401000")
        self.assertEqual(len(events), 2)


class TestCognitiveCompiler(unittest.TestCase):
    
    def test_full_compile_pipeline(self):
        """完整编译流程。"""
        compiler = CognitiveCompiler("session_1", mode="fast")
        
        result = compiler.compile(
            user_input="这个喝了很呛，扫描 0x401000",
            turn_index=0,
        )
        
        self.assertIsNotNone(result.query)
        self.assertEqual(len(result.clauses), 2)
        self.assertIn("汽水", result.preprocessed_entities)  # 头文件引入
        self.assertIn("0x401000", result.preprocessed_entities)
        self.assertIsNotNone(result.compiler_trace)
    
    def test_backward_compatibility(self):
        """向后兼容：未启用编译器时，PCRInput 行为一致。"""
        compiler = CognitiveCompiler("session_1", mode="fast")
        result = compiler.compile("scan 100", turn_index=0)
        
        pcr_input = result.to_pcr_input()
        self.assertEqual(pcr_input.query, "scan 100")
        self.assertIn("cognitive_compiler", pcr_input.metadata)
```

### 9.2 集成测试

```python
class TestCompilerWithTopicTree(unittest.TestCase):
    """认知编译器 + 话题树集成。"""
    
    def test_topic_fork_by_cohesion(self):
        """粘合度低 → 话题分叉。"""
        tree = TopicTreeManager("session_1")
        compiler = CognitiveCompiler("session_1", topic_tree=tree, mode="fast")
        
        # 第一轮：扫描
        r1 = compiler.compile("scan 0x401000", turn_index=0)
        tree.create_node(None, "TOOL", 0, "scan 0x401000", ["0x401000"])
        
        # 第二轮：话题切换（牛奶 → 低粘合度）
        history = [HistoryEntry(role="user", content="scan 0x401000")]
        r2 = compiler.compile("说说牛奶怎么产奶", turn_index=1, session_history=history)
        
        # 粘合度应该 < 0.25，触发 fork
        self.assertLess(r2.cohesion_score.total_score, 0.25)
        self.assertEqual(r2.cohesion_score.decision, "fork")
    
    def test_topic_continue_by_cohesion(self):
        """粘合成度高 → 继续话题。"""
        tree = TopicTreeManager("session_1")
        compiler = CognitiveCompiler("session_1", topic_tree=tree, mode="fast")
        
        history = [HistoryEntry(role="user", content="scan 0x401000")]
        r2 = compiler.compile("所以数值是 90", turn_index=1, session_history=history)
        
        self.assertGreater(r2.cohesion_score.total_score, 0.75)
        self.assertEqual(r2.cohesion_score.decision, "continue")
```

---

## 10. 实现计划

### Phase 1: 语法分解 + 头文件引入（1 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 1.1 | `compiler/syntactic_decomposer.py` | 创建 `SyntacticDecomposer` + `ParsedClause` |
| 1.2 | `compiler/header_injector.py` | 创建 `HeaderInjector` + 领域 KB（技术术语） |
| 1.3 | `tests/test_compiler_decompose.py` | 语法分解测试（否定、祈使、实体提取） |
| 1.4 | `tests/test_compiler_inject.py` | 头文件引入测试（上下文补全、因果 KB） |
| 1.5 | `tests/test_compiler_integration.py` | 集成测试（分解 → 引入端到端） |

### Phase 2: 粘合度 + 双结构（1 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 2.1 | `compiler/cohesion_scorer.py` | 创建 `CohesionScorer` + 四维度加权 |
| 2.2 | `compiler/dual_structure.py` | 创建 `DualStructureManager` + 虚拟边 |
| 2.3 | `compiler/compiler.py` | 创建 `CognitiveCompiler` 主控（编排所有组件） |
| 2.4 | `tests/test_compiler_cohesion.py` | 粘合度测试（高/低/灰区） |
| 2.5 | `tests/test_compiler_dual.py` | 双结构测试（时序冲突、跨实体查询） |
| 2.6 | `tests/test_compiler_full.py` | 完整编译流程测试 |

### Phase 3: 三级模式 + 集成（1 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 3.1 | `compiler/compiler.py` | 实现 `_resolve_gray_zone()`（LLM 辅助决策） |
| 3.2 | `intent_trace_cli.py` | 注入 `CognitiveCompiler`，添加 `--compiler-mode` 参数 |
| 3.3 | `pcr/datacontract.py` | `PCRInput_v1` 的 `metadata` 支持 `cognitive_compiler` 字段 |
| 3.4 | `tests/test_compiler_cli.py` | CLI 集成测试 |
| 3.5 | `tests/test_compiler_backward_compat.py` | 向后兼容测试（关闭编译器时行为一致） |

### Phase 4: 持久化与优化（0.5 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 4.1 | `service/stores/async_sqlite.py` | 增加 `timeline_events` 表（时空结构持久化） |
| 4.2 | `service/stores/async_sqlite.py` | 增加 `virtual_edges` 表 |
| 4.3 | `observability/logger.py` | `DecisionLogEntry` 增加编译器字段 |
| 4.4 | `tests/test_compiler_persistence.py` | 持久化恢复测试 |

---

## 11. 风险与回退

### 风险 1: 头文件引入错误（误判实体）

**场景**：用户说"这个喝了很呛"，但用户实际喝的是"辣椒水"，系统引入"汽水"。

**回退**：
- 引入的实体标记为 `"[injected]"`，PCR 和后续模块可识别为"非用户显式提及"
- 保留原始文本在 `compiler_trace` 中，用户可溯源
- 如果用户后续明确纠正（"不是汽水，是辣椒"），更新 KB 并标记该会话的引入规则失效

### 风险 2: 语法分解过度简化（丢失复杂句结构）

**场景**：长句含嵌套从句、被动语态、倒装句，规则分解失败。

**回退**：
- 分解失败时（无法提取主谓宾），标记 `parse_failed=True`，退化为原始文本直接送入 PCR
- 可观测性记录分解失败率，超过 20% 时告警（建议引入外部 NLP 库或训练专用模型）

### 风险 3: 粘合度阈值不准（频繁误分叉/误合并）

**场景**：用户正常延续话题，但粘合度因缺少关键词被误判为 fork。

**回退**：
- 默认模式设为 `hybrid`（灰区调 LLM），而非纯 `fast`
- 提供 `--cohesion-threshold` 参数让用户/开发者调优
- 记录分叉准确率到仪表盘，人工调优阈值

### 风险 4: 双结构时序冲突（逻辑与事实矛盾）

**场景**：话题回溯（attach）导致逻辑父节点时间 > 子节点时间。

**回退**：
- 冲突时生成虚拟边，不打断流程（逻辑视图允许"时间旅行"，用虚拟边标记）
- 仪表盘显示 `TEMPORAL_INVERSION` 计数，超过阈值时提示用户检查话题树结构

### 风险 5: 性能劣化（LLM 辅助引入延迟）

**场景**：每轮灰区都调 LLM，30ms × 100 轮 = 3s 累积延迟。

**回退**：
- 灰区缓存：同一会话内相似句子的粘合度结果缓存（LRU，maxsize=100）
- 异步 LLM：如果架构允许，LLM 辅助可异步执行，不阻塞当前轮（保守先 continue，LLM 返回后修正下一轮的树结构）
- 降级开关：`--compiler-mode=fast` 完全关闭 LLM 调用

---

## 12. 设计文档体系

| 文档 | 说明 | 依赖 |
|---|---|---|
| `design_persistence.md` | 会话持久化（SQLite） | 无 |
| `design_context_window.md` | 上下文窗口管理（热/温/冷） | 读取持久化历史 |
| `design_observability.md` | 可观测性（日志/指标/告警） | 观察所有模块 |
| `design_topic_tree.md` | 话题树（对话图/回溯/分叉） | 依赖持久化 + 窗口管理 |
| `design_cognitive_compiler.md` | **认知编译器（本文档）** | **上游：所有模块的输入预处理** |

### 认知编译器的位置

```
用户输入
    ↓
[CognitiveCompiler]  ← 本文档
    ↓
[TopicTreeManager]   ← design_topic_tree.md
    ↓
[ContextWindowManager] ← design_context_window.md
    ↓
[PCR + Gate 体系]      ← 现有核心
    ↓
[CLISessionPersistence] ← design_persistence.md
    ↓
[Observability]        ← design_observability.md
```

**认知编译器是“最上游”的跨层组件**，它让所有下游模块接收到的输入更干净、结构更明确。不启用它时，系统退化为现有行为（向后兼容）。

---

## 附录：文件清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `compiler/syntactic_decomposer.py` | 🆕 新建 | 语法分解器 |
| `compiler/header_injector.py` | 🆕 新建 | 头文件引入器 |
| `compiler/cohesion_scorer.py` | 🆕 新建 | 粘合度计算器 |
| `compiler/dual_structure.py` | 🆕 新建 | 双结构管理器 |
| `compiler/compiler.py` | 🆕 新建 | 认知编译器主控 |
| `compiler/__init__.py` | 🆕 新建 | 包入口 |
| `tests/test_compiler_decompose.py` | 🆕 新建 | 语法分解测试 |
| `tests/test_compiler_inject.py` | 🆕 新建 | 头文件引入测试 |
| `tests/test_compiler_cohesion.py` | 🆕 新建 | 粘合度测试 |
| `tests/test_compiler_dual.py` | 🆕 新建 | 双结构测试 |
| `tests/test_compiler_full.py` | 🆕 新建 | 完整编译流程测试 |
| `tests/test_compiler_integration.py` | 🆕 新建 | 集成测试 |
| `tests/test_compiler_cli.py` | 🆕 新建 | CLI 集成测试 |
| `tests/test_compiler_backward_compat.py` | 🆕 新建 | 向后兼容测试 |
| `pcr/datacontract.py` | 📝 修改 | `PCRInput_v1.metadata` 支持编译器字段 |
| `intent_trace_cli.py` | 📝 修改 | 注入 `CognitiveCompiler` |
| `service/stores/async_sqlite.py` | 📝 修改 | `timeline_events` + `virtual_edges` 表 |
| `observability/logger.py` | 📝 修改 | `DecisionLogEntry` 增加编译器追踪字段 |
