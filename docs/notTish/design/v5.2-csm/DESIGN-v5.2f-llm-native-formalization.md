# Literature Cortex v5.2f 设计方案：LLM+领域原生形式化协同架构

> **文档编号:** LC-DESIGN-v5.2f
> **版本:** v5.2f-DRAFT
> **状态:** 📋 DRAFT
> **完成度:** 40%（架构重构设计）
> **日期:** 2026-06-17
> **依赖:** v5.2e 端到端问题修复方案
> **注册表:** 参见 `DESIGN-REGISTRY.md`
> **核心变更:** 放弃统一函数树，改用标准通用图(SGF)；LLM主导+领域原生形式化锚定；新增草稿持久化层

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-17 | v5.2f-DRAFT | 架构重构：放弃统一函数树，改用SGF；LLM+插件化协同；新增草稿持久化 |

---

## 1. 架构重构的核心决策

### 1.1 放弃统一函数树的原因

**v5.2c 的问题：** 五元组函数树（Input/Output/Sub-functions/Call-Graph/Constraints）是**程序设计的思维方式**，不是物理/化学/生物/社会的通用结构。

| 领域 | 能否被函数树覆盖 | 问题 |
|------|-------------------|------|
| 程序代码 | ✅ 完美 | AST 本身就是函数树 |
| 控制系统 | ✅ 可以 | 反馈环可用 Call-Graph 表达 |
| 键合图 | ⚠️ 勉强 | 功率守恒、势/流对偶关系丢失 |
| 化学反应网络 | ❌ 困难 | 反应方程式不是函数调用，是物质转化 |
| 基因调控网络 | ❌ 困难 | 促进/抑制关系不是输入输出 |
| 社会网络 | ❌ 困难 | 关系边没有"调用"语义 |

**核心洞察：** 键合图本身就是跨域统一语言（功率流 `P = e × f`），没有必要再转一层函数树。多一层抽象就多一次信息损耗。

### 1.2 新架构的核心原则

1. **减少抽象次数：** 有原生形式化语言就用原生，没有才让 LLM 做转换
2. **LLM 换泛化能力：** 提高 LLM 比重，用其语义理解能力处理非结构化文本
3. **领域原生语言换准确性：** 用键合图/控制框图/AST 等成熟标准保证精确性
4. **自指优先：** 先从持久化层查找已有结果，避免重复计算
5. **草稿持久化：** 中间结果先存为草稿，后续人工/规则筛选后再正式持久化

---

## 2. 新四层架构（契约优先 + 插件化）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 1: 语义嵌入与领域粗分层 (Semantic Embedding & Domain Classification)  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  输入: 原始文本（节点描述、论文摘要、需求文本）                              │
│  输出: 标准化文本特征包 (TextFeaturePacket)                                  │
│  工具: Sentence-BERT / SciBERT + TextRank + 关键词规则                       │
│  职责: 只做纯文本语义处理——向量化、领域粗分类、关键词提取                     │
│  绝对不做: 生成图结构、做转译、判定同构                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓ TextFeaturePacket (JSON)
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 2: 领域化结构化转译层 (Domain-Specific Transliteration) — 核心改造    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  输入: TextFeaturePacket                                                     │
│  输出: 标准通用图 (Standard Graph Format, SGF)                               │
│  内部结构: 路由层 + 领域转译插件                                              │
│  职责: 非结构化文本 → 标准化图结构                                           │
│  绝对不做: 同构计算、相似度判定、规则校验                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓ SGF (JSON)
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 3: 统一图计算引擎 (Unified Graph Computation Engine)                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  输入: 标准通用图 SGF（只认这个格式，不区分领域）                             │
│  输出: 标准化图计算结果包 (GraphComputationResult)                           │
│  工具: WL 着色 + 拓扑相似度 + 分层同构打分 + 两级缓存 + 增量更新             │
│  职责: 所有图计算能力收敛于此                                               │
│  绝对不做: 语义解释、领域识别、规则判定                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓ GraphComputationResult (JSON)
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 4: 规则判定与结果输出层 (Rule-Based Judgment & Output)                │
│  ─────────────────────────────────────────────────────────────────────────  │
│  输入: GraphComputationResult + 场景配置                                     │
│  输出: 标准化判定结论 (IsomorphismVerdict)                                   │
│  职责: 场景化阈值判定、分层同构结论、自然语言解释（LLM辅助）                  │
│  绝对不做: 图计算、转译逻辑                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 层间契约：标准化数据格式

### 3.1 Layer 1 → Layer 2: TextFeaturePacket

