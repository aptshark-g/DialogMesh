# Literature Cortex — 完整架构设计文档 (v6.0-UNIFIED)

> **文档编号:** LC-DESIGN-v6.0-UNIFIED
> **版本:** v6.0-UNIFIED-rev5 → v6.1-OPT（已追加附录 D + E）
> **状态:** ✅ ACTIVE（已修正：统一引擎+向量延拓+L5指挥官+量化反馈+CSM四层认知流+三大死穴修补）
> **日期:** 2026-06-19 → 2026-06-30
> **核心目标:** 整合 v4.x~v5.2x 全部设计，给出系统的哲学公理层、解构层、重构层与协同层的完整全貌

---

## 目录

1. [架构总览：五层宇宙](#1-架构总览五层宇宙)
2. [L0-L4：公理层（哲学与约束）](#2-l0-l4公理层哲学与约束)
3. [Layer 1：入口解构（文本→形式化）](#3-layer-1入口解构文本形式化)
4. [Layer 2：结构重构（形式化→同构判定）](#4-layer-2结构重构形式化同构判定)
5. [Divergent Core：解构引擎](#5-divergent-core解构引擎)
6. [Convergent Core：重构引擎](#6-convergent-core重构引擎)
7. [Meta-Cognitive Arbiter：协同拍板层](#7-meta-cognitive-arbiter协同拍板层)
8. [Coordination Layer：跨层同步](#8-coordination-layer跨层同步)
9. [持久化层：双链路知识图谱](#9-持久化层双链路知识图谱)
10. [数据流全景](#10-数据流全景)
11. [遗忘机制与概念生命周期](#11-遗忘机制与概念生命周期)
12. [实施状态矩阵](#12-实施状态矩阵)
13. [AI控制流：多层LLM协同控制架构](#13-ai控制流多层llm协同控制架构)
14. [关键缺口与下一步](#14-关键缺口与下一步)
15. [附录 D：SLP 视角下的 NLP 优化方向](#附录-dslp-视角下的-nlp-优化方向v61-opt)
16. [附录 E：非论文内容摄取的架构适配方案](#附录-e非论文内容摄取的架构适配方案v61-opt)

---

## 1. 架构总览：五层宇宙

Literature Cortex 不是单一功能系统，而是一个**五层嵌套的认知宇宙**。

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 5: 元认知拍板层 (Meta-Cognitive Arbiter)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ 发散预算  │ │ 收敛停滞  │ │ 视角仲裁  │ │ 验证反馈  │          │
│  │ 控制器   │ │ 检测器   │ │ 器      │ │ 循环    │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: 协同层 (Coordination)                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ 双网络   │ │ 概念健康  │ │ 跨层同步  │                        │
│  │ 协调器   │ │ 监控器   │ │ 引擎    │                        │
│  └──────────┘ └──────────┘ └──────────┘                        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: 双核心引擎 (Dual-Core Engine)                          │
│  ┌────────────────────────┐  ┌────────────────────────┐        │
│  │  Divergent Core        │  │  Convergent Core       │        │
│  │  (解构引擎)            │  │  (重构引擎)            │        │
│  │  ┌────┐┌────┐┌────┐  │  │  ┌────┐┌────┐┌────┐  │        │
│  │  │L1  ││L2  ││L3  │  │  │  │L1  ││L2  ││L3  │  │        │
│  │  │反事││溯因││跨域│  │  │  │正向││规则││层级│  │        │
│  │  │实  ││假设││类比│  │  │  │演绎││校验││验证│  │        │
│  │  └────┘└────┘└────┘  │  │  └────┘└────┘└────┘  │        │
│  └────────────────────────┘  └────────────────────────┘        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 形式化转译层 (Formalization Layer)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ 物理域   │ │ 社会/经济│ │ 逻辑/规则│ │ 抽象映射 │          │
│  │ 键合图   │ │ 系统动力 │ │ Petri网 │ │ 范畴论  │          │
│  │ 元解析器 │ │ 学引擎   │ │ 引擎    │ │ 语义    │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌─────────────────────────────────────────────────────┐      │
│  │ 元角色注册表（Meta-Role Registry）                    │      │
│  │ source / sink / store / dissipate / transform        │      │
│  │ monitor / junction + store_type(potential/kinetic)   │      │
│  └─────────────────────────────────────────────────────┘      │
│  │ 全领域   │ │ 通用元   │ │ LLM     │                        │
│  │ 粗匹配器 │ │ 框架归约 │ │ 兜底    │                        │
│  │ (30+领域)│ │ (4个)    │ │ (5%)    │                        │
│  └──────────┘ └──────────┘ └──────────┘                        │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 入口解构层 (Ingress Layer)                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ 领域分类 │ │ L0-L4   │ │ 通用元  │                        │
│  │ 器(6领域)│ │ 桥接(27)│ │ 框架   │                        │
│  └──────────┘ └──────────┘ └──────────┘                        │
├─────────────────────────────────────────────────────────────────┤
│  L0-L4: 公理层 (Axiom Layer)                                   │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                           │
│  │L0  │ │L1  │ │L2  │ │L3  │ │L4  │                           │
│  │元理论│ │公理 │ │数学 │ │方法 │ │物理 │                           │
│  │6节点│ │12  │ │10  │ │13  │ │8   │                           │
│  └────┘ └────┘ └────┘ └────┘ └────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

**核心哲学：**
- **L0-L4 是公理层**：不处理具体文本，提供跨领域的抽象范式、约束条件和结构同构的底层依据
- **Layer 1-2 是解构层**：将任意文本转化为标准化的形式化结构
- **Layer 3 双核心是运算层**：解构（发散）与重构（收敛）的对抗与协同
- **Layer 4 是协同层**：双网络的同步、健康监控、概念退化
- **Layer 5 是拍板层**：决定何时发散、何时收敛、何时切换视角

---

## 2. L0-L4：公理层（哲学与约束）

### 2.1 定位

L0-L4 不是「数据」，而是「认知的宪法」。它们定义了系统如何理解知识本身的结构。

| 层级 | 名称 | 节点数 | 核心角色 | 类比 |
|------|------|--------|---------|------|
| L0 | 元理论 | 6 | 控制策略、认识边界、因果规则 | 哲学 |
| L1 | 公理 | 12 | 数学基础（ZFC、范畴论、图灵） | 数学 |
| L2 | 数学框架 | 10 | 动力系统、优化、谱分析、拓扑 | 工具 |
| L3 | 方法范式 | 13 | 搜索、递归、自适应、反馈、前馈 | 算法 |
| L4 | 物理现实 | 8 | 振动、热、电磁、材料、信号 | 物理 |

### 2.2 与上层的关系

L0-L4 不直接参与文本分类，而是通过**反向索引**为 Layer 1 提供推导能力：

```
文本 "Bellman equation in MPC" 
  → 未命中 Layer 1 精确匹配（6领域）
  → L0-L4 桥接：命中 L3 "Dynamic Programming"（method-3）
  → method-3 的反向索引：control_system (0.9), economics (0.7), biology (0.7)
  → 返回 control_system 作为候选领域
```

**关键特性：**
- L0-L4 的 `description` 中 "In [domain]:" 模式是反向索引的源头
- 46/49 个节点已建立到 27 个领域的映射
- 这是「哲学范式」向「应用解构」的渗透

---

## 3. Layer 1：入口解构（文本→形式化）

### 3.1 三层转译策略

| 层级 | 覆盖率 | 机制 | 精度 |
|------|--------|------|------|
| Layer 1a | 85% | 领域原生标准匹配（关键词+上下文） | 100% |
| Layer 1b | 10% | L0-L4 反向索引桥接 | 80% |
| Layer 1c | 5% | LLM 兜底提取 | 70% |

### 3.2 输入输出

**输入：** 任意文本（论文摘要、专利、教材段落、用户查询）
**输出：** `DomainClassification`（领域ID + 置信度 + 来源标记）

```python
class DomainClassification:
    layer: int          # 1=精确匹配, 1.5=L0-L4桥接, 2=通用元框架, 3=LLM兜底
    domain_id: str      # 如 "control_system", "biology", "unknown"
    confidence: float   # 0-1
    source: str         # "exact_match" / "l0l4_bridge" / "universal_meta" / "llm_fallback"
```

---

## 4. Layer 2：结构重构（形式化→同构判定）

### 4.1 形式化转译引擎

将文本转化为**标准化五元组函数树**（SGF - Structured Graph Format）：

```json
{
  "function_tree": {
    "input": ["..."],
    "output": ["..."],
    "sub_functions": [...],
    "call_graph": [...],
    "constraints": [...]
  }
}
```

### 4.2 三层转译架构（已修正：统一引擎 + 四类 + 元角色）

**核心修正（v6.0-rev1）：** 废弃"35个独立手写插件"的反模式，改为"四类引擎 + 元角色注册表"。

#### 4.2.1 架构概览

```
文本输入
  ↓
[领域分类器] → 判定 domain_class ∈ {physical, socioeconomic, logical, abstract, unknown}
  ↓
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│  物理域引擎      │ 社会/经济域引擎  │  逻辑/规则域引擎 │  抽象映射域引擎  │
│  (键合图元解析器)│  (系统动力学)   │  (Petri网)      │  (范畴论语义)   │
│  配置表驱动      │  配置表驱动     │  配置表驱动     │  LLM辅助       │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
  ↓
[元角色注册表] → 统一打上 MetaRole 标签（source/sink/store/dissipate/transform/monitor/junction）
  ↓
[统一输出] → FunctionTree（nodes + edges + meta_roles + store_types）
```

#### 4.2.2 物理域引擎：键合图元解析器（Bond Graph Meta-Parser）

**不再为"控制、机械、热、电、流体"各写一个插件。**

内核只做一件事：识别通用物理结构——**势变量（Effort）× 流变量（Flow）= 功率（Power）**。

```python
class BondGraphMetaParser:
    """
    输入：自然语言文本（已做过专有名词替换）
    输出：PhysicalStructure(efforts, flows, elements, causality)
    
    步骤：
      1. 专有名词替换（按配置表把"热阻"→"R元件"）
      2. 识别势变量（力、电压、压力、温度、化学势）
      3. 识别流变量（速度、电流、体积流量、熵流、摩尔流）
      4. 识别元件角色（R/C/I/Se/Sf/TF/GY/0-junction/1-junction）
      5. 因果推断（积分因果 vs 微分因果）
    """
```

**配置表（YAML）示例：**

```yaml
# config/physical_domains/thermal.yaml
domain: thermal
mappings:
  "thermal resistance": { element: "R", meta_role: "dissipate" }
  "heat capacity": { element: "C", meta_role: "store", store_type: "potential" }
  "temperature source": { element: "Se", meta_role: "source" }
  "heat flux": { flow_var: "entropy_flow" }
  "temperature difference": { effort_var: "temperature" }

# config/physical_domains/mechanical.yaml  
domain: mechanical
mappings:
  "spring": { element: "C", meta_role: "store", store_type: "potential" }
  "mass": { element: "I", meta_role: "store", store_type: "kinetic" }
  "damper": { element: "R", meta_role: "dissipate" }
  "force": { effort_var: "force" }
  "velocity": { flow_var: "velocity" }

# config/physical_domains/control.yaml
domain: control
mappings:
  "reference input": { element: "Se", meta_role: "source" }
  "PID controller": { element: "TF", meta_role: "transform" }
  "sensor": { element: "TF", meta_role: "monitor" }  # monitor是transform语义子类
  "actuator": { element: "Sf", meta_role: "sink" }
  "state variable": { element: "I", meta_role: "store", store_type: "kinetic" }
  "error": { element: "0-junction", meta_role: "junction" }  # 0结：代数求和/比较
```

**效果：** 新增一个物理领域 = 写一张20行的YAML配置表，15分钟完成。

#### 4.2.3 非物理域引擎：LLM结构化提取（统一兜底）

对于博弈论、叙事结构、形式语法等没有物理量纲的领域，不走手写解析器，直接走LLM路径。

**强制输出Schema：**

```json
{
  "entities": [
    {"id": "A", "type": "proposition", "meta_role": "source", "content": "..."}
  ],
  "relations": [
    {"source": "A", "target": "B", "type": "implies", "meta_role": "transform"}
  ],
  "constraints": ["..."]
}
```

**LLM路径降级链：**
```
Few-shot Prompt + JSON Schema约束
  ↓
输出校验（字段完整性、type枚举、meta_role合法性）
  ↓
失败 → 自动重试（最多3次）
  ↓
仍失败 → 关键词简单配对（降级）
  ↓
存入 deconstruction_audit 表，标记待人工审核
```

**注意：** 非物理域的"能量关系"是隐喻，不执行守恒计算。统一存储格式兼容，但数值引擎不运行。

#### 4.2.4 元角色注册表（Meta-Role Registry）

跨域对齐的核心基础设施。

```python
class MetaRole(str, Enum):
    SOURCE = "source"         # 源：入度=0，出度≥1
    SINK = "sink"             # 汇：入度≥1，出度=0（严格终点）
    STORE = "store"           # 储能：入度=1，出度=1（反馈环）
    DISSIPATE = "dissipate"   # 耗散：入度=1，出度=0/1
    TRANSFORM = "transform"   # 转换：入度=1，出度=1（映射）
    MONITOR = "monitor"       # 观测：入度=1（旁路），出度=1；语义上是transform子类
    JUNCTION = "junction"     # 汇合：入度≥2，出度≥1（分流/合并/比较）

class StoreType(str, Enum):
    POTENTIAL = "potential"   # C元件：势储能（电压、力、温度）
    KINETIC = "kinetic"       # I元件：流储能（电流、速度、熵流）
```

**对齐规则：**

| 元角色 | 可匹配 | 不可匹配 | 说明 |
|--------|--------|---------|------|
| source | source | 其他 | 严格一对一 |
| sink | sink | 其他 | 严格一对一 |
| store | store | 其他 | 忽略store_type子属性 |
| dissipate | dissipate | 其他 | 严格一对一 |
| transform | transform, monitor | 其他 | monitor是transform语义子类 |
| monitor | monitor, transform | 其他 | 拓扑等价 |
| junction | junction | 其他 | 需验证入度/出度兼容 |

**结构特征校验（入度/出度）：**

```python
STRUCTURE_SIGNATURE = {
    MetaRole.SOURCE:      (0, 1, 1, float('inf')),   # 入度=0，出度≥1
    MetaRole.SINK:        (1, float('inf'), 0, 0),    # 入度≥1，出度=0
    MetaRole.STORE:       (1, 1, 1, 1),               # 入度=1，出度=1
    MetaRole.DISSIPATE:   (1, 1, 0, 1),               # 入度=1，出度=0或1
    MetaRole.TRANSFORM:   (1, 1, 1, 1),               # 入度=1，出度=1
    MetaRole.MONITOR:     (1, 1, 1, 1),               # 入度=1，出度=1（旁路）
    MetaRole.JUNCTION:    (2, float('inf'), 1, float('inf')), # 入度≥2，出度≥1
}
```

### 4.3 结构同构判定（已修正：分层WL + 元角色对齐）

#### 4.3.1 三层匹配策略

CSM（跨域类比引擎）不再只做"度+Jaccard"，而是分层匹配：

```
Step 1: 结构匹配（WL子树同构测试）
  - 忽略标签，只看拓扑连通性
  - 使用VF2算法在候选子图中搜索同构
  - 输出：结构相似度 score_structural

Step 2: 角色对齐（元角色匹配）
  - 对比对应节点的MetaRole标签
  - 验证入度/出度兼容性
  - 输出：角色对齐度 score_role

Step 3: 语义过滤（向量相似度）
  - 对候选匹配对，用Sentence-BERT/SciBERT计算余弦相似度
  - 剔除语义完全不相关的配对（如"热耗散"vs"金融耗散"但上下文无关联）
  - 输出：语义相似度 score_semantic

Step 4: 综合判定
  - 加权融合：score = α·structural + β·role + γ·semantic
  - 默认权重：α=0.5, β=0.3, γ=0.2（结构优先）
  - 阈值：≥0.7 → "潜在类比"；≥0.85 → "高置信类比"
```

#### 4.3.2 关键边界

- **物理域 vs 物理域**：可用全部三层，数值仿真可运行
- **物理域 vs 逻辑域**：结构+角色层可用，语义层降级，**不执行守恒计算**
- **逻辑域 vs 逻辑域**：结构+角色+语义全可用，但数值引擎不运行
- **抽象域（范畴论）**：主要用于元类型标注，不直接参与CSM匹配

---

## 5. Divergent Core：解构引擎

### 5.1 定位

Divergent Core 是系统的**「怀疑能力」**——不相信任何单一结构，主动寻找替代可能。

```
┌─────────────────────────────────────────────────────┐
│              Divergent Core（解构引擎）              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ Layer 1  │ │ Layer 2  │ │ Layer 3  │          │
│  │ 反事实   │ │ 溯因     │ │ 跨域     │          │
│  │ 链路破坏 │ │ 假设生成 │ │ 类比     │          │
│  └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ Layer 4  │ │ 约束空间 │ │ 差异分析 │          │
│  │ 倒置因果 │ │ 映射     │ │ 引擎     │          │
│  │ 约束反推 │ │ (CSM)   │ │ (DAE)   │          │
│  └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐                                     │
│  │ 约束价值 │                                     │
│  │ 评估器   │                                     │
│  │ (CVE)   │                                     │
│  └──────────┘                                     │
└─────────────────────────────────────────────────────┘
```

### 5.2 四层解构机制

| 层级 | 功能 | 输出 |
|------|------|------|
| Layer 1 | 反事实链路破坏 | `BreakReport`（移除哪条边、目标是否仍可达、关键性评分） |
| Layer 2 | 溯因假设生成 | `Hypothesis`（最佳假设 + 置信度 + 候选列表） |
| Layer 3 | 跨域类比（CSM+DAE） | `AnalogyMatch`（源域→目标域的结构映射 + 置信度） |
| Layer 4 | 倒置因果约束反推 | `InvertReport`（假设结果→需要修改哪些约束 + 可行性评分） |

### 5.3 激活追踪（ACT-R 双权重）

```python
activation = ln(freq + 1) − λ·ln(Δt + 1)

# freq: 节点访问频率（长期记忆）
# Δt: 距上次访问的时间（短期记忆）
# λ: 遗忘衰减系数
```

- **探索-利用平衡**：ε-greedy 采样发散起点
- **传播激活**：高激活节点激活其邻居
- **剪枝**：激活度低于 θ_prune 的节点不参与发散

---

## 6. Convergent Core：重构引擎

### 6.1 定位

Convergent Core 是系统的**「验证能力」**——从发散的假设中筛选出结构自洽、可验证的命题。

```
┌─────────────────────────────────────────────────────┐
│              Convergent Core（重构引擎）            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ 正向演绎 │ │ 规则校验 │ │ 层级验证 │          │
│  │ 引擎    │ │ 引擎    │ │ 引擎    │          │
│  └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────┐                        │
│  │ 多视角   │ │ 对偶器   │                        │
│  │ 管理器   │ │ (锚点吸引)│                        │
│  └──────────┘ └──────────┘                        │
└─────────────────────────────────────────────────────┘
```

### 6.2 核心机制

| 模块 | 功能 |
|------|------|
| 正向演绎 | 从事实出发，沿层级结构推导新命题（depth=3） |
| 规则校验 | 约束一致性检查、维度匹配、调用完整性 |
| 层级验证 | 六层解构（what/why/physical/math/eng/failure）是否完整 |
| 多视角管理 | 每个节点的多层级视角（`node_perspectives` 表） |
| 对偶器 | 相似节点锚点吸引，补全缺失视角 |

### 6.3 六层解构模型

每个概念被强制解构为六个维度：

| 维度 | 问题 | 示例（FxLMS） |
|------|------|---------------|
| what | 是什么？ | 前馈自适应振动控制算法 |
| why_exists | 为什么存在？ | 解决前馈路径中次级路径的延迟补偿 |
| physical_basis | 物理基础？ | 声波传播延迟、因果性约束 |
| mathematical_form | 数学形式？ | w(n+1) = w(n) + μ·e(n)·x'(n) |
| engineering_mapping | 工程映射？ | FPGA 定点运算、实时约束 |
| failure_modes | 失效模式？ | 收敛过慢、发散、失配 |

---

## 7. Meta-Cognitive Arbiter：协同拍板层

### 7.1 定位

Meta-Cognitive Arbiter 是系统的**「大脑皮层」**——不是执行具体任务，而是决定执行什么、何时执行、何时停止。

### 7.2 四个子模块

| 模块 | 功能 | 触发条件 |
|------|------|---------|
| **发散预算控制** (AntiBloat) | 根据验证历史动态分配发散资源 | 发散前 |
| **收敛停滞检测** (ConvergenceMonitor) | 检测正向演绎是否陷入局部最优 | 每 depth 结束后 |
| **视角切换仲裁** (PerspectiveArbiter) | 根据查询上下文选择最佳视角 | 查询时 |
| **验证反馈循环** (ValidationFeedback) | 假设验证结果反馈到权重调整 | 验证后 |

### 7.3 决策流程

```
收到任务
  ↓
Step 1: 视角仲裁 → 确定最佳视角
  ↓
Step 2: 收敛演绎 → 正向推导
  ↓
Step 3: 停滞检测 → 是否停滞？
  ↓ 是
Step 4: 发散生成 → Divergent Core 生成假设
  ↓
Step 5: 预算控制 → 截断超限假设
  ↓
Step 6: 约束校验 → Convergent Core 验证
  ↓
Step 7: 反馈记录 → 更新方向统计
  ↓
返回结果
```

---

## 8. Coordination Layer：跨层同步

### 8.1 定位

Coordination Layer 是系统的**「神经系统」**——确保各层之间的信息不丢失、状态不冲突。

### 8.2 核心组件

| 组件 | 功能 |
|------|------|
| **双网络协调器** | 收敛层与发散层之间的请求-响应循环 |
| **概念健康监控** | 识别僵尸概念（长期无激活、无引用） |
| **概念退化引擎** | 低价值概念自动降级（从 asserted → hypothesis → archived） |
| **跨层同步引擎** | 确保持久化层与内存层状态一致 |

---

## 9. 持久化层：双链路知识图谱

### 9.1 数据结构

```
graph.db (SQLite)
├── nodes_v2          — 节点主表（含六层解构字段）
├── edges_v2          — 边表（含因果语义标记）
├── node_perspectives — 多视角表（v5.1设计，v5.2强制实施）
├── perspective_validation — 视角验证记录
├── direction_stats   — 发散方向统计
├── hypothesis_archive — 假设归档
├── node_activation   — ACT-R 激活记录（WAL模式）
├── counterfactual_log — 反事实日志
├── abductive_hypothesis — 溯因假设
├── analogical_matches — 类比匹配
├── inverted_causality — 倒置因果
├── constraint_space_matches — 约束空间匹配
├── difference_analysis — 差异分析
└── dual_matches / perspective_suggestions — 对偶器相关
```

### 9.2 双链路语义

- **事实断言层** (asserted): 100%可信，用户确认或文献验证
- **假设推演层** (hypothesis): 条件化+置信度，待验证
- **自动推导层** (auto_gen): 系统生成，待人工审核

---

## 10. 数据流全景

```
用户输入: "分析 FxLMS 的热控耦合可能性"
  ↓
[Layer 1] 领域分类
  - 精确匹配: control_system (0.94)
  - L0-L4桥接: 确认 control_system + thermal_system
  ↓
[Layer 2] 形式化转译
  - 加载 control_system + thermal_system 模板
  - 输出 FxLMS 函数树 + 热传导函数树
  ↓
[Layer 3 双核心]
  Convergent: 正向演绎 FxLMS 的物理基础
  Divergent: 反事实——如果热效应作为次级路径？
  ↓
[Layer 4 协同]
  - 双网络协调：收敛发现"热膨胀→延迟变化→滤波失配"
  - 发散生成"温度补偿前馈"假设
  ↓
[Layer 5 拍板]
  - 视角仲裁：engineering(L5) + physical(L1)
  - 预算控制：给 thermal-coupling 方向分配 15 预算
  - 停滞检测：depth=2 有 3 新假设，继续
  ↓
输出: 结构化的多视角分析报告
```

---

## 11. 实施状态矩阵

### 11.1 各层实现状态

| 层级 | 模块 | 设计 | 实现 | 测试 | 备注 |
|------|------|------|------|------|------|
| L0-L4 | 种子库 | ✅ | ✅ | ✅ | 49节点，JSON静态 |
| L0-L4 | 反向索引 | ✅ | ✅ | ✅ | 46节点→27领域 |
| Layer 1 | 精确匹配 | ✅ | ✅ | ✅ | 6领域 |
| Layer 1 | L0-L4桥接 | ✅ | ✅ | ⚠️ | 需优化关键词覆盖 |
| Layer 2 | 键合图元解析器 | ✅ | ⚠️ | ⚠️ | bond_graph.py可复用，需提取为通用引擎 |
| Layer 2 | 物理域配置表 | ✅ | ❌ | ❌ | 需写thermal/mechanical/control等配置 |
| Layer 2 | 非物理域LLM兜底 | ✅ | ✅ | ⚠️ | generic_llm已有LLM路径，需稳定调用 |
| Layer 2 | 元角色注册表 | ✅ | ❌ | ❌ | 需新建meta_roles.py，定义7个元角色+映射 |
| Layer 2 | 统一输出格式 | ✅ | ✅ | ✅ | FunctionTreeFormat已实现 |
| Layer 3 | 反事实 | ✅ | ⚠️ | ⚠️ | CounterfactualEngine可用，但受限于图密度 |
| Layer 3 | 溯因 | ✅ | ❌ | ❌ | AbductiveEngine为简化版 |
| Layer 3 | 跨域类比(CSM) | ✅ | ❌ | ❌ | 需实现：VF2子图+元角色对齐+向量过滤 |
| Layer 3 | 倒置因果 | ✅ | ❌ | ❌ | InvertedCausalityEngine为数值替换版 |
| Layer 3 | ACT-R激活 | ✅ | ✅ | ✅ | 双权重实现 |
| Layer 3 | CVE | ✅ | ❌ | ❌ | 框架存在 |
| Layer 3 | 正向演绎 | ✅ | ⚠️ | ⚠️ | depth=3，无停滞检测 |
| Layer 3 | 规则校验 | ✅ | ⚠️ | ⚠️ | 基础约束 |
| Layer 3 | 多视角管理 | ✅ | ✅ | ⚠️ | node_perspectives表 |
| Layer 3 | 对偶器 | ✅ | ⚠️ | ⚠️ | 算法实现，未批量应用 |
| Layer 4 | 双网络协调 | ✅ | ❌ | ❌ | 仅返回建议 |
| Layer 4 | 健康监控 | ✅ | ⚠️ | ⚠️ | 基础僵尸识别 |
| Layer 5 | 发散预算 | ✅ | ❌ | ❌ | |
| Layer 5 | 停滞检测 | ✅ | ❌ | ❌ | |
| Layer 5 | 视角仲裁 | ✅ | ❌ | ❌ | |
| Layer 5 | 反馈循环 | ✅ | ❌ | ❌ | |

### 11.2 关键缺口（v6.0-rev1 已修正 Layer 2 方向）

1. **Layer 2 形式化转译（已修正为统一引擎路线）**:
   - 旧问题：35个独立手写插件，33个空壳
   - 新路线：1个键合图元解析器 + 5张YAML配置表 + LLM兜底
   - 待实现：元解析器提取、配置表编写、元角色注册表

2. **Layer 3 跨域类比（CSM）**: 核心引擎未实现。需串接：VF2子图匹配 → 元角色对齐 → 向量语义过滤

3. **Layer 4 双网络协调**: 设计完整但实现被简化，协调循环未自动执行

4. **Layer 5 元认知层**: 全部四个子模块未实现

5. **AI控制流（CL0-CL4）**: 设计完成，零代码实现

---

### 12.3 遗忘机制与概念生命周期

Literature Cortex 的遗忘不是被动的时间衰减，而是主动的**冗余检测与压缩策略**。它包含三个核心机制：

#### 12.3.1 双维度激活追踪

每个节点维护两个计数器：

| 维度 | 计数器 | 公式 | 含义 |
|------|--------|------|------|
| **频率** | `access_count` | `freq = ln(access_count + 1)` | 长期被引用次数（类似Hebbian权重） |
| **新近性** | `last_accessed` | `recency = -λ·ln(Δt + 1)` | 距上次访问的时间（ACT-R 衰减） |

**综合激活度：**
```
activation = ln(freq + 1) − λ·ln(Δt + 1)
```
- **λ**: 遗忘衰减系数（默认 0.5）
- **θ_forget**: 遗忘阈值（默认 -1.0，激活度低于此值触发遗忘审查）
- **θ_prune**: 剪枝阈值（默认 0.1，发散时低于此值的节点不参与传播）

#### 12.3.2 Hebbian 共现计数（传播激活）

当两个节点在同一上下文中共现，记录共现次数：
```
co_occurrence[A][B] += 1  # 每次 A 和 B 在同一推导路径中出现
```

这是 Hebbian 学习的简化版：
- **完整版**：`w_ij += α·pre_i·post_j`（需要激活值矩阵）
- **当前版**：仅记录共现次数，传播时累加邻居频率权重

```python
# 传播激活示例
def spread_activation(start_node, max_depth=2):
    activated = {start_node: base_activation}
    for depth in range(max_depth):
        for node, act in list(activated.items()):
            for neighbor in get_neighbors(node):
                co_occ = co_occurrence[node][neighbor]
                boost = ln(co_occ + 1) * 0.1  # 共现加权
                activated[neighbor] = activated.get(neighbor, 0) + act * boost
    return activated
```

#### 12.3.3 遗忘判定逻辑：冗余检测与压缩

**核心洞察：** 如果某个节点在其概念学科内被频繁提及，但**计数不增**，意味着该节点存在冗余或低效，需要进入遗忘审查流程。

**判定条件：**
```python
def should_review_forgetting(node_id):
    node = get_node(node_id)
    
    # 条件1：激活度低于遗忘阈值
    if activation(node_id) < THETA_FORGET:
        return True
    
    # 条件2：被引用但计数不增（周围概念演化，该节点成为冗余中介）
    refs = get_incoming_edges(node_id)
    if len(refs) > 3 and access_count(node_id) == 0 for last_30_days:
        # 被多次引用但自身长期未被直接访问
        return True
    
    # 条件3：对偶器显示该节点视角可被完全吸收到邻居
    duals = get_dual_matches(node_id)
    if any(d.similarity > 0.85 and d.target_has_all_my_perspectives for d in duals):
        return True
    
    return False
```

**遗忘处理流程：**
```
发现候选节点
  ↓
Step 1: 评估是否可被分解
  - 检查节点的六层解构内容
  - 如果每个维度都可映射到已有节点 → 标记为"可分解"
  ↓
Step 2: 分解压缩
  - 将节点的 what/why/physical/math/eng/failure 分别迁移到最相似节点
  - 更新边：将指向该节点的边重定向到分解目标
  - 保留一条 "compressed_into" 记录
  ↓
Step 3: 迁入低效区（Limbo Zone）
  - 从 active graph 移除
  - 写入 `limbo_nodes` 表（保留完整信息，但不再参与推导）
  - 设置 `resurrection_threshold`: 如果被查询 N 次，可迁回
  ↓
Step 4: 定期审查（每月）
  - 检查 limbo 节点是否被频繁查询
  - 如果是 → 重新评估是否迁回或彻底归档
  - 如果否 → 保留在 limbo 或迁移到 `archive_nodes`
```

#### 12.3.4 低效区（Limbo Zone）

```sql
CREATE TABLE IF NOT EXISTS limbo_nodes (
    id TEXT PRIMARY KEY,
    original_node_id TEXT NOT NULL,
    compressed_into TEXT,           -- JSON: [{target_id, dimension}, ...]
    compression_reason TEXT,        -- "redundant" / "underutilized" / "superseded"
    limbo_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count_in_limbo INTEGER DEFAULT 0,  -- 在 limbo 中被查询的次数
    resurrection_threshold INTEGER DEFAULT 5,  -- 超过此值考虑迁回
    last_queried_at TIMESTAMP
);
```

**Limbo 节点的行为：**
- 不参与正向演绎、发散生成、对偶匹配
- 但被查询时仍然返回内容（从 limbo 表读取）
- 每次查询增加 `access_count_in_limbo`
- 如果 `access_count_in_limbo > resurrection_threshold` → 触发"复活审查"

#### 12.3.5 与概念退化（Degradation）的协同

概念退化是主动降级，遗忘是被动审查。两者协同：

```
健康监控发现节点
  ↓
长期无激活 → 遗忘审查 → 可能进入 Limbo
  ↓
对偶器发现完全覆盖 → 退化审查 → 可能压缩/合并
  ↓
两者同时满足 → 优先压缩（保留结构），其次 Limbo（保留信息），最后归档（仅保留记录）
```

#### 12.3.6 实施状态

| 组件 | 设计 | 实现 | 状态 |
|------|------|------|------|
| ACT-R 双权重激活 | ✅ | ✅ | `activation.py` 已实现 |
| 共现计数（简化 Hebbian） | ✅ | ✅ | `node_activation` 表记录 |
| 遗忘阈值审查 | ✅ | ⚠️ | 配置已定义，自动审查未触发 |
| 分解压缩到邻居 | ✅ | ❌ | 对偶器未批量应用 |
| Limbo 区 | ✅ | ❌ | 表未创建 |
| 复活机制 | ✅ | ❌ | |
| 概念退化引擎 | ✅ | ⚠️ | `health_monitor.py` 基础识别，无自动执行 |

**这是 v6.0 的明显缺口：遗忘机制存在于工程设计文档，但统一架构中未体现，且大部分未实现。**

---

## 13. AI控制流：多层LLM协同控制架构

### 13.1 定位与核心原则

Literature Cortex 的既有五层架构（L0-L4 → Layer 1-5）解决了**知识如何被解构、重构与协同**的问题，但未解决一个更根本的问题：**如何控制 AI（LLM）本身，使其不沦为模糊语义的 `if-else` 黑盒**。

**核心洞察：**
- LLM 本质上是统计概率工具，其输出服从分布而非确定规则
- 氛围编程中 AI 常被名词陷阱困住，简化本质、不深入结构
- Agent 设计若把 LLM 当作模糊语义的 `if-else`，则失去了工程可控性

**设计原则：**
1. **算法协调概率**：通过准确的算法层去约束和调度 LLM，而非让 LLM 自由裁决
2. **分层约束递减**：从硬约束（100%规则）到软约束（概率推断），每层有明确的边界
3. **自指修正**：高层可质疑低层，低层为高层提供锚点，形成闭环
4. **算力比例化**：协调层不做跷跷板式切换，而是按比例分配各层算力预算

### 13.2 五层控制架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Control Layer 4: 协调统筹层 (Coordination)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ 算力比例 │ │ 层间仲裁 │ │ 输出融合 │                        │
│  │ 分配器   │ │ 器      │ │ 器      │                        │
│  └──────────┘ └──────────┘ └──────────┘                        │
├─────────────────────────────────────────────────────────────────┤
│  Control Layer 3: 质疑层 (Skeptic)                               │
│  ┌──────────┐ ┌──────────┐                                     │
│  │ 边界条件 │ │ 假设失效 │                                     │
│  │ 审查器   │ │ 检测器   │                                     │
│  └──────────┘ └──────────┘                                     │
├─────────────────────────────────────────────────────────────────┤
│  Control Layer 2: 远迁移思考层 (Far-Transfer)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ 持久化层 │ │ 跨域模式 │ │ 类比激活 │                        │
│  │ 读取器   │ │ 检索器   │ │ 引擎    │                        │
│  └──────────┘ └──────────┘ └──────────┘                        │
├─────────────────────────────────────────────────────────────────┤
│  Control Layer 1: 近迁移反思层 (Near-Transfer)                   │
│  ┌──────────┐ ┌──────────┐                                     │
│  │ 规则执行 │ │ 局部一致性│                                     │
│  │ 验证器   │ │ 检查器   │                                     │
│  └──────────┘ └──────────┘                                     │
├─────────────────────────────────────────────────────────────────┤
│  Control Layer 0: 硬约束代码层 (Hard-Constraint)                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ 精确规则 │ │ 形式化校验│ │ 维度审查 │                        │
│  │ 引擎    │ │ 引擎    │ │ 引擎    │                        │
│  └──────────┘ └──────────┘ └──────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

| 控制层级 | 名称 | 核心功能 | 约束强度 | LLM参与度 |
|---------|------|---------|---------|----------|
| CL0 | 硬约束代码层 | 精确规则引擎、形式化校验、维度审查 | 100% | 0% |
| CL1 | 近迁移反思层 | 验证规则执行结果、局部一致性检查 | 80% | 10% |
| CL2 | 远迁移思考层 | 从持久化层读取、跨域模式检索、类比激活 | 50% | 60% |
| CL3 | 质疑层 | 审查边界条件、检测假设失效、挑战低层结论 | 40% | 70% |
| CL4 | 协调统筹层 | 算力比例分配、层间仲裁、输出融合 | 30% | 40% |

### 13.3 各层详细设计

#### CL0 — 硬约束代码层

**定位：** 系统的绝对地基。零 LLM 参与，所有输出必须 100% 可复现、可验证。

**核心模块：**
| 模块 | 功能 | 示例 |
|------|------|------|
| 精确规则引擎 | 执行确定性的形式化规则 | SGF 函数树的字段完整性检查 |
| 形式化校验引擎 | 验证数学一致性 | 公式维度匹配、调用图无环 |
| 维度审查引擎 | 物理/工程约束检查 | 单位一致性、量纲分析 |

**输入输出：**
- **输入：** Layer 2 输出的形式化结构（SGF、键合图、信号流图）
- **输出：** `HardConstraintReport`（通过 / 失败 + 失败项列表）

```python
class HardConstraintReport:
    passed: bool
    failures: List[ConstraintFailure]  # 字段缺失、维度冲突、循环依赖等
    latency_ms: int  # 必须在 <10ms 内完成
```

**关键约束：**
- 执行时间 < 10ms（纯代码，零 LLM 调用）
- 无概率输出，只有布尔判定
- 失败时直接阻断上层流程，不允许 LLM "兜底绕过"

#### CL1 — 近迁移反思层

**定位：** 贴合硬约束的局部反思。不挑战规则本身，但验证规则在**当前上下文**中是否正确执行。

**核心机制：**
1. **规则执行验证器：** 检查 CL0 的判定是否符合预期模式
   - 例："FxLMS 的数学形式必须包含 `w(n+1)`" → 验证该字段确实存在
2. **局部一致性检查器：** 检查同一文档内多个形式化结构之间的一致性
   - 例：摘要中的 `μ` 与正文中 `μ` 的取值范围是否一致

**输入输出：**
- **输入：** CL0 的 `HardConstraintReport` + 原始文本片段
- **输出：** `NearTransferReport`（一致性评分 + 可疑项列表）

```python
class NearTransferReport:
    consistency_score: float  # 0-1
    suspicious_items: List[SuspiciousItem]
    # suspicious_item: 字段存在但值异常、上下文不一致等
```

**与 LLM 的关系：**
- 10% 的 LLM 参与度：仅用于处理 CL0 无法覆盖的"边缘一致性"问题
- LLM 被严格限制在"描述性任务"（"这段文本中的 μ 是否有歧义？"），不做判定

#### CL2 — 远迁移思考层

**定位：** 从系统的**持久化知识**中读取，进行跨域关联和模式识别。这是 LLM 的核心价值层——利用其泛化能力，但数据锚点必须来自持久化层。

**核心机制：**
1. **持久化层读取器：**
   - 从 `graph.db` 检索与当前概念相关的节点（ACT-R 双权重排序）
   - 读取 `node_perspectives` 的多视角信息
   - 检索 `analogical_matches` 的既有跨域类比
2. **跨域模式检索器：**
   - 基于 WL 子树同构测试，查找结构相似的既有概念
   - 激活度传播：从当前节点出发，沿高共现边传播
3. **类比激活引擎：**
   - 调用 LLM："给定 [结构A] 和 [结构B]，它们之间的映射关系是什么？"
   - LLM 的输出必须附加到 `analogical_matches` 表，标记为 `auto_gen`

**输入输出：**
- **输入：** 当前任务上下文 + CL0/CL1 的输出
- **输出：** `FarTransferReport`（关联概念列表 + 类比假设 + 置信度）

```python
class FarTransferReport:
    related_concepts: List[NodeActivation]  # ACT-R 排序后的相关节点
    analogies: List[AnalogyHypothesis]      # 结构映射假设
    confidence: float  # 基于持久化数据的密度加权
```

**关键约束：**
- LLM 不被允许"编造"知识：所有远迁移的锚点必须来自 `graph.db`
- LLM 的角色是"模式补全"（填补数据稀疏时的映射），不是"知识生成"
- 每个类比假设必须可追溯至持久化层的至少一个锚点

#### CL3 — 质疑层

**定位：** 主动挑战低层（CL0-CL2）的隐含假设。硬约束代码不可能无失误，规则本身可能有边界条件错误、遗漏或过时。

**核心机制：**
1. **边界条件审查器：**
   - 扫描 CL0 规则的边界条件（"此规则在 [X] 场景下是否失效？"）
   - 例："维度审查引擎假设所有物理量都有 SI 单位，但无量纲数（如雷诺数）怎么办？"
2. **假设失效检测器：**
   - 检测 CL1/CL2 输出中违反 L0-L4 公理层的内容
   - 例：CL2 生成的一个类比假设违反了 L0 "因果律" 的约束
3. **低层结论挑战：**
   - 调用 LLM："CL0 判定此结构不合法。是否存在 CL0 规则未覆盖的合法情况？"
   - LLM 输出进入 `skeptic_challenges` 表，待人工审核

**输入输出：**
- **输入：** CL0/CL1/CL2 的全部输出 + L0-L4 公理层
- **输出：** `SkepticReport`（挑战列表 + 风险等级 + 建议行动）

```python
class SkepticReport:
    challenges: List[Challenge]
    # challenge: {target_layer, target_module, issue_type, severity, suggested_action}
    risk_level: str  # "low" / "medium" / "high" / "critical"
```

**关键约束：**
- 质疑层本身不替代低层判定，只生成"待审查项"
- `critical` 级别挑战必须触发人工审核或暂停任务
- LLM 参与度 70%：质疑本质上是创造性任务，但需要 L0-L4 作为锚点约束

#### CL4 — 协调统筹层

**定位：** 不是跷跷板式的"要么CL0要么LLM"，而是**按比例分配算力预算**，统筹各层输出的最终决策。

**核心机制：**
1. **算力比例分配器：**
   - 根据任务类型动态分配各层算力预算（token/时间/调用次数）
   - 例："形式化转译"任务 → CL0: 50%, CL1: 20%, CL2: 15%, CL3: 10%, CL4: 5%
   - 例："跨域类比"任务 → CL0: 10%, CL1: 10%, CL2: 50%, CL3: 20%, CL4: 10%
2. **层间仲裁器：**
   - 当 CL0（通过）与 CL3（质疑）冲突时，根据任务域的容错性裁决
   - 例：工程映射层（L5）更信任 CL0；物理基础层（L1）更重视 CL3
3. **输出融合器：**
   - 将各层输出按置信度加权融合
   - CL0 输出权重固定为 1.0（硬约束不可override），其余层按历史准确率动态调整

**输入输出：**
- **输入：** CL0-CL3 的全部输出 + 任务类型 + 历史准确率统计
- **输出：** `CoordinationDecision`（最终行动 + 置信度 + 各层贡献度）

```python
class CoordinationDecision:
    action: str  # "proceed" / "retry_with_more_cl2" / "escalate_to_human" / "halt"
    confidence: float
    layer_contributions: Dict[str, float]  # {cl0: 0.5, cl2: 0.3, ...}
    reasoning: str  # 决策依据的简短说明
```

**关键约束：**
- 算力分配不是固定比例，而是基于任务类型的预设模板 + 历史反馈的动态微调
- CL0 的 `passed=False` 不能被 CL4 override，只能通过 CL3 的 challenge 进入人工审核
- 所有决策必须可追溯至至少两层的一致或冲突信号

### 13.4 数据流与控制流

```
用户输入 / 系统任务
  ↓
[CL4] 算力分配器 → 确定各层预算比例
  ↓
[CL0] 硬约束执行 ─────────────────────┐
  ↓ 通过/失败                        │
[CL1] 近迁移反思 ───────────────────┐ │
  ↓ 一致性评分                      │ │
[CL2] 远迁移思考 ─────────────────┐ │ │
  ↓ 类比假设                        │ │ │
[CL3] 质疑层 ───────────────────┐ │ │ │
  ↓ 挑战列表                      │ │ │ │
[CL4] 层间仲裁 + 输出融合 ←─────┘ │ │ │
  ↓
最终输出 或 人工审核
```

**控制流规则：**
1. CL0 失败 → 直接阻断，不进入 CL1-CL4（除非 CL3 发起 challenge 进入审核）
2. CL1 一致性评分 < 0.5 → 触发 CL2 进行更多远迁移检索
3. CL2 类比置信度 < 0.3 → 降低该方向算力分配，转投其他方向
4. CL3 产生 critical 挑战 → 强制人工审核，CL4 无权裁决
5. CL4 的融合置信度 < 0.6 → 返回 "retry_with_more_X" 而非直接输出

### 13.5 与现有五层宇宙的映射

AI 控制流不是替代既有架构，而是**横切（cross-cutting）于既有架构之上**的控制平面：

| 既有层级 | AI控制流映射 | 说明 |
|---------|------------|------|
| L0-L4 公理层 | CL3 的审查锚点 | 质疑层用公理层作为"正确性标准" |
| Layer 1 入口解构 | CL0 的主要战场 | 领域分类的精确匹配由 CL0 硬约束处理 |
| Layer 2 形式化转译 | CL0 + CL1 | 模板匹配（CL0）+ 局部一致性（CL1） |
| Layer 3 Divergent Core | CL2 远迁移 + CL3 质疑 | 发散由远迁移驱动，质疑防止发散失控 |
| Layer 3 Convergent Core | CL0 + CL1 | 收敛由硬约束和局部反思保障 |
| Layer 4 Coordination | CL4 的子集 | 系统协同层关注数据同步，AI控制流关注算力分配 |
| Layer 5 Arbiter | CL4 的仲裁器 | 拍板层的具体实现由 CL4 统筹 |
| 持久化层 | CL2 的数据源 | 远迁移思考层必须锚定于持久化知识 |

### 13.6 实施状态

| 控制层级 | 模块 | 设计 | 实现 | 状态 |
|---------|------|------|------|------|
| CL0 | 精确规则引擎 | ✅ | ⚠️ | Layer 2 部分规则已存在，未统一为 CL0 |
| CL0 | 形式化校验引擎 | ✅ | ❌ | 维度审查、调用图检查未实现 |
| CL1 | 规则执行验证器 | ✅ | ❌ | 概念设计，无代码 |
| CL1 | 局部一致性检查器 | ✅ | ❌ | |
| CL2 | 持久化层读取器 | ✅ | ⚠️ | `graph.db` 查询存在，未封装为 CL2 接口 |
| CL2 | 跨域模式检索器 | ✅ | ❌ | WL 同构测试未实现 |
| CL2 | 类比激活引擎 | ✅ | ❌ | |
| CL3 | 边界条件审查器 | ✅ | ❌ | 概念设计 |
| CL3 | 假设失效检测器 | ✅ | ❌ | |
| CL4 | 算力比例分配器 | ✅ | ❌ | 概念设计，无历史反馈数据 |
| CL4 | 层间仲裁器 | ✅ | ❌ | |
| CL4 | 输出融合器 | ✅ | ❌ | |

**关键缺口：**
1. CL0 的统一封装：现有 Layer 2 的规则分散在各模块，未提炼为独立的硬约束层
2. CL2 的持久化锚点机制：LLM 调用尚未强制绑定 `graph.db` 检索结果
3. CL3 的 L0-L4 审查接口：公理层尚未暴露为可编程的审查规则
4. CL4 的历史反馈循环：需要积累至少 1000 次任务执行数据才能启动动态比例调整

---

## 15. 设计变更记录（Change Log）

### v6.0-UNIFIED-rev1（2026-06-23）

**问题来源：** 外部架构评估指出的6项结构性缺陷（35插件反模式、L0-L4脱节、L5与CL权责混乱、反馈缺量化、跨域类比理想化、CL悬挂层）。

**核心变更：Layer 2 从"35个手写插件"改为"四类引擎+元角色注册表"**

| # | 变更项 | 原设计 | 新设计 | 原因 |
|---|--------|--------|--------|------|
| 1 | Layer 2架构 | 35个独立插件，各写解析逻辑 | 4类引擎（物理/社会经济/逻辑/抽象）+ YAML配置表 | 35插件不可持续，33个空壳 |
| 2 | 物理域解析 | bond_graph.py + control_system.py 各自为政 | 键合图元解析器 + 配置表驱动 | 键合图本身就是多物理域统一语言 |
| 3 | 元角色层 | 无 | 7个元角色（source/sink/store/dissipate/transform/monitor/junction）+ store_type子属性 | 跨域对齐必须有统一角色语义 |
| 4 | sink定义 | 模糊（含误差传感器） | 严格：入度≥1，出度=0的终点 | 拓扑一致性要求 |
| 5 | monitor定位 | 独立角色 | transform语义子类，物理域为信息转换 | 传感器本质是旁路能量域转换 |
| 6 | CSM匹配策略 | 度+Jaccard | 三层：WL结构→元角色对齐→向量语义过滤 | 原策略精度太低 |
| 7 | 非物理域 | 33个空壳插件 | LLM结构化提取（JSON Schema约束） | 抽象领域无法手写解析 |
| 8 | 统一存储 | FunctionTree | FunctionTree + meta_role + store_type | 兼容四类引擎输出 |

**未变更部分（确认保留）：**
- L0-L4公理层：设计正确，无需调整
- Layer 1入口解构：关键词提取降级为toy级，但架构正确
- Layer 3双核心：收敛引擎可用，发散引擎反事实/激活可用，CSM待实现
- Layer 4协同层：框架存在，协调循环待实现
- Layer 5元认知：设计正确，待实现
- AI控制流（CL0-CL4）：设计正确，但需与L5合并权责（下一步）
- 持久化层：Schema兼容，无需调整

**下一步（按优先级）：**
1. 实现键合图元解析器（提取bond_graph.py核心逻辑为通用引擎）
2. 编写5张物理域YAML配置表（thermal/mechanical/electrical/fluid/control）
3. 实现元角色注册表（meta_roles.py）
4. 实现VF2子图匹配（替换SimpleWL的全图匹配）
5. 串接CSM调度器（三层匹配策略）
6. 合并L5与CL层权责（解决"两个大脑"问题）

### v6.0-UNIFIED-rev3（2026-06-24）

**问题来源：** L5元认知层与CL控制流层的权责冲突（两个"大脑"互相争抢指挥权）。

**核心修正：L5是唯一指挥官，CL是L5的"执行模态"（Execution Mode）**

| 层级 | 旧定位 | 新定位 | 类比 |
|------|--------|--------|------|
| L5 | 与CL平行的"拍板层" | **唯一指挥官**（元认知决策中枢） | 大脑皮层 |
| CL0-CL4 | 独立的"横切控制层" | **L5的上下文配置**（执行模态） | 脊髓反射 |

**具体重构：**

```python
class ExecutionMode(Enum):
    """L5 控制下的执行模态，对应原 CL0-CL4。"""
    HARD_CODED = 0     # 原 CL0：100%硬约束，0% LLM
    NEAR_REFLECT = 1   # 原 CL1：80%规则，10% LLM（局部反思）
    FAR_THINK = 2      # 原 CL2：50%规则，60% LLM（远迁移）
    SELF_QUESTION = 3  # 原 CL3：40%规则，70% LLM（质疑）
    COORDINATE = 4     # 原 CL4：30%规则，40% LLM（统筹协调）

class MetaCognitiveArbiter:
    """L5 核心：唯一指挥官，接收状态输入，输出执行模态。"""
    
    def decide(self, state: SystemState) -> ExecutionMode:
        # 1. 发散预算检查（L5 原发职责）
        if state.divergence_budget <= 0:
            return ExecutionMode.HARD_CODED  # 强制停止发散
        
        # 2. 收敛停滞检查（L5 原发职责）
        if state.convergence_stagnation_detected and state.budget_remaining > 20:
            return ExecutionMode.FAR_THINK  # 允许深度发散
        
        # 3. 接收 CL 反馈（CL 只是输入信号，不是决策依据）
        if state.cl2_analogy_confidence < 0.3:
            # CL2 说类比置信度低 → L5 决定切换视角，不强行发散
            if state.budget_remaining < 10:
                return ExecutionMode.HARD_CODED  # 预算不足，直接回退
            return ExecutionMode.NEAR_REFLECT  # 预算够，尝试局部优化
        
        # 4. 默认
        return ExecutionMode.COORDINATE
```

**关键规则：**
- CL 层**不独立发号施令**，只向 L5 提供**状态信号**（budget, confidence, stagnation flag）
- 所有决策由 `MetaCognitiveArbiter.decide()` 统一输出
- 执行流是**单向的**：L5 → 执行模态 → 各层按模态约束运行
- 消除了 L5 与 CL 之间的双向消息和死锁风险

**为什么正确：**
1. **生物学对齐**：人的元认知（前额叶）可以压制本能（边缘系统），控制权永远在高层
2. **消除死锁**：决策流单向，无需层间同步锁
3. **简化测试**：只需测试 L5 的决策逻辑，不需要测试 L5-CL 交互

**未变更：** CL 的 5 种能力（硬约束、近迁移、远迁移、质疑、协调）全部保留，只是从"独立层"变为"L5 决策后的执行模态"。

### v6.0-UNIFIED-rev4.1（2026-06-24）

**问题来源：** Issue 4 补全 — 反馈循环的"关系阈值"和"成本阈值"缺失。

**核心补丁：量化反馈完整版（单体+关系+成本三维度量）**

| # | 补丁项 | 原因 | 方案 |
|---|--------|------|------|
| 4.1 | 级联传播衰减 | 僵尸节点感染邻居 | `CASCADE_DECAY_RATE=0.8` + 边权重阈值 |
| 4.2 | 共现亲和度 | 区分冗余合并 vs 跨域候补 | `co_occurrence` 计数 + 双分支判定 |
| 4.3 | 成本分级调度 | Heavy动作并发导致系统卡死 | `ActionCost`枚举 + `Budget_Scheduler` |
| 4.4 | 校准器增强 | 仅precision/recall维度不足 | 增加 `cost_efficiency` 维度 |

**关键升级：**
- 触发条件表从"单体触发"升级为"单体+关系+成本"三列
- 冗余检测不再只看 `WL_sim>0.85`，而是 `WL_sim>0.85 AND co_occurrence>5` → 合并；`co_occurrence=0` → CSM候补
- 新增 `BudgetScheduler`：Heavy动作超3个时自动降级/延迟
- 校准器新增成本效率维度：系统响应慢时自动提高阈值、减少并发

**未变更：** rev4 的全部内容（三层阈值体系、数据校准器、触发条件表）全部保留，rev4.1 是在其上的增量增强。

### v6.0-UNIFIED-rev4（2026-06-24）

**问题来源：** Issue 4 — 反馈循环（Layer 4）缺少量化指标和触发条件；Issue 5 — 跨域类比（CSM）过于理想化，缺少语义降级链。

**核心补丁：**

| # | 补丁项 | 原因 | 方案 |
|---|--------|------|------|
| 4 | 量化指标+触发条件 | 僵尸识别、遗忘审查、概念退化均无明确阈值 | 引入可配置阈值表+数据校准机制 |
| 5 | 跨域类比语义降级 | WL结构匹配失败后系统卡住 | 已在新CSM三层匹配中解决：结构→角色→语义降级链 |

#### 补丁4：反馈循环量化指标（Quantified Feedback Loop）— 完整版（v4.1）

**问题：** 遗忘阈值是拍脑袋值，且仅管理单体节点，忽略了级联传播、共现语义和执行成本。

**方案：三层阈值体系 + 三维度量（单体/关系/成本）**

```python
class ThresholdConfig:
    """可配置阈值表，支持单体、关系、成本三维度量。"""
    
    # ===== 第一层：单体阈值（原设计）=====
    # 激活度（ACT-R公式）
    FORGET_REVIEW = -1.0      # 触发遗忘审查
    FORGET_PRUNE = 0.1       # 发散时剪枝
    FORGET_LIMBO = -2.0     # 直接进入低效区
    
    # ===== 第二层：关系阈值（新增）=====
    # 级联传播衰减
    CASCADE_DECAY_RATE = 0.8   # 僵尸节点向邻居传播衰减比例（0.8=每跳衰减20%）
    EDGE_WEIGHT_THRESHOLD = 0.7  # 触发级联传播的最小边权重
    
    # 共现亲和度
    CO_OCCURRENCE_MERGE = 5     # 高共现→合并阈值（>=5次同时出现）
    CO_OCCURRENCE_ANALOGY = 0   # 零共现→跨域候补（直接送入CSM）
    
    # ===== 第三层：成本阈值（新增）=====
    # 执行成本分级（ActionCost枚举）
    MAX_HEAVY_PER_CYCLE = 3     # 单轮次最大重计算动作数
    MAX_TOTAL_MS_PER_CYCLE = 5000  # 单轮次总时间预算（ms）
    
    # 统计相似度（原设计）
    REDUNDANT_SIMILARITY = 0.85
    DEGRADATION_CONFIDENCE = 0.3
```

**ActionCost 枚举（执行成本分级）：**

| 动作 | 成本分级 | 操作内容 | 典型耗时 |
|------|---------|---------|---------|
| 僵尸识别 | Micro | 查询数据库入度/出度 | <1ms |
| 遗忘审查 | Normal | 计算激活度，比对阈值 | <5ms |
| 冗余检测 | Normal | WL结构相似度计算 | <10ms |
| 反事实审核 | Heavy | BFS图遍历+替代路径搜索 | 50-200ms |
| 溯因假设 | Heavy | LLM调用（或本地推理） | 100-500ms |
| 跨域类比 | Heavy | CSM引擎（WL+角色+向量） | 50-500ms |

**Budget_Scheduler（成本调度器）：**

```python
class BudgetScheduler:
    """当重负载动作累积时，触发分时调度。"""
    
    def schedule(self, pending_actions: List[Action]) -> List[Action]:
        # 1. 按成本排序：Micro优先，Heavy延后
        micro = [a for a in pending_actions if a.cost == ActionCost.MICRO]
        normal = [a for a in pending_actions if a.cost == ActionCost.NORMAL]
        heavy = [a for a in pending_actions if a.cost == ActionCost.HEAVY]
        
        # 2. 检查Heavy动作数量
        if len(heavy) > MAX_HEAVY_PER_CYCLE:
            # 超限：只处理前3个Heavy，其余放入延迟队列
            delayed = heavy[MAX_HEAVY_PER_CYCLE:]
            heavy = heavy[:MAX_HEAVY_PER_CYCLE]
            self.deferred_queue.extend(delayed)
        
        # 3. 检查总时间预算
        estimated_time = sum(a.estimated_ms for a in micro + normal + heavy)
        if estimated_time > MAX_TOTAL_MS_PER_CYCLE:
            # 超时：降级Heavy为Normal（跳过语义匹配，只保留结构匹配）
            for a in heavy:
                a.degrade()  # Heavy → Normal（简化计算）
        
        return micro + normal + heavy
```

**触发条件全景表（升级版）：**

| 动作 | 单体触发 | 关系触发 | 成本分级 | 降级策略 |
|------|---------|---------|---------|---------|
| 遗忘审查 | `activation < FORGET_REVIEW` | 父节点已遗忘 → 子节点衰减 | Normal | 跳过级联检查 |
| 僵尸识别 | `in=0 AND out=0 AND idle>30` | 邻居大面积僵尸 → 提前审查 | Micro | 无 |
| 冗余检测 | `WL_sim > 0.85` | `co_occurrence > 5` → 合并；`=0` → CSM候补 | Normal | 只算结构，跳过语义 |
| 概念降级 | `confidence < 0.3` | 父节点已降级 → 子节点同步降级 | Normal | 无 |
| 强制归档 | `zombie+redundant+low_conf` | 邻居已归档 → 加速归档 | Micro | 无 |
| 反事实审核 | 发散层触发 | 无 | Heavy | 超时→跳过替代路径 |
| 溯因假设 | 发散层触发 | 无 | Heavy | 超时→跳过假设生成 |
| 跨域类比 | CSM触发 | 无 | Heavy | 超时→只做结构匹配 |

**级联传播机制（传导性遗忘）：**

```python
def cascade_forget_review(node_id: str):
    """当节点被标记为遗忘审查时，触发级联衰减。"""
    node = get_node(node_id)
    if node.activation < FORGET_REVIEW:
        # 找到所有高权重出边邻居
        for edge in get_outgoing_edges(node_id, min_weight=EDGE_WEIGHT_THRESHOLD):
            neighbor = get_node(edge.target)
            # 邻居激活度衰减
            neighbor.activation *= CASCADE_DECAY_RATE
            # 如果衰减后低于阈值，触发邻居的遗忘审查
            if neighbor.activation < FORGET_REVIEW:
                queue_forget_review(neighbor.id)
```

**校准器增强（含成本效率维度）：**

```python
class ThresholdCalibrator:
    """基于 precision + recall + cost_efficiency 三维校准。"""
    
    def calibrate(self, historical_data: List[AuditRecord], performance_log: List[PerformanceRecord]):
        # 1. 单体指标校准（原设计）
        precision, recall = self._evaluate_thresholds(historical_data)
        if recall < 0.8:
            self.config.FORGET_REVIEW -= 0.2
        elif precision < 0.7:
            self.config.FORGET_REVIEW += 0.1
        
        # 2. 成本效率校准（新增）
        avg_latency_ms = sum(p.latency for p in performance_log) / len(performance_log)
        heavy_ratio = sum(1 for p in performance_log if p.heavy_count > MAX_HEAVY_PER_CYCLE) / len(performance_log)
        
        if avg_latency_ms > MAX_TOTAL_MS_PER_CYCLE * 0.8:
            # 系统响应慢：提高冗余检测阈值（减少审核量），或降低Heavy并发限制
            self.config.REDUNDANT_SIMILARITY += 0.05  # 更保守的合并策略
            self.config.MAX_HEAVY_PER_CYCLE = max(1, self.config.MAX_HEAVY_PER_CYCLE - 1)
        
        if heavy_ratio > 0.3:
            # 30%轮次触发Heavy超限：说明系统负载高，需要更严格的预算控制
            self.config.MAX_HEAVY_PER_CYCLE = max(1, self.config.MAX_HEAVY_PER_CYCLE - 1)
            self.config.MAX_TOTAL_MS_PER_CYCLE *= 0.9
        
        return self.config
```

**共现亲和度判定（区分冗余与跨域候补）：**

```python
def classify_redundancy(node_a, node_b, wl_sim: float) -> str:
    """
    基于WL相似度和共现频次，判定是冗余合并还是跨域类比候补。
    """
    co_occur = get_co_occurrence_count(node_a.id, node_b.id)
    
    if wl_sim > REDUNDANT_SIMILARITY and co_occur >= CO_OCCURRENCE_MERGE:
        return "merge"  # 高共现+高结构相似 → 合并
    elif wl_sim > REDUNDANT_SIMILARITY and co_occur == CO_OCCURRENCE_ANALOGY:
        return "analogy_candidate"  # 零共现+高结构相似 → 跨域候补
    else:
        return "distinct"  # 其他 → 保持独立
```

#### 补丁5：跨域类比语义降级（已在 rev1 中解决，此处确认）

**问题：** CSM 仅依赖 WL 结构同构测试，如果结构不匹配，系统卡住。

**解决状态：** ✅ 已在 rev1 的 CSM 三层匹配策略中解决，但 **rev4.2 补全了"判定→决策→学习"的完整认知流**。

#### 补丁5：跨域类比语义降级 + 元认知学习钩子（完整版）

**问题：** CSM 仅有"匹配→判定"两层，缺少"决策→学习"环节。失败未被利用，弱匹配未触发探索。

**方案：四层认知流（匹配 → 判定 → 决策 → 学习）**

```
CSM 完整流程：
Step 1: 匹配（三层降级链）
  WL结构 → 元角色 → 向量语义
  → 输出：三维评分 (structural, role, semantic)

Step 2: 判定（综合置信度）
  weighted_score = 0.5*structural + 0.3*role + 0.2*semantic
  → > 0.6: 强匹配
  → 0.3-0.6: 弱匹配
  → < 0.3: 不匹配

Step 3: 决策（L5元认知介入）
  强匹配 → L5拍板（确认/否决/推迟）
  弱匹配 → 存入观察队列，定期重检
  不匹配 → 存入负知识库，避免重复计算

Step 4: 学习（系统效率提升）
  负知识库 → 下次直接跳过
  观察队列 → 积累上下文后重新匹配
  L5反馈 → 调整权重参数
```

**L5 拍板决策（三选一）：**

| 决策 | 条件 | 行动 |
|------|------|------|
| **确认** | 三层证据充分，且与L1公理无冲突 | 接受类比，生成类比边，更新权重 |
| **否决** | 与L1公理冲突，或证据存在明显漏洞 | 拒绝类比，记录否决理由，降低未来权重 |
| **推迟** | 证据不足，但潜在价值高 | 要求CSM补充证据（如爬取更多文献），或等待观察队列积累 |

**元认知学习钩子（Meta-Learning Hook）：**

```python
class CSMResultHandler:
    """CSM匹配结果的后续处理：决策 + 学习。"""
    
    def handle(self, result: CSMResult) -> Action:
        score = result.weighted_score
        
        if score > 0.6:
            # 强匹配：送L5拍板
            evidence = {
                "structural_proof": result.wl_proof,
                "role_proof": result.role_alignment,
                "semantic_proof": result.vector_similarity
            }
            return L5Arbiter.review(result, evidence)
        
        elif score >= 0.3:
            # 弱匹配：存入观察队列
            observation_queue.enqueue(
                node_pair=(result.node_a, result.node_b),
                initial_score=score,
                re_check_interval=timedelta(days=30)  # 30天后重检
            )
            return Action.WAIT_AND_OBSERVE
        
        else:
            # 不匹配：存入负知识库
            negative_matches.store(
                node_pair=(result.node_a, result.node_b),
                failure_mode=self._classify_failure(result),  # "结构不同" / "角色冲突" / "语义无关"
                timestamp=now()
            )
            return Action.SKIP_FOREVER
    
    def _classify_failure(self, result: CSMResult) -> str:
        """分析失败原因，用于负知识库的精细索引。"""
        if result.structural < 0.2:
            return "structural_mismatch"
        elif result.role < 0.3:
            return "role_conflict"
        else:
            return "semantic_unrelated"
```

**数据库表（新增）：**

```sql
-- 负知识库：避免重复计算同一失败路径
CREATE TABLE negative_matches (
    id TEXT PRIMARY KEY,
    node_a_id TEXT NOT NULL,
    node_b_id TEXT NOT NULL,
    failure_mode TEXT CHECK(failure_mode IN ('structural_mismatch', 'role_conflict', 'semantic_unrelated')),
    first_failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fail_count INTEGER DEFAULT 1,
    UNIQUE(node_a_id, node_b_id)
);

-- 观察队列：弱匹配定期重检
CREATE TABLE observation_queue (
    id TEXT PRIMARY KEY,
    node_a_id TEXT NOT NULL,
    node_b_id TEXT NOT NULL,
    initial_score REAL,
    current_score REAL,
    check_count INTEGER DEFAULT 0,
    next_check_at TIMESTAMP,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'promoted', 'merged', 'archived'))
);
```

**边界失败案例表（设计验证）：**

| 匹配对 | 三层结果 | 综合置信度 | 最终判定 | 系统行动 | 设计意图 |
|--------|---------|-----------|---------|---------|---------|
| PID控制器 vs 拉格朗日力学 | WL:0.1 / Role:0.2 / Sem:0.15 | 0.13 | NOT_ISOMORPHIC | 存入negative_matches，标记"结构无关" | 防止误判，节约算力 |
| 神经网络 vs 大脑神经元 | WL:0.4 / Role:0.6 / Sem:0.85 | 0.60 | WEAKLY_ISOMORPHIC | 存入observation_queue，标记"语义类比候补" | 承认语义关联，但暂不参与结构匹配 |
| 反馈回路 vs 捕食者-猎物 | WL:0.7 / Role:0.5 / Sem:0.25 | 0.50 | STRUCTURAL_SIMILARITY | 送入CSM深入分析，检查数学同构 | 结构上找到潜在等价，主动探索 |
| 热阻 vs 金融耗散 | WL:0.6 / Role:0.8 / Sem:0.30 | 0.55 | ROLE_ALIGNED | L5拍板：确认跨域隐喻，但禁用守恒计算 | 角色对齐成立，但物理域与非物理域边界清晰 |
| 弹簧 vs 电容 | WL:0.9 / Role:0.9 / Sem:0.70 | 0.87 | HIGHLY_ISOMORPHIC | 直接接受，建立键合图标准映射 | 经典同构，无需L5审核 |

**关键设计意图：**
- **失败不是终点**：NOT_ISOMORPHIC 积累为负知识，系统越运行越高效
- **弱匹配是种子**：WEAKLY_ISOMORPHIC 进入观察期，知识增长后可能"转正"
- **L5有否决权**：强匹配也必须过L5，防止幻觉类比（如"热力学熵" vs "信息熵"的过度推广）

**问题来源：** 延拓种子晋升流程的隐藏执行隐患（异步成本、阈值绝对性、依赖链缝合、元角色衔接）。

**核心补丁：三重门审核的异步化与降级策略 + 突变信号 + 依赖链缝合 + 元角色强制分配**

| # | 补丁项 | 原因 | 方案 |
|---|--------|------|------|
| 1 | 异步审核队列 | 三重质疑（反事实/溯因/类比）同步执行成本爆炸 | 消息队列分派子任务，并行执行，等待聚合 |
| 2 | 超时降级 | 类比引擎可能死锁或LLM调用超时 | 单任务超时≤5s，失败时降级为结构匹配（跳过语义） |
| 3 | 突变信号（Anomaly Signal） | 颠覆性理论频次低（如"负质量"），但冲击极强 | 低相似度(<0.2) + 频次≥3 + 高影响力源 → 高优先级审核 |
| 4 | 依赖链缝合 | 多父锚点继承可能导致规则冲突 | 晋升时生成缝合报告，冲突点标记，优先新锚点规则 |
| 5 | 元角色强制分配 | 新锚点晋升后无法参与CSM | 继承最近父锚点的MetaRole，进入激活场 |

**具体实现：**

#### 补丁1：异步审核队列（Task Queue）

```python
class PromotionTaskQueue:
    """延拓种子晋升的三重门异步审核队列。"""
    
    def submit(self, seed: ExtensionSeed) -> str:
        job_id = generate_job_id()
        # 拆分为三个子任务，并行执行
        futures = {
            "counterfactual": executor.submit(self._run_counterfactual, seed),
            "abductive": executor.submit(self._run_abductive, seed),
            "analogy": executor.submit(self._run_analogy, seed),
        }
        
        # 设置整体超时（15秒）和单任务超时（5秒）
        try:
            results = wait_for_all(futures, timeout=15)
        except TimeoutError:
            # 超时降级：只保留已完成的任务，未完成的用默认值
            results = self._degrade_on_timeout(futures)
        
        return self._aggregate(job_id, results)
    
    def _degrade_on_timeout(self, futures):
        """降级策略：类比失败时只做结构匹配，溯因失败时跳过假设生成。"""
        return {
            "counterfactual": futures["counterfactual"].result(timeout=5) if done else DEFAULT_CRITICALITY,
            "abductive": futures["abductive"].result(timeout=5) if done else None,
            "analogy": futures["analogy"].result(timeout=5) if done else None,  # 类比失败 → 无跨域映射
        }
```

#### 补丁2：突变信号（Anomaly Signal）

```python
class AnomalyDetector:
    """检测颠覆性低频次概念。"""
    
    def check(self, seed: ExtensionSeed) -> bool:
        # 条件1：与所有锚点的相似度都极低（<0.2）
        max_sim = max(cosine_sim(seed.vector, a.embedding) for a in anchors)
        
        # 条件2：出现频次≥3（但<10，未达统计门）
        # 条件3：出现的第一篇论文是高影响力（引用量/期刊因子）
        
        if max_sim < 0.2 and seed.occurrence_count >= 3 and seed.has_high_impact_source:
            return True  # 触发高优先级审核
        return False

# 在统计门之前插入突变门
if anomaly_detector.check(seed):
    return PromotionDecision(action="priority_review", reason="anomaly_signal")
```

#### 补丁3：依赖链缝合与元角色衔接

```python
def promote_with_stitching(seed: ExtensionSeed) -> NewAnchor:
    # 1. 收集所有父锚点（可能多个）
    parent_anchors = seed.ancestor_anchors  # 向量最近邻的Top-3
    
    # 2. 收集依赖链
    inherited_rules = []
    for parent in parent_anchors:
        inherited_rules.extend(DEPENDENCY_RULES.get(parent, []))
    
    # 3. 冲突检测
    conflicts = detect_conflicts(inherited_rules)
    
    # 4. 缝合报告
    stitching_report = {
        "parents": parent_anchors,
        "inherited_rules": inherited_rules,
        "conflicts": conflicts,
        "resolution": "priority_new_anchor"  # 新锚点规则优先，冲突时回退父锚点
    }
    
    # 5. 强制分配元角色（基于最近父锚点）
    meta_role = MetaRoleRegistry.resolve(parent_anchors[0])
    store_type = MetaRoleRegistry.resolve_store_type(parent_anchors[0]) if meta_role == "store" else None
    
    return NewAnchor(
        node_id=f"ext-{seed.seed_id}",
        meta_role=meta_role,
        store_type=store_type,
        dependency_chain=stitching_report,
        enters_activation_field=True  # 立即参与CSM
    )
```

**元角色衔接规则：**

```
新锚点晋升
  ↓
强制分配元角色（继承最近父锚点）
  ├─ 父锚点是 L3-feedback → meta_role = transform
  ├─ 父锚点是 L4-thermal → meta_role = dissipate (R) / store (C)
  ├─ 父锚点是 L3-search → meta_role = source
  └─ 父锚点是 L2-graph → meta_role = junction
  ↓
进入激活场（Activation Field）
  ↓
CSM引擎可直接参与结构匹配（无需重新训练）
```

**未变更部分（确认保留）：**
- 向量延拓机制作为第一层过滤
- 分层投射作为第二层精化
- 49锚点作为硬基座，延拓种子作为软覆盖
- 统计门（频次≥10）作为硬门槛，突变门作为例外通道

---

### v6.0-UNIFIED-rev4.2（2026-06-24）

**问题来源：** Issue 5 补全 — CSM仅有"匹配→判定"，缺少"决策→学习"环节。

**核心补丁：CSM四层认知流 + 元认知学习钩子**

| # | 补丁项 | 原因 | 方案 |
|---|--------|------|------|
| 5.1 | 负知识库（negative_matches） | 同一失败路径重复计算浪费算力 | 失败模式分类存储，下次直接跳过 |
| 5.2 | 观察队列（observation_queue） | 弱匹配（WEAKLY_ISOMORPHIC）未被利用 | 30天周期重检，知识增长后可能"转正" |
| 5.3 | L5拍板三选一 | 强匹配直接接受，缺少审核 | 确认/否决/推迟，基于三层过程证据 |
| 5.4 | 边界失败案例表 | 设计文档缺少"优雅失败"的验证案例 | 5个案例覆盖：不相关/语义类比/结构相似/角色对齐/经典同构 |

**关键升级：**
- CSM从"三层降级链"升级为"四层认知流"：匹配→判定→决策→学习
- 失败不是终点：NOT_ISOMORPHIC积累为负知识，系统越运行越高效
- 弱匹配是种子：WEAKLY_ISOMORPHIC进入观察期，知识增长后可能"转正"
- L5有否决权：强匹配也必须过L5，防止幻觉类比

**数据库新增表：**
- `negative_matches`：负知识库（节点对+失败模式+失败次数）
- `observation_queue`：观察队列（节点对+初始评分+重检周期+状态）

**未变更：** rev4.1的全部内容（三层阈值、级联传播、成本调度）全部保留。

---

### v6.0-UNIFIED-rev5（2026-06-24）

**问题来源：** 外部评估指出的 3 个"隐形死穴"（L5 优先级仲裁缺失、junction 元角色过宽、CL2 锚点约束不足）。

**核心补丁：**

| # | 死穴 | 原因 | 修复方案 |
|---|------|------|---------|
| 5.1 | L5 decide() 优先级仲裁 | 预算耗尽时用户做"跨域类比查询"，HARD_CODED 无法处理 | 增加 `IntentPriority`（探索型/验证型）+ 紧急资源再分配 |
| 5.2 | junction 元角色过宽 | 0结（汇集）和 1结（分流）混为一谈，CSM 误匹配 | 拆分为 `JUNCTION_SUM` 和 `JUNCTION_SPLIT` 两个子角色 |
| 5.3 | CL2 锚点约束不足 | 非物理域锚点可能不存在，LLM 可能编造伪锚点 | 硬闸门：锚点数<3 且无物理域 → 强制降级到 CL1 |

#### 死穴1：L5 优先级仲裁（Intent Priority）

**问题：**
```python
# 旧逻辑（缺陷）
if state.divergence_budget <= 0:
    return ExecutionMode.HARD_CODED  # 无法处理跨域类比
# 如果用户正在做"探索型"查询，静默失败
```

**修复：** 增加 `IntentPriority` 维度，区分"探索型"与"验证型"。

```python
class IntentPriority(str, Enum):
    EXPLORATION = "exploration"   # 跨域类比、假设生成、发散搜索
    VERIFICATION = "verification" # 结构校验、约束检查、收敛确认

class MetaCognitiveArbiter:
    def decide(self, state: SystemState) -> ExecutionMode:
        # 新增：意图优先级判断
        if state.intent_priority == IntentPriority.EXPLORATION:
            # 探索型任务：即使预算耗尽，也尝试紧急资源再分配
            if state.divergence_budget <= 0:
                if self._emergency_reallocate(state):
                    return ExecutionMode.FAR_THINK  # 成功回收资源
                else:
                    return ExecutionMode.HARD_CODED  # 回收失败，回退
        
        # 验证型任务：严格按预算执行
        if state.divergence_budget <= 0:
            return ExecutionMode.HARD_CODED
        
        # ... 其余逻辑不变
    
    def _emergency_reallocate(self, state: SystemState) -> bool:
        """紧急资源再分配：从低优先级任务回收算力。"""
        # 1. 暂停后台遗忘审查（Normal成本，可延迟）
        paused_forgetting = self._pause_background_forgetting()
        
        # 2. 回收僵尸节点释放的内存/算力
        freed_resources = self._recycle_zombie_resources()
        
        # 3. 如果回收足够，重新分配预算
        if freed_resources >= MIN_EXPLORATION_BUDGET:
            state.divergence_budget += freed_resources
            return True
        return False
```

**关键规则：**
- 探索型任务（EXPLORATION）可以触发紧急资源再分配
- 验证型任务（VERIFICATION）严格按预算，不允许超支
- 再分配失败时，必须返回明确错误（不能静默失败）

#### 死穴2：junction 元角色拆分（JUNCTION_SUM vs JUNCTION_SPLIT）

**问题：** 旧定义 `JUNCTION: 入度≥2，出度≥1` 把 0结（汇集）和 1结（分流）混在一起。

```
控制系统：误差求和 = 0结（2入1出）→ 代数求和
键合图：机械杠杆 = 1结（1入2出）→ 等势分配
```

CSM 会把两者误认为拓扑等价，但因果关系完全相反。

**修复：拆分 junction 为两个子角色**

```python
class MetaRole(str, Enum):
    # ... 其他角色不变
    JUNCTION_SUM = "junction_sum"     # 0结：汇集/求和/比较
    JUNCTION_SPLIT = "junction_split"  # 1结：分流/分配/等势
```

| 子角色 | 结构签名 | 物理对应 | 控制对应 | 因果方向 |
|--------|---------|---------|---------|---------|
| JUNCTION_SUM | 入度≥2，出度=1 | 0结（功率守恒，代数求和） | 误差求和点 | 多→一（汇聚） |
| JUNCTION_SPLIT | 入度=1，出度≥2 | 1结（等势，流量分配） | 信号分配/并联输出 | 一→多（分流） |

**CSM 匹配规则更新：**
- JUNCTION_SUM 只能匹配 JUNCTION_SUM（不能匹配 JUNCTION_SPLIT）
- JUNCTION_SPLIT 只能匹配 JUNCTION_SPLIT
- 两者在结构签名上直接区分，避免误匹配

#### 死穴3：CL2 锚点硬闸门（防止 LLM 编造伪锚点）

**问题：** 非物理域（博弈论、叙事）的延拓种子可能不在 graph.db，LLM 可能编造锚点。

**修复：在 CL2 入口加硬闸门**

```python
class CL2FarTransferEngine:
    """CL2 远迁移思考层：硬闸门防止 LLM 编造。"""
    
    MIN_ANCHOR_COUNT = 3          # 最少锚点数
    REQUIRES_PHYSICAL_ANCHOR = True  # 必须至少有一个物理域锚点
    
    def think(self, query: str, context: Context) -> FarTransferResult:
        # 1. 从 graph.db 检索锚点
        anchors = self._retrieve_anchors(query, context)
        
        # 2. 硬闸门检查
        if len(anchors) < MIN_ANCHOR_COUNT:
            # 锚点不足 → 强制降级到 CL1
            return FarTransferResult(
                status="degraded_to_cl1",
                reason=f"insufficient_anchors: {len(anchors)} < {MIN_ANCHOR_COUNT}",
                data=None
            )
        
        if REQUIRES_PHYSICAL_ANCHOR and not any(a.is_physical for a in anchors):
            # 无物理域锚点 → 强制降级到 CL1
            return FarTransferResult(
                status="degraded_to_cl1",
                reason="no_physical_anchor_found",
                data=None
            )
        
        # 3. 通过闸门 → 允许 LLM 参与远迁移
        return self._llm_far_transfer(query, anchors, context)
```

**关键规则：**
- 锚点数 < 3 → 禁止 LLM 远迁移，降级到 CL1
- 无物理域锚点 → 禁止 LLM 远迁移，降级到 CL1
- 降级时必须返回明确原因，不静默失败

#### 锦上添花（可选，但建议实现）

**建议1：negative_matches 的 Hot-Cache**

```python
class NegativeMatchCache:
    """Bloom Filter + LRU 缓存，避免负知识库查询瓶颈。"""
    
    def __init__(self, db: Connection, capacity: int = 10000):
        self.bloom = BloomFilter(capacity=capacity, error_rate=0.01)
        self.lru = LRUCache(maxsize=1000)  # 最近24小时高频失败
        self._sync_from_db(db)  # 启动时从数据库同步
    
    def check(self, node_a: str, node_b: str) -> Optional[str]:
        """检查是否已知失败。返回失败模式，或 None（未记录）。"""
        key = f"{node_a}:{node_b}"
        
        # 1. 查 LRU 缓存（内存，O(1)）
        if key in self.lru:
            return self.lru[key]
        
        # 2. 查 Bloom Filter（内存，O(1)，可能误判）
        if not self.bloom.contains(key):
            return None  # 肯定不在负知识库
        
        # 3. 查数据库（精确确认）
        result = self.db.query("SELECT failure_mode FROM negative_matches WHERE ...")
        if result:
            self.lru[key] = result  # 加入缓存
            return result
        
        return None  # Bloom Filter 误判
```

**建议2：ObservationQueue 的置信度上升激励**

```python
class ObservationQueue:
    """弱匹配队列，支持置信度上升提前触发。"""
    
    def check_acceleration(self, item: QueueItem, current_score: float) -> bool:
        """
        如果置信度爬升速度超过阈值，提前触发重检。
        """
        score_delta = current_score - item.initial_score
        time_elapsed = now() - item.enqueued_at
        
        # 爬升速度 = 置信度提升 / 时间
        climb_rate = score_delta / time_elapsed.days
        
        # 如果爬升速度 > 0.05/天，提前触发（不需要等30天）
        if climb_rate > 0.05:
            return True  # 提前触发重检
        
        # 否则按固定周期（30天）
        return time_elapsed >= timedelta(days=30)
```

**未变更：** rev4.2的全部内容（四层认知流、负知识库、观察队列）全部保留。rev5 是在其上的死穴修补。

---

## 附录 D：SLP 视角下的 NLP 优化方向（v6.1-OPT）

> **来源：** 基于 Jurafsky & Martin, *Speech and Language Processing* (3rd ed.) 的系统审视
> **状态：** 设计优化提案，待 Phase C5+ 评估实施
> **日期：** 2026-06-30

### D.1 预处理层：多级 Tokenization（Ch.2）

**当前状态：** 论文 LaTeX 源码进入清洗模块时，公式、引用、图表 caption 的边界模糊。希腊字母统一已实现，但数学表达式的结构化解析不足。

**SLP 启示：** Tokenization 不是一次性操作，而是多级粒度决策。

**优化方向：**
1. **多级 tokenization 管道：**
   - `word-level`：正文文本（已有）
   - `symbol-level`：公式变量（新增：将 `$\\alpha = \\beta + \\gamma$` 转为符号树而非纯文本）
   - `citation-level`：引用上下文（新增：解析 `\\cite{...}` 的共现网络）
   - `figure-level`：图表 caption 与正文的指代链接
2. **引理还原（lemmatization）：** 在 FuzzyMatcher 基础上，对学术动词做词形还原（"controlled" → "control"），减少词汇稀疏性。

**关联模块：** Layer 1 入口解构层、`lcortex/layer1/keyword_extractor.py`

---

### D.2 语义表示层：领域自适应嵌入（Ch.6-7, Ch.10）

**当前状态：** SemanticFilter 使用 all-MiniLM-L6-v2（通用模型），对学术文本的领域适配不足。

**SLP 启示：** 静态词向量（Word2Vec/GloVe）vs. 动态上下文表示（BERT 族）的 trade-off——静态快但歧义多，动态准但计算重。

**优化方向：**
1. **领域自适应嵌入（高优先级）：**
   - 基线方案：替换 MiniLM 为 SciBERT / academic BERT
   - 理由：学术术语分布（如 "Fourier transform" 作为整体概念）与通用文本差异显著
   - 回退：SciBERT 不可用时，保留 MiniLM + 领域词典加权
2. **多粒度语义索引（中优先级）：**
   - 词级：TF-IDF 快速过滤（已有）
   - 句级：sentence-transformers 语义匹配（已有）
   - 文档级：增加文档向量（doc2vec 或 mean-pooled BERT），用于跨论文宏观主题聚类
3. **上下文消歧（低优先级，预留）：**
   - "control" 在控制论文中是核心概念，在医学论文中是对照组
   - 方案：领域标签做嵌入加权，或引入轻量词义消歧（WordNet 风格）

**关联模块：** `lcortex/divergence/semantic_filter.py`、`CSMCognitiveFlow._step3_semantic_distance()`

---

### D.3 句法结构层：依存分析与谓词-论元（Ch.17-18）

**当前状态：** WL 子树同构比较图拓扑，但缺少对句法结构的显式利用。论文句子有强烈的谓词-论元结构。

**SLP 启示：** 依存分析（Dependency Parsing）揭示"谁对谁做了什么"。

**优化方向：**
1. **谓词-论元抽取（中优先级）：**
   - 对论文摘要/结论做依存分析，提取 `(方法, 作用于, 对象)` 三元组
   - 示例："FxLMS reduces vibration" → `(FxLMS, reduces, vibration)`
   - 输出：直接写入 graph.db 作为结构化边，替代部分关键词匹配
2. **结构签名升级（低优先级）：**
   - 当前 WL 签名基于图拓扑
   - 叠加句法签名：将依存树编码为 WL 颜色，形成"语义-句法双层签名"
   - 两个概念即使图拓扑不同，若句法角色相似（都是"方法-改善-指标"结构），也应提高匹配度

**关联模块：** `lcortex/inference/divergent/wl_subtree_isomorphism.py`、`AbductiveEngine`

---

### D.4 语义角色标注：SRL 框架（Ch.22）

**当前状态：** AbductiveEngine 的关键词搜索缺少对句子深层语义框架的理解。

**SLP 启示：** SRL 将句子映射到"谁对谁用什么方法做了什么"的框架。

**优化方向：**
1. **学术 SRL 框架模板（中优先级）：**
   - `PREDICATE`：方法/算法
   - `AGENT`：研究者/系统
   - `THEME`：被处理对象（信号、材料）
   - `INSTRUMENT`：工具（软件、设备）
   - `RESULT`：输出指标（dB、误差）
2. **跨论文对齐：**
   - 比较两篇论文的假设时，先对齐 SRL 框架
   - 若 `PREDICATE` 和 `THEME` 对齐但 `INSTRUMENT` 不同 → 产生"工具替换"型假设
   - 比纯文本匹配更有结构感，直接支持 CL2 跨域类比

**关联模块：** `lcortex/divergence/abductive.py`、`lcortex/inference/divergent/cl2_far_transfer.py`

---

### D.5 指代消解：概念一致性（Ch.21）

**当前状态：** 论文中大量指代（"该方法"、"上述结果"、"Fig. 3 所示"）在解析时被当作独立概念。

**SLP 启示：** 指代链（coreference chain）将多个 mention 链接到同一实体。

**优化方向：**
1. **指代消解预处理（高优先级）：**
   - 在文本进入 L1-L4 之前，先做指代消解
   - "the proposed algorithm" → 链接到具体算法名称（如 "FxLMS"）
   - 直接减少概念碎片化，提升 L1-L4 输入质量
2. **跨句图构建：**
   - 消解后的指代链作为图的额外边
   - 强化概念的跨句一致性

**关联模块：** Layer 1 入口解构层、`lcortex/persistence/graph.db`

---

### D.6 信息抽取：关系模板（Ch.19）

**当前状态：** 系统主要做匹配和类比，但缺少对论文中显式关系的抽取。

**SLP 启示：** 关系抽取（Relation Extraction）从文本中提取结构化关系。

**优化方向：**
1. **预定义学术关系模板（中优先级）：**
   - `CAUSE(原因, 结果)`："A leads to B"
   - `COMPARE(对象A, 对象B)`："A outperforms B"
   - `APPLY(方法, 领域)`："A is applied to B"
   - `IMPROVE(方法, 指标, 幅度)`："A improves B by X%"
2. **模式 + 神经网络混合抽取：**
   - 高频模式用规则（快）
   - 长尾用 LLM（准）
   - 抽取结果直接写入 graph.db，替代部分手动构建的键合图

**关联模块：** `lcortex/persistence/convergent_store.py`、`lcortex/layer1/l0l4_bridge.py`

---

### D.7 语言模型先验：困惑度评估（Ch.3, Ch.10）

**当前状态：** 系统没有利用预训练语言模型的概率先验来评估假设合理性。

**SLP 启示：** 语言模型的困惑度（perplexity）反映序列的"自然度"。

**优化方向：**
1. **假设合理性评分（低优先级，预留）：**
   - 对生成的假设（如 "FxLMS 应用于热传导控制"），用领域语言模型计算困惑度
   - 若困惑度极高 → 该假设在学术文本中极少出现，可能不合理
2. **反事实验证的 LLM 增强：**
   - CounterfactualEngine 当前做删边检查
   - 叠加 LLM 评估：删除某前提后的结论，让 LLM 判断逻辑连贯性（作为额外置信度来源）

**关联模块：** `lcortex/divergence/counterfactual.py`、`lcortex/inference/convergent/cl3_questioning.py`

---

### D.8 机器翻译对齐：细粒度概念对齐（Ch.13）

**当前状态：** 跨域类比（CL2）寻找不同领域的同构结构，但"对齐"机制较粗（图级别）。

**SLP 启示：** IBM 模型、注意力机制中的对齐（alignment）思想。

**优化方向：**
1. **细粒度概念对齐（低优先级）：**
   - 当前 WL 同构是图级别的
   - 借鉴 MT 词对齐：在两个域的图之间，找到最细粒度的节点对齐（如 "PID controller" ↔ "thermostat"）
   - 生成更精确的类比映射，而非全图匹配
2. **注意力权重解释（预留）：**
   - 若用 Transformer 做跨域编码，其注意力权重可直接揭示"哪些概念在对齐时被重点关注"
   - 增强可解释性

**关联模块：** `lcortex/inference/divergent/wl_subtree_isomorphism.py`、`lcortex/divergence/csm_cognitive_flow.py`

---

### D.9 对话系统：CL 层 POMDP 策略学习（Ch.24）

**当前状态：** CL0-CL4 的控制流设计类似对话状态跟踪，但缺少显式的"对话策略"学习。

**SLP 启示：** 对话系统 = 状态跟踪 + 策略学习 + 自然语言生成。

**优化方向：**
1. **POMDP 策略学习（低优先级，长期）：**
   - 将 CL 层决策建模为部分可观察马尔可夫决策过程
   - 状态 = 当前证据 + 历史决策
   - 动作 = {硬编码, CL1, CL2, CL3, LLM}
   - 奖励 = 决策准确率 - 计算成本
   - 比当前阈值规则更具适应性
2. **历史依赖编码：**
   - 当前 CL 层 mostly stateless
   - 引入对话历史编码（类似对话系统的 context vector）
   - 让后续决策依赖前面的质疑和修正

**关联模块：** `lcortex/inference/convergent/pipeline.py`、`lcortex/inference/convergent/state.py`

---

### D.10 优先级排序与实施建议

| SLP 章节 | 优化项 | 成本 | 影响 | 建议 Phase |
|---|---|---|---|---|
| Ch.2 | 多级 tokenization | 低 | 数据质量提升 | Phase C5 |
| Ch.21 | 指代消解 | 中 | 概念一致性 | Phase C5 |
| Ch.10 | 领域自适应嵌入（SciBERT） | 低 | 语义匹配精度 | Phase C5 |
| Ch.22 | SRL 框架抽取 | 中 | 假设生成结构化 | Phase C6 |
| Ch.19 | 关系抽取模板 | 中 | 图谱自动构建 | Phase C6 |
| Ch.13 | 细粒度概念对齐 | 高 | 跨域类比精度 | Phase C7+ |
| Ch.24 | CL 层 POMDP 策略学习 | 高 | 控制流自适应 | Phase C7+ |

**最优先三项（Phase C5 可落地）：**
1. **指代消解** — 低成本解决概念碎片化，直接提升 L1-L4 输入质量
2. **领域自适应嵌入** — 替换通用 MiniLM，学术语义匹配上限更高
3. **多级 tokenization** — 公式/引用的结构化解析，减少噪声输入

**与现有架构的兼容性：**
- 所有优化均为"叠加式"，不破坏现有 L0-L5 层级结构
- 指代消解和 tokenization 作为 Layer 1 的预处理插件
- SciBERT 作为 SemanticFilter 的可选后端
- SRL 和关系抽取作为 Layer 2 的增强模块
- 与"数学接驳口"设计哲学一致：提供可解析的结构，不引入黑盒依赖

---

## 附录 E：非论文内容摄取的架构适配方案（v6.1-OPT）

> **问题来源：** 当前系统假设输入为论文结构（摘要、方法、结论、引用链），非论文内容（行业报告、新闻、自媒体、评论、专利、标准）在这些维度上缺失或变形
> **状态：** 设计优化提案，待 Phase C5+ 评估实施
> **日期：** 2026-06-30

### E.1 非论文内容类型谱系

| 类型 | 结构度 | 术语密度 | 噪声水平 | 可信度要求 |
|---|---|---|---|---|
| 行业技术报告 | 中（有目录、章节） | 中高 | 低 | 高（决策依据） |
| 新闻报道 | 低（倒金字塔） | 中 | 中 | 中（事实核查） |
| 自媒体/博客 | 低 | 低-中 | 高 | 低（观点过滤） |
| 社交媒体评论 | 极低 | 低 | 极高 | 极低（情绪为主） |
| 专利文档 | 高（法律格式） | 极高 | 低 | 高（侵权判定） |
| 标准/规范 | 高（条款化） | 高 | 低 | 极高（合规依据） |

**核心判断：** 不是所有非论文内容都值得进入深层认知流。需要**准入筛子**做资源分配。

---

### E.2 各层级的适配改造

#### E.2.1 Layer 1：入口解构层（改动最大）

**当前问题：** `keyword_extractor` 假设文本有学术段落结构，TF-IDF 在短文本上失效。

**改造方案：**

**a) 内容类型自动识别器**
```python
class ContentTypeClassifier:
    """输入文本 → 类型标签 + 可信度"""
    def classify(self, text: str) -> ContentType:
        # 特征：平均句长、术语密度、引用模式、URL/emoji 频率
        if citation_density > 0.1: return ContentType.ACADEMIC
        if emoji_count > 0.05: return ContentType.SOCIAL
        if section_pattern_match: return ContentType.REPORT
        ...
```

**b) 类型专属的清洗管道**
- **行业报告：** 保留目录结构作为语义段落边界，提取"执行摘要"作为高置信度区域
- **新闻报道：** 识别"倒金字塔"结构，首段权重 ×3，后续段落逐层降权
- **自媒体：** 激进过滤：emoji 替换为情绪标签，URL 替换为域名实体，删除营销话术模板
- **评论：** 极简处理：只提取显式评价对象 + 极性，不做深层假设生成

**c) 短文本聚合（针对评论/推文）**
单个评论太短，但同主题下的评论聚合后形成"分布式语义"。
- 先按主题聚类（如某产品下的所有评论）
- 提取共识性陈述（高频出现的观点）
- 将聚合后的"共识摘要"作为认知流的输入单元

**关联模块：** `lcortex/layer1/keyword_extractor.py`、`lcortex/layer1/text_cleaner.py`

---

#### E.2.2 Layer 2：形式化转译层（改动中）

**当前问题：** 键合图、Petri 网、系统动力学等元框架假设物理/工程系统。非论文内容常涉及经济、社会、心理过程。

**改造方案：**

**a) 元框架扩展**
```python
META_FRAMEWORKS = {
    # 已有
    "physical": BondGraphParser,
    "social": SystemDynamicsParser,
    "logic": PetriNetParser,
    # 新增
    "narrative": NarrativeSchemaParser,   # 叙事 schema：角色-事件-结果
    "argument": ArgumentationParser,     # 论证结构：前提-推论-结论
    "sentiment": SentimentFrameParser,    # 情绪框架：对象-极性-强度
    "economic": ValueChainParser,        # 价值链：投入-转化-产出
}
```

**b) 弱形式化策略**
论文追求"强形式化"（精确方程）。非论文内容需要"弱形式化"：
- 不追求数学公式，而是**结构化命题**
- 示例："这款芯片发热严重" → `(芯片, 属性:发热, 程度:严重, 来源:用户评论)`
- 这种"轻量三元组"足以进入 L1-L4 的匹配流程

**c) 引用链替代（针对无引用内容）**
非论文没有 `\cite{}`，但有：
- 超链接 → 提取域名作为"来源实体"
- "据XX报道" → 提取报道机构作为引用代理
- 隐式引用（"众所周知"）→ 标记为 UNSOURCED，置信度降级

**关联模块：** `lcortex/layer2/meta_roles.py`、`lcortex/layer2/formalization_engine.py`

---

#### E.2.3 L0-L4：公理层（改动中）

**当前问题：** L0-L4 的公理主要是物理、数学、方法论约束。非论文内容需要社会学、经济学、传播学的约束。

**改造方案：**

**a) 领域公理的动态加载**
当前 L0-L4 是静态的。非论文内容需要**按需加载领域公理**：
- 财经报道 → 加载"会计恒等式"、"市场有效性"等公理
- 医疗自媒体 → 加载"循证医学层级"、"药物副作用"等公理
- 法律文本 → 加载"无罪推定"、"合同约束力"等公理
- 加载机制：基于 `ContentTypeClassifier` 的输出，从公理数据库动态 SELECT

**b) 可信度公理（新增 L0 节点）**
非论文内容需要显式的"来源可信度"评估：
```python
class CredibilityAxiom:
    """来源类型 → 基础可信度"""
    ACADEMIC_PEER_REVIEWED = 0.95
    INDUSTRY_REPORT = 0.80
    ESTABLISHED_MEDIA = 0.70
    INDEPENDENT_BLOG = 0.50
    SOCIAL_MEDIA = 0.30
    UNKNOWN = 0.10
```

这个可信度作为乘数进入 L5 的置信度计算。

**关联模块：** `lcortex/layer1/l0l4_bridge.py`、`lcortex/inference/convergent/axiom_verifier.py`

---

#### E.2.4 Layer 3：双核心引擎（改动小）

**改造方案：**

**a) 发散层（Divergent Core）**
- 反事实引擎：对非论文内容，"删边"操作更保守——因为非论文的因果关系往往是相关性
- 溯因引擎：允许"弱假设"存在。例如从评论"电池不耐用"溯因到"电池容量衰减"，不需要严格物理推导

**b) 收敛层（Convergent Core）**
- 质疑层（CL3）对非论文内容更激进：自媒体内容默认不信任，直到交叉验证
- 正向演绎（CL0）对非论文内容可能失效——逻辑链条不严密时应降级为"归纳支持"而非"演绎证明"

**关联模块：** `lcortex/divergence/counterfactual.py`、`lcortex/inference/convergent/cl3_questioning.py`

---

#### E.2.5 Layer 4-5：协同与拍板（改动小）

**改造方案：**

**a) 内容类型权重进入 L5 决策**
```python
class MetaCognitiveArbiter:
    def decide(self, state):
        # 新增：内容类型影响置信度阈值
        if state.content_type == ContentType.SOCIAL_MEDIA:
            min_confidence = 0.80  # 社交媒体需要更高置信度才通过
        elif state.content_type == ContentType.ACADEMIC:
            min_confidence = 0.60  # 论文可以容忍更多不确定性
```

**b) 跨类型类比的风险控制**
非论文内容进入类比流程时，需要额外的"类型距离"惩罚：
- 论文 ↔ 论文：类型距离 0，类比正常
- 论文 ↔ 行业报告：类型距离 1，类比降级
- 论文 ↔ 评论：类型距离 3，类比拒绝或强制人工审核

**关联模块：** `lcortex/analysis/meta_cognitive_arbiter.py`

---

### E.3 新增模块：内容准入筛子（Content Admission Filter）

建议在 Layer 1 之前增加一个轻量筛子：

```python
class ContentAdmissionFilter:
    """
    决定是否让内容进入认知流。
    
    不是 censorship，而是资源分配：
    - 高价值内容 → 全层激活
    - 低价值内容 → 浅层处理或丢弃
    """
    
    def admit(self, text: str, source_type: str) -> AdmissionDecision:
        # 1. 信息密度检查
        info_density = self._compute_info_density(text)
        if info_density < 0.1:  # 如纯情绪表达 "太棒了！"
            return AdmissionDecision.SHALLOW_ONLY  # 只做情绪分析
        
        # 2. 结构可解析性
        parseability = self._estimate_parseability(text)
        if parseability < 0.3:
            return AdmissionDecision.AGGREGATE_FIRST  # 需要聚合多篇
        
        # 3. 来源可信度
        base_credibility = CREDIBILITY_AXIOMS.get(source_type, 0.1)
        if base_credibility < 0.2:
            return AdmissionDecision.REJECT  # 垃圾信息直接丢弃
        
        return AdmissionDecision.FULL_PIPELINE
```

**四种决策：**
- `FULL_PIPELINE`：全层激活（论文、高质量报告、专利、标准）
- `SHALLOW_ONLY`：浅层处理（提取关键词、情感、主题，不入持久化层）
- `AGGREGATE_FIRST`：先聚合再处理（评论、推文）
- `REJECT`：直接丢弃（垃圾信息、纯广告）

**关联模块：** 新建 `lcortex/layer1/admission_filter.py`

---

### E.4 实施优先级

| 优化项 | 成本 | 影响 | 建议 Phase |
|---|---|---|---|
| 内容类型识别器 | 低 | 决定后续处理路径 | C5 |
| 准入筛子 | 低 | 防止垃圾占用算力 | C5 |
| Layer 1 类型专属清洗 | 中 | 非论文输入质量 | C5 |
| 元框架扩展（叙事/论证） | 中 | 弱形式化覆盖 | C6 |
| L0-L4 动态公理加载 | 中 | 跨领域可信度 | C6 |
| 短文本聚合器 | 中 | 评论/社交媒体 | C6 |
| 可信度公理体系 | 低 | 来源质量评估 | C5 |

---

### E.5 核心原则

**不是所有内容都值得深度处理。**

论文的深层价值在于其结构化的知识贡献。非论文内容的价值往往在于**时效性、观点多样性、市场情绪**——这些用浅层处理（情感分析、主题聚类、来源追踪）即可满足需求，不需要动用 WL 同构和反事实引擎。

深层认知流应该留给**经过准入筛子、结构可解析、来源可信**的内容。其余内容走"浅层快速通道"——提取关键信息，不入持久化层，不生成假设。

这个原则本身也是一种"奥卡姆剃刀"：处理深度与内容价值成正比。