```json
{
  "schema_version": "1.0",
  "packet_type": "TextFeaturePacket",
  "raw_text": "原始文本原文",
  "source_node_id": "thermal-vibration-coupling",
  "semantic_vector": [0.1, 0.2, 0.3, 0.4, 0.5],
  "vector_model": "all-MiniLM-L6-v2",
  "domain_prediction": {
    "bond_graph": 0.85,
    "control_system": 0.10,
    "chemical_reaction": 0.03,
    "unknown": 0.02
  },
  "keywords": [
    {"term": "thermal", "weight": 0.92, "category": "domain"},
    {"term": "vibration", "weight": 0.88, "category": "domain"},
    {"term": "coupling", "weight": 0.75, "category": "relation"}
  ],
  "text_rank_top_terms": ["thermal", "vibration", "coupling", "modal", "temperature"],
  "confidence": 0.85,
  "processing_timestamp": "2026-06-17T03:00:00Z"
}
```

### 3.2 Layer 2 → Layer 3: Standard Graph Format (SGF)

**核心设计：** 所有领域原生形式化语言的统一图表示，不丢失领域语义。

```json
{
  "schema_version": "1.0",
  "graph_type": "StandardGraphFormat",
  "graph_id": "bg_thermal_vibration_001",
  "domain": "bond_graph",
  "domain_version": "1.0",
  "title": "Thermal-Vibration Coupling",
  
  "nodes": [
    {
      "id": "n1",
      "base_type": "Se",
      "labels": ["source", "thermal", "effort_source"],
      "domain_specific": {
        "bond_graph_type": "effort_source",
        "variable": "temperature",
        "unit": "K",
        "value": "T_env"
      },
      "properties": {
        "description": "环境温度",
        "can_compute": false
      }
    },
    {
      "id": "n2",
      "base_type": "R",
      "labels": ["dissipation", "thermal", "energy_dissipator"],
      "domain_specific": {
        "bond_graph_type": "resistor",
        "effort_variable": "temperature_difference",
        "flow_variable": "heat_flow_rate",
        "constitutive_relation": "e = R * f"
      },
      "properties": {
        "description": "热接触热阻",
        "parameter": "1/(hA)"
      }
    },
    {
      "id": "n3",
      "base_type": "C",
      "labels": ["storage", "thermal", "energy_storage"],
      "domain_specific": {
        "bond_graph_type": "capacitor",
        "effort_variable": "temperature",
        "flow_variable": "heat_flow_rate",
        "constitutive_relation": "f = C * de/dt"
      },
      "properties": {
        "description": "结构热容",
        "parameter": "mc_p"
      }
    },
    {
      "id": "n4",
      "base_type": "GY",
      "labels": ["transducer", "cross_domain", "thermal_to_mechanical"],
      "domain_specific": {
        "bond_graph_type": "gyrator",
        "from_domain": "thermal",
        "to_domain": "mechanical",
        "constitutive_relation": "e1*f1 = e2*f2"
      },
      "properties": {
        "description": "温度-刚度耦合回转器",
        "parameter": "∂E/∂T"
      }
    }
  ],
  
  "edges": [
    {
      "id": "e1",
      "source": "n1",
      "target": "n2",
      "type": "power_flow",
      "labels": ["thermal_path"],
      "domain_specific": {
        "bond_graph_causality": "effort_out_flow_in",
        "power_direction": "forward"
      },
      "properties": {
        "description": "热流从环境通过热阻"
      }
    },
    {
      "id": "e2",
      "source": "n1",
      "target": "n3",
      "type": "power_flow",
      "labels": ["thermal_storage"],
      "domain_specific": {
        "bond_graph_causality": "effort_out_flow_in",
        "power_direction": "forward"
      },
      "properties": {
        "description": "热流进入结构热容"
      }
    },
    {
      "id": "e3",
      "source": "n3",
      "target": "n4",
      "type": "cross_domain_coupling",
      "labels": ["thermal_to_mechanical"],
      "domain_specific": {
        "bond_graph_causality": "gyrator_coupling",
        "coupling_type": "energy_port",
        "power_conservation": true
      },
      "properties": {
        "description": "温度变化影响材料刚度"
      }
    }
  ],
  
  "global_constraints": [
    {
      "type": "power_conservation",
      "expr": "Σ(e_i × f_i) = 0",
      "domain": "bond_graph",
      "applies_to_junctions": ["0", "1"]
    },
    {
      "type": "constitutive_equation",
      "expr": "K(T) = K_0 × (1 - α(T - T_0))",
      "description": "温度软化"
    }
  ],
  
  "metadata": {
    "translated_by": "bond_graph_plugin_v1",
    "translation_confidence": 0.95,
    "source_text_hash": "sha256:abc123...",
    "created_at": "2026-06-17T03:00:00Z",
    "is_draft": true
  }
}
```

**关键设计点：**
- `base_type`: WL 拓扑计算只用这个字段，保证算法通用性
- `labels`: 用于分层同构判定（拓扑/功能/物理）
- `domain_specific`: 保留领域原生语义，不丢失信息
- `is_draft`: 标记是否为草稿，待后续筛选

### 3.3 Layer 3 → Layer 4: GraphComputationResult

```json
{
  "schema_version": "1.0",
  "result_type": "GraphComputationResult",
  "graph_pair": ["bg_thermal_vibration_001", "ctrl_anc_single_001"],
  
  "wl_coloring": {
    "depth": 3,
    "node_colors": {
      "bg_thermal_vibration_001": {"n1": "c_001", "n2": "c_002"},
      "ctrl_anc_single_001": {"n1": "c_003", "n2": "c_001"}
    }
  },
  
  "similarity_scores": {
    "topological": 0.72,
    "functional": 0.45,
    "physical": 0.12
  },
  
  "topo_features": {
    "node_count_a": 8,
    "node_count_b": 7,
    "edge_count_a": 7,
    "edge_count_b": 6,
    "has_feedback_a": false,
    "has_feedback_b": true,
    "cycle_count_a": 0,
    "cycle_count_b": 1
  },
  
  "cache_info": {
    "cache_hit": false,
    "cache_key": "sha256:def456..."
  },
  
  "computation_time_ms": 45
}
```

### 3.4 Layer 4 输出: IsomorphismVerdict

```json
{
  "schema_version": "1.0",
  "verdict_type": "IsomorphismVerdict",
  "system_a": "bg_thermal_vibration_001",
  "system_b": "ctrl_anc_single_001",
  "use_case": "architecture_search",
  
  "level": "WEAKLY_ISOMORPHIC",
  "scores": {
    "topology": 0.72,
    "function": 0.45,
    "physical": 0.12
  },
  
  "reasoning": {
    "topology": "两系统均为能量流网络，具有相似的串联-并联混合结构",
    "function": "热系统为开环物理耦合，控制系统为闭环反馈调节，功能不同",
    "physical": "物理域完全不同（热能 vs 声能），量纲不匹配，不可复用"
  },
  
  "recommendations": [
    "可借鉴热-振耦合的端口建模方法用于ANC的次级路径建模",
    "不建议直接复用物理模型参数"
  ],
  
  "explanation_generated_by": "llm_gpt4_v1",
  "confidence": 0.85,
  "timestamp": "2026-06-17T03:00:00Z"
}
```

---

## 4. Layer 2 核心改造：路由层 + 插件化

### 4.1 自指优先：草稿持久化层

**核心机制：** 在开始任何转译工作前，先在持久化层查找是否已有匹配结果。

```python
class Layer2Router:
    def __init__(self, draft_store: DraftStore, plugin_registry: PluginRegistry):
        self.draft_store = draft_store
        self.plugins = plugin_registry
    
    def translate(self, text_packet: TextFeaturePacket) -> StandardGraphFormat:
        # Step 1: 自指——检查草稿持久化层
        cached = self.draft_store.find_by_text_hash(text_packet.text_hash)
        if cached and cached.confidence > 0.8:
            return cached.sgf  # 直接复用
        
        # Step 2: 路由——选择转译插件
        domain = self._select_domain(text_packet.domain_prediction)
        plugin = self.plugins.get(domain)
        
        # Step 3: 转译
        sgf = plugin.translate(text_packet)
        
        # Step 4: 存入草稿持久化层
        self.draft_store.save_draft(
            text_hash=text_packet.text_hash,
            sgf=sgf,
            confidence=sgf.metadata.translation_confidence,
            status="pending_review"
        )
        
        return sgf
```

### 4.2 草稿持久化层设计

```sql
-- 草稿表
CREATE TABLE IF NOT EXISTS sgf_drafts (
    id TEXT PRIMARY KEY,
    text_hash TEXT NOT NULL,
    source_node_id TEXT,
    sgf_json TEXT NOT NULL,  -- 完整的 SGF JSON
    domain TEXT,
    translation_confidence REAL,
    plugin_version TEXT,
    status TEXT CHECK(status IN ('pending_review', 'approved', 'rejected', 'deprecated')),
    reviewed_by TEXT,  -- human / llm / rule
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(text_hash, plugin_version)
);

-- 草稿审批记录
CREATE TABLE IF NOT EXISTS draft_reviews (
    id TEXT PRIMARY KEY,
    draft_id TEXT REFERENCES sgf_drafts(id),
    reviewer TEXT,  -- human_username / llm_model / rule_engine
    verdict TEXT CHECK(verdict IN ('approve', 'reject', 'modify')),
    modifications TEXT,  -- JSON diff
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**价值：**
- 避免重复计算：相同文本多次查询，直接复用
- 积累资产：每次 LLM 转译的结果都沉淀为可复用草稿
- 人机协同：高质量草稿经人工审核后升级为正式数据
- A/B 测试：多个版本的转译结果可并行比较

### 4.3 插件接口定义

```python
from abc import ABC, abstractmethod
from typing import Any

class DomainTransliterationPlugin(ABC):
    """领域转译插件基类。"""
    
    @property
    @abstractmethod
    def domain_name(self) -> str:
        """插件处理的领域名称，如 'bond_graph', 'control_system'"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """插件版本号"""
        pass
    
    @abstractmethod
    def can_handle(self, text_packet: TextFeaturePacket) -> float:
        """判断能否处理该文本，返回置信度 0-1。"""
        pass
    
    @abstractmethod
    def translate(self, text_packet: TextFeaturePacket) -> StandardGraphFormat:
        """将文本转译为 SGF。"""
        pass
    
    @abstractmethod
    def validate(self, sgf: StandardGraphFormat) -> list[str]:
        """验证 SGF 的合法性，返回错误列表（空列表表示通过）。"""
        pass


# 键合图插件示例
class BondGraphPlugin(DomainTransliterationPlugin):
    @property
    def domain_name(self) -> str:
        return "bond_graph"
    
    @property
    def version(self) -> str:
        return "1.0"
    
    def can_handle(self, text_packet: TextFeaturePacket) -> float:
        # 检查关键词
        keywords = ["bond graph", "键合图", "势变量", "流变量", "0-节点", "1-节点"]
        score = sum(1 for kw in keywords if kw in text_packet.raw_text.lower())
        return min(1.0, score / 3)  # 命中3个关键词即置信度1.0
    
    def translate(self, text_packet: TextFeaturePacket) -> StandardGraphFormat:
        # 如果有模板库匹配，走快速路径
        template_match = self._match_template(text_packet)
        if template_match.confidence > 0.8:
            return self._apply_template(template_match, text_packet)
        
        # 否则走 LLM 路径
        return self._llm_translate(text_packet)
    
    def validate(self, sgf: StandardGraphFormat) -> list[str]:
        errors = []
        # 检查功率守恒
        for junction in sgf.get_junctions():
            if not self._check_power_conservation(junction):
                errors.append(f"功率守恒违反: {junction.id}")
        return errors
```

---

## 5. 现有插件清单

| 领域 | 插件名 | 状态 | 模板库 | LLM 兜底 |
|------|--------|------|--------|---------|
| 键合图 | BondGraphPlugin | 已原型 | 热-振耦合模板 | ✅ |
| 控制系统 | ControlSystemPlugin | 已原型 | 单通道ANC模板 | ✅ |
| 程序代码 | CodeASTPlugin | 待实现 | 通用AST模板 | ✅ |
| 化学反应 | ChemicalReactionPlugin | 待实现 | CRN模板 | ✅ |
| 基因调控 | GeneRegulationPlugin | 待实现 | SBML/GO模板 | ✅ |
| 通用 | GenericLLMPlugin | 待实现 | 无 | 纯LLM |

---

## 6. 与 v5.2d 全领域粗匹配器的关系

**v5.2d 的能力被整合进 Layer 2：**

- 领域识别 → 成为 Layer 2 路由层的输入
- 模板匹配 → 成为各插件内部的快速路径
- 30+ 形式化语言 → 成为插件注册表

**v5.2d 不再作为独立模块存在**，其设计思想被继承，但代码被拆分重组。

---

## 7. 一句话总结

**v5.2f 架构重构的核心是"降抽象、提泛化、保准确"：放弃试图统一所有领域的"函数树"（它本质上是程序思维），改用"标准通用图"容纳各领域原生形式化语言；用 LLM 做语义理解和兜底转换，用键合图/控制框图/AST 等成熟标准保证精确性；新增草稿持久化层，让每次 LLM 输出都成为可积累、可筛选、可复用的资产。不是推翻重来，是把之前四层的接口焊死，把黑盒拆成插件，让系统从"能跑"变成"能长"。**

---

*设计方案版本: v5.2f-DRAFT*
*撰写日期: 2026-06-17*
*作者: 合作 (OpenClaw)*
*基于: v5.2e 问题修复方案 + 用户架构重构要求*
