# Literature Cortex v5.2d 设计方案：全领域粗匹配器 (Universal Coarse Matcher)

> **文档编号:** LC-DESIGN-v5.2d
> **版本:** v5.2d-DRAFT
> **状态:** 📋 DRAFT
> **完成度:** 50%（框架设计完成，具体映射规则待逐项拆解）
> **日期:** 2026-06-17
> **依赖:** v5.2c 形式化转译引擎（形式化转译模块作为核心实现层）
> **注册表:** 参见 `DESIGN-REGISTRY.md` 第 #design-文档清单 节
> **核心目标:** 覆盖全领域20+标准化形式化语言，实现85%零LLM、10%轻规则、5%LLM兜底的分层转译

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-17 | v5.2d-DRAFT | 初始设计，整合全领域20+形式化语言标准 |

---

## 1. 核心原则

**最小化LLM依赖的三层转译策略：**

| 层级 | 覆盖率 | LLM介入 | 精度 | 适用场景 |
|------|--------|---------|------|---------|
| **Layer 1: 领域原生标准** | 85% | **零LLM** | 100% | 理工、工程、生命科学、系统类 |
| **Layer 2: 通用元框架** | 10% | **轻规则** | 90% | 新兴领域、交叉领域、无标准领域 |
| **Layer 3: LLM兜底** | 5% | **LLM提取+规则校验** | 70% | 纯人文、艺术、小众边缘领域 |

**关键认知：** 绝大多数知识领域已有成熟的「专属形式化语言」，这些语言经过数十年学界/工业界验证，可直接作为「领域原生转译模板」。LLM只应承担「非结构化文本→形式化语言」的入口转译，而非直接参与结构判定。

---

## 2. 全领域形式化语言映射总表

### 2.1 数理基础层（全领域通用，跨域同构的底层依据）

| 形式化语言 | 核心本质 | 覆盖领域 | 五元组映射 | 成熟度 | 标准文献 |
|-----------|---------|---------|-----------|--------|---------|
| **范畴论 (Category Theory)** | 对象+态射+函子的跨域结构映射 | 所有数学化领域 | 对象=输入输出，态射=函数变换，函子=跨层级嵌套，自然变换=同构关系 | 70年纯数学基础 | Mac Lane, Categories for the Working Mathematician |
| **抽象重写系统 (ARS)** | 项集合+重写规则的通用演化 | 数学证明、化学、生物演化、游戏规则 | 项=状态/数据，重写规则=子函数，规约路径=调用图，正规式=输出 | 理论CS基础 | Baader & Nipkow, Term Rewriting and All That |
| **类型论+柯里-霍华德同构** | 逻辑命题↔程序类型↔数学证明的三方统一 | 逻辑学、CS、形式化验证 | 类型=输入输出约束，函数=证明步骤，类型签名=命题，组合=推导 | 证明助手底层 | Pierce, Types and Programming Languages |

### 2.2 物理与工程领域

| 形式化语言 | 核心本质 | 覆盖领域 | 五元组映射 | 成熟度 | 标准文献 |
|-----------|---------|---------|-----------|--------|---------|
| **键合图 (Bond Graph)** | 势变量×流变量=功率，5类元件+2类节点 | 多物理场耦合、机电一体化、热工 | 元件=子函数，0/1节点=汇流/分流，功率键=数据流 | 60年工业标准 | Paynter, Analysis and Design of Engineering Systems (1961) |
| **端口哈密顿系统 (Port-Hamiltonian)** | 能量端口+互联结构+哈密顿函数 | 复杂机电、机器人、电网 | 端口=输入输出，互联=调用，哈密顿=状态约束 | 控制理论前沿 | van der Schaft, L2-Gain and Passivity Techniques |
| **信号流图 (SFG)** | 节点=信号，支路=传输函数，梅森增益 | 控制工程、电路、信号处理、机械振动 | 节点=中间变量，支路=子函数，通路/反馈=调用图 | 经典控制标准 | Mason, Feedback Theory—Some Properties of Signal Flow Graphs (1953) |
| **功能基 (Functional Basis)** | 动词+流的二元组，8大类动词+3大类流 | 工程设计、TRIZ、仿生设计 | 动词=功能函数，流=输入输出，层级=函数嵌套 | NIST标准 | Hirtz et al., A Functional Basis for Engineering Design (2002) |

### 2.3 计算机与信息科学领域

| 形式化语言 | 核心本质 | 覆盖领域 | 五元组映射 | 成熟度 | 标准文献 |
|-----------|---------|---------|-----------|--------|---------|
| **进程代数 (π-演算/CCS)** | 进程+通道+同步交互 | 通信协议、分布式系统、多智能体 | 进程=子函数，通道=接口，交互=调用，嵌套=函数嵌套 | 理论CS经典 | Milner, Communicating and Mobile Systems: The π-Calculus |
| **Petri网** | 库所+变迁+流关系 | 工作流、生产系统、业务流程、基因调控 | 库所=状态/输入输出，变迁=子函数，托肯=数据流，可达图=调用图 | 60年/ISO标准 | Reisig, Petri Nets: An Introduction |
| **信息论信道模型** | 信源→编码→信道→解码→信宿 | 通信、信号处理、生物信息、神经科学 | 信源/信宿=输入输出，编解码=子函数，信道=传输链路，噪声=约束 | 信息论基础 | Shannon, A Mathematical Theory of Communication (1948) |
| **抽象语法树 (AST)** | 程序结构的树形表示 | 所有编程语言、编译器、代码分析 | 节点=表达式/语句，边=嵌套/调用关系，叶节点=输入/输出 | 编译器基础 | Aho et al., Compilers: Principles, Techniques, and Tools |
| **控制流图 (CFG)** | 程序执行路径的图表示 | 程序分析、优化、验证 | 基本块=子函数，边=跳转/调用，入口/出口=输入输出 | 程序分析标准 | Allen, Control Flow Analysis (1970) |

### 2.4 生命科学与化学领域

| 形式化语言 | 核心本质 | 覆盖领域 | 五元组映射 | 成熟度 | 标准文献 |
|-----------|---------|---------|-----------|--------|---------|
| **SBML** | 系统生物学标准标记语言 | 代谢网络、信号通路、基因调控 | 物种=输入输出物质，反应=子函数，隔间=层级模块，反应规则=函数逻辑 | 国际标准/90%+覆盖率 | Hucka et al., The Systems Biology Markup Language (2003) |
| **化学反应网络 (CRN)** | 反应式+物质浓度的图灵完备模型 | 化学动力学、合成生物学、代谢工程 | 反应物/产物=输入输出，速率方程=子函数，守恒律=约束 | 物理化学基础 | Feinberg, Chemical Reaction Network Theory |
| **基因本体 (GO)** | 生物功能标准词汇表，三层结构 | 分子生物学、遗传学、生物信息学 | 术语=功能函数，层级=函数嵌套，注释=输入输出约束 | 生命科学核心标准 | Ashburner et al., Gene Ontology: Tool for the Unification of Biology (2000) |
| **CellML** | 细胞/生理级建模标准 | 生理学、生物力学、药理学、医工交叉 | 组件=子函数，变量=输入输出，连接=函数调用 | 国际生理组学联盟标准 | Cuellar et al., An Overview of CellML 1.1 (2003) |
| **BioPAX** | 生物通路数据交换标准 | 信号转导、代谢、基因调控通路 | 实体=输入输出，交互=子函数，转换=调用关系 | 通路数据库标准 | Demir et al., The BioPAX Community Standard (2010) |

### 2.5 系统工程与工业制造领域

| 形式化语言 | 核心本质 | 覆盖领域 | 五元组映射 | 成熟度 | 标准文献 |
|-----------|---------|---------|-----------|--------|---------|
| **SysML** | 系统工程标准建模语言，UML扩展 | 复杂装备、航空航天、汽车、机器人 | 块=子函数，端口=输入输出，关联=调用图，约束块=约束 | OMG国际标准 | Friedenthal et al., A Practical Guide to SysML (2014) |
| **IDEF0** | 功能建模：输入-输出-控制-机制 | 工业制造、企业管理、军事系统 | 活动框=子函数，箭头=输入输出流，分解=函数嵌套 | 美国国防部标准 | Mayer et al., IDEF0 Function Modeling |
| **IDEF3** | 过程流建模：事件时序与逻辑 | 业务流程、制造过程 | 单元=子函数，链接=调用关系，交汇点=约束逻辑 | 美国国防部标准 | Menzel & Mayer, IDEF3 Process Description Capture Method |
| **STEP (EXPRESS)** | 产品数据交换标准，ISO 10303 | 机械制造、CAD/CAM、工业数字化 | 实体=组件函数，属性=参数，继承/聚合=函数嵌套 | ISO国际标准 | Schenck & Wilson, Information Modeling: The EXPRESS Way |
| **Modelica** | 面向对象、非因果、基于方程的多领域建模 | 机械、电气、液压、热控、控制算法 | 模型=子函数，连接器=输入输出，方程=约束，层级=嵌套 | 工业级仿真标准 | Fritzson, Principles of Object-Oriented Modeling and Simulation with Modelica |
| **PLCopen/XML** | 工业控制程序的标准化交换格式 | 自动化、PLC控制、工业软件 | 功能块=子函数，输入/输出变量=接口，执行顺序=调用图 | IEC 61131-3标准 | PLCopen Technical Committee, XML Formats for IEC 61131-3 |

### 2.6 社会经济与复杂系统领域

| 形式化语言 | 核心本质 | 覆盖领域 | 五元组映射 | 成熟度 | 标准文献 |
|-----------|---------|---------|-----------|--------|---------|
| **系统动力学 (System Dynamics)** | 存量-流量-反馈回路 | 宏观经济、人口、生态、企业管理、公共政策 | 存量=状态变量，流量=变化函数，反馈=闭环调用，表函数=约束 | 60年实践 | Forrester, Industrial Dynamics (1961) |
| **扩展式博弈 (Extensive-form Game)** | 决策树：行动顺序、信息、收益 | 经济学、博弈论、多智能体、国际关系 | 节点=决策状态，分支=子函数，收益=输出，信息集=约束 | 博弈论标准 | Osborne & Rubinstein, A Course in Game Theory |
| **ABM + ODD协议** | 基于主体建模的标准化描述 | 生态、社会、经济、交通、流行病 | 主体=子函数，行为规则=函数逻辑，环境交互=调用关系 | 计算社会科学标准 | Grimm et al., The ODD Protocol (2006) |
| **投入产出分析 (I-O Model)** | 部门间经济流量的矩阵模型 | 宏观经济、产业关联、供应链 | 部门=子函数，投入/产出=接口，技术系数=约束矩阵 | 经济学标准 | Leontief, Input-Output Economics |
| **社会网络分析 (SNA)** | 节点+关系+中心性/聚类度量 | 社会结构、组织分析、信息传播 | 节点=实体，边=关系/调用，路径=调用链，指标=约束评估 | 社会学标准 | Wasserman & Faust, Social Network Analysis (1994) |

### 2.7 认知、语言与人文领域

| 形式化语言 | 核心本质 | 覆盖领域 | 五元组映射 | 成熟度 | 标准文献 |
|-----------|---------|---------|-----------|--------|---------|
| **形式文法 (乔姆斯基层级)** | 正则/上下文无关/上下文相关/递归可枚举 | 自然语言、编程语言、逻辑、音乐 | 终结符/非终结符=输入输出，产生式=子函数，推导树=调用树 | 理论语言学基础 | Chomsky, Syntactic Structures (1957) |
| **ACT-R认知架构** | 感知-运动-记忆-产生式规则的模块化认知 | 认知心理学、人机交互、教育心理 | 模块=子函数，产生式=函数逻辑，缓冲=状态变量，目标=约束 | 40年实验验证 | Anderson, ACT-R: A Cognitive Architecture (1993) |
| **概念图 (Conceptual Graphs)** | 概念+关系+类型的图形逻辑 | 语义表示、知识工程、自然语言理解 | 概念=节点/输入输出，关系=边/调用，类型=约束 | 知识表示标准 | Sowa, Conceptual Structures (1984) |
| **本体工程 (OWL/RDF)** | 类-属性-个体的语义网络 | 知识图谱、语义网、生物本体 | 类=函数类型，属性=接口，个体=实例，公理=约束 | W3C标准 | OWL 2 Web Ontology Language Primer |
| **叙事结构 (Propp/Quest模型)** | 角色+功能+情节的叙事形式化 | 文学、影视、游戏叙事、文化传播 | 角色=功能函数，情节=调用序列，情境=约束条件 | 叙事学标准 | Propp, Morphology of the Folktale (1928) |

### 2.8 通用跨域元框架（所有领域通用的转译规范）

| 形式化语言 | 核心本质 | 覆盖领域 | 五元组映射 | 成熟度 | 标准文献 |
|-----------|---------|---------|-----------|--------|---------|
| **DEVS** | 原子模型+耦合模型的层级嵌套 | 所有离散事件系统，跨全领域 | 原子模型=基础函数，耦合模型=嵌套函数，端口=接口，事件调度=调用时序 | 建模与仿真国际标准 | Zeigler et al., Theory of Modeling and Simulation (2000) |
| **MDA + QVT** | 平台无关模型→平台相关模型的分层转换 | 所有建模领域的转译流程 | PIM=通用函数树，PSM=领域原生形式化，转换规则=映射函数 | OMG工业标准 | OMG, MDA Guide and QVT Specification |
| **SysML v2 + KerML** | 下一代系统工程语言，更严格的语义基础 | 所有工程领域，语义更严格 | 与SysML映射一致，但增加了形式化语义约束 | OMG最新标准 | OMG, SysML v2 Specification |
| **MOF (Meta-Object Facility)** | 元建模的元模型，定义所有模型的语言 | 所有建模语言本身的定义 | 元类=函数类型，元属性=接口，元关联=调用关系 | OMG标准 | OMG, MOF Core Specification |

---

## 3. 三层转译架构

```
输入：任意知识节点（自然语言描述/论文/专利/教材段落）
  ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: 领域识别与原生标准匹配（85%覆盖，零LLM）                    │
│                                                                     │
│  Step 1: 关键词/特征识别领域                                         │
│    - 匹配规则：标题/关键词/参考文献 → 领域分类器                       │
│    - 示例：含"键合图""功率守恒"→ Bond Graph                          │
│            含"信号流""梅森增益"→ SFG                                │
│            含"物种""反应""代谢"→ SBML                                │
│                                                                     │
│  Step 2: 套用领域原生模板                                            │
│    - 加载对应形式化语言的元模型                                       │
│    - 将节点内容按模板字段填入                                         │
│    - 示例：Bond Graph 模板 → 识别势变量/流变量/元件类型               │
│                                                                     │
│  Step 3: 输出领域原生形式化结构                                       │
│    - 键合图JSON / 信号流图JSON / SBML-XML / 功能基JSON 等             │
│                                                                     │
│  失败条件：无法识别领域 / 内容不匹配任何已知模板 → 降级到 Layer 2      │
└─────────────────────────────────────────────────────────────────────┘
  ↓ (若 Layer 1 失败)
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 2: 通用元框架兜底（10%覆盖，轻规则）                           │
│                                                                     │
│  Step 1: 通用元框架识别                                              │
│    - 先匹配 DEVS（离散事件系统特征）                                 │
│    - 再匹配 范畴论（数学结构特征）                                    │
│    - 再匹配 重写系统（规则演化特征）                                  │
│    - 再匹配 系统动力学（反馈回路特征）                                │
│                                                                     │
│  Step 2: 轻规则配置                                                   │
│    - 提取通用结构：输入/输出/子组件/调用关系/约束                      │
│    - 用正则/规则匹配填充五元组                                       │
│    - 示例：DEVS原子模型 → 输入端口/输出端口/状态/外部转移函数          │
│                                                                     │
│  Step 3: 输出通用函数树                                               │
│    - 统一的五元组 JSON                                               │
│                                                                     │
│  失败条件：通用元框架也无法匹配 → 降级到 Layer 3                       │
└─────────────────────────────────────────────────────────────────────┘
  ↓ (若 Layer 2 失败)
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3: LLM兜底（5%覆盖，LLM提取+规则校验）                          │
│                                                                     │
│  Step 1: LLM提取五元组                                               │
│    - Prompt: "请将以下知识节点转译为函数嵌套树：输入、输出、            │
│              子函数、调用关系、约束"                                  │
│                                                                     │
│  Step 2: 规则校验修正                                                │
│    - 检查层级一致性（输入维度 vs 输出维度）                            │
│    - 检查调用完整性（所有子函数输入是否被上级输出覆盖）                  │
│    - 检查约束一致性（是否有自相矛盾的约束）                            │
│                                                                     │
│  Step 3: 人工审核标记                                                │
│    - 置信度 < 0.7 的 LLM 产出 → 加入 deconstruction_audit 表          │
│    - 标记 generator_type = "llm_fallback"                             │
│                                                                     │
│  输出：带置信度标记的五元组 JSON                                       │
└─────────────────────────────────────────────────────────────────────┘
  ↓
统一输出：标准化的五元组函数树（Input/Output/Sub-functions/Call-Graph/Constraints）
```

---

## 4. 领域识别器 (Domain Classifier) — Layer 1 入口

### 4.1 识别规则（基于关键词+结构特征）

```python
DOMAIN_RULES = {
    "bond_graph": {
        "keywords": ["键合图", "bond graph", "势变量", "流变量", "0-节点", "1-节点", 
                     "R元件", "C元件", "I元件", "TF", "GY", "功率守恒"],
        "formal_language": "BondGraph",
        "template_path": "templates/bond_graph.json"
    },
    "signal_flow_graph": {
        "keywords": ["信号流图", "signal flow graph", "梅森增益", "Mason", "前向通路", 
                     "反馈环", "传输函数", "支路"],
        "formal_language": "SFG",
        "template_path": "templates/sfg.json"
    },
    "port_hamiltonian": {
        "keywords": ["端口哈密顿", "port-hamiltonian", "能量端口", "互联结构", 
                     "Dirac结构", "耗散"],
        "formal_language": "PortHamiltonian",
        "template_path": "templates/port_hamiltonian.json"
    },
    "functional_basis": {
        "keywords": ["功能基", "functional basis", "分支", "通道", "转换", "供应", 
                     "物质流", "能量流", "信号流", "TRIZ"],
        "formal_language": "FunctionalBasis",
        "template_path": "templates/functional_basis.json"
    },
    "sbml": {
        "keywords": ["SBML", "物种", "species", "反应", "reaction", "代谢", "metabolism",
                     "信号通路", "signaling pathway", "隔间", "compartment"],
        "formal_language": "SBML",
        "template_path": "templates/sbml.json"
    },
    "chemical_reaction_network": {
        "keywords": ["化学反应网络", "CRN", "反应速率", "质量作用定律", "守恒律", 
                     "化学计量矩阵", "stoichiometric"],
        "formal_language": "CRN",
        "template_path": "templates/crn.json"
    },
    "gene_ontology": {
        "keywords": ["基因本体", "GO", "Gene Ontology", "分子功能", "生物过程", "细胞组分",
                     "GO term", "富集分析"],
        "formal_language": "GO",
        "template_path": "templates/go.json"
    },
    "sysml": {
        "keywords": ["SysML", "块图", "block diagram", "端口", "port", "需求图", 
                     "活动图", "序列图", "状态机", "MBSE"],
        "formal_language": "SysML",
        "template_path": "templates/sysml.json"
    },
    "idef0": {
        "keywords": ["IDEF0", "功能建模", "输入-输出-控制-机制", "ICOM", 
                     "活动框", "箭头", "A-0图"],
        "formal_language": "IDEF0",
        "template_path": "templates/idef0.json"
    },
    "modelica": {
        "keywords": ["Modelica", "非因果", "equation-based", "连接器", "connector", 
                     "模型", "model", "组件", "component"],
        "formal_language": "Modelica",
        "template_path": "templates/modelica.json"
    },
    "petri_net": {
        "keywords": ["Petri网", "Petri net", "库所", "place", "变迁", "transition", 
                     "托肯", "token", "可达图", "fire"],
        "formal_language": "PetriNet",
        "template_path": "templates/petri_net.json"
    },
    "process_algebra": {
        "keywords": ["进程代数", "π-演算", "CCS", "CSP", "通道", "channel", "同步", 
                     "交互", "并发", "deadlock"],
        "formal_language": "ProcessAlgebra",
        "template_path": "templates/process_algebra.json"
    },
    "system_dynamics": {
        "keywords": ["系统动力学", "system dynamics", "存量", "stock", "流量", "flow", 
                     "反馈回路", "feedback loop", "因果环", "causal loop"],
        "formal_language": "SystemDynamics",
        "template_path": "templates/system_dynamics.json"
    },
    "game_theory": {
        "keywords": ["博弈论", "game theory", "纳什均衡", "Nash equilibrium", "扩展式", 
                     "extensive-form", "信息集", "收益矩阵", "payoff"],
        "formal_language": "GameTheory",
        "template_path": "templates/game_theory.json"
    },
    "abm_odd": {
        "keywords": ["ABM", "基于主体", "agent-based", "ODD协议", "ODD protocol", 
                     "主体", "agent", "涌现", "emergence"],
        "formal_language": "ABM_ODD",
        "template_path": "templates/abm_odd.json"
    },
    "formal_grammar": {
        "keywords": ["形式文法", "formal grammar", "乔姆斯基", "Chomsky", "正则语言", 
                     "上下文无关", "产生式", "production", "推导"],
        "formal_language": "FormalGrammar",
        "template_path": "templates/formal_grammar.json"
    },
    "act_r": {
        "keywords": ["ACT-R", "认知架构", "cognitive architecture", "产生式规则", 
                     "production rule", "陈述性记忆", "程序性记忆", "冲突集"],
        "formal_language": "ACT_R",
        "template_path": "templates/act_r.json"
    },
    "category_theory": {
        "keywords": ["范畴论", "category theory", "函子", "functor", "自然变换", 
                     "natural transformation", "态射", "morphism", "对象", "object"],
        "formal_language": "CategoryTheory",
        "template_path": "templates/category_theory.json"
    },
    "ars": {
        "keywords": ["重写系统", "rewriting system", "重写规则", "rewrite rule", "规约", 
                     "reduction", "正规式", "normal form", "合流性", "confluence"],
        "formal_language": "ARS",
        "template_path": "templates/ars.json"
    },
    "devs": {
        "keywords": ["DEVS", "离散事件", "discrete event", "原子模型", "atomic model", 
                     "耦合模型", "coupled model", "事件调度", "event scheduling"],
        "formal_language": "DEVS",
        "template_path": "templates/devs.json"
    },
    "information_theory": {
        "keywords": ["信息论", "information theory", "信道", "channel", "信源", "source", 
                     "信宿", "sink", "熵", "entropy", "互信息", "mutual information"],
        "formal_language": "InformationTheory",
        "template_path": "templates/information_theory.json"
    },
    "owl": {
        "keywords": ["OWL", "本体", "ontology", "RDF", "三元组", "triple", "类", "class", 
                     "属性", "property", "个体", "individual", "公理", "axiom"],
        "formal_language": "OWL",
        "template_path": "templates/owl.json"
    },
    "conceptual_graphs": {
        "keywords": ["概念图", "conceptual graph", "Sowa", "类型", "type", "关系", 
                     "relation", " referent", "概念节点", "关系节点"],
        "formal_language": "ConceptualGraphs",
        "template_path": "templates/conceptual_graphs.json"
    },
    "narrative_structure": {
        "keywords": ["叙事结构", "narrative structure", "Propp", "角色功能", "角色", 
                     "function", "情节", "plot", "Quest模型", "英雄之旅"],
        "formal_language": "NarrativeStructure",
        "template_path": "templates/narrative_structure.json"
    },
    "step_express": {
        "keywords": ["STEP", "EXPRESS", "ISO 10303", "产品数据", "产品模型", "实体", "entity", 
                     "属性", "attribute", "几何", "拓扑", "装配"],
        "formal_language": "STEP_EXPRESS",
        "template_path": "templates/step_express.json"
    },
    "input_output": {
        "keywords": ["投入产出", "input-output", "Leontief", "技术系数", "部门间", 
                     "产业关联", "直接消耗系数", "完全消耗系数"],
        "formal_language": "InputOutput",
        "template_path": "templates/input_output.json"
    },
    "social_network": {
        "keywords": ["社会网络", "social network", "中心性", "centrality", "聚类系数", 
                     "clustering", "度分布", "小世界", "六度分隔"],
        "formal_language": "SocialNetwork",
        "template_path": "templates/social_network.json"
    },
    "ast_cfg": {
        "keywords": ["抽象语法树", "AST", "控制流图", "CFG", "基本块", "basic block", 
                     "控制流", "control flow", "数据流", "data flow"],
        "formal_language": "AST_CFG",
        "template_path": "templates/ast_cfg.json"
    },
    "type_theory": {
        "keywords": ["类型论", "type theory", "依赖类型", "dependent type", "柯里-霍华德", 
                     "Curry-Howard", "类型签名", "type signature", "lambda演算"],
        "formal_language": "TypeTheory",
        "template_path": "templates/type_theory.json"
    },
    "cellml": {
        "keywords": ["CellML", "细胞模型", "cell model", "电生理", "electrophysiology", 
                     "离子通道", "ion channel", "组件", "变量", "连接"],
        "formal_language": "CellML",
        "template_path": "templates/cellml.json"
    },
    "biopax": {
        "keywords": ["BioPAX", "生物通路", "biological pathway", "信号转导", "代谢通路", 
                     "实体", "物理实体", "interaction", "转换", "调控"],
        "formal_language": "BioPAX",
        "template_path": "templates/biopax.json"
    },
    "mof": {
        "keywords": ["MOF", "元对象设施", "Meta-Object Facility", "元模型", "metamodel", 
                     "元类", "metaclass", "元属性", "meta-attribute"],
        "formal_language": "MOF",
        "template_path": "templates/mof.json"
    },
    "sysml_v2": {
        "keywords": ["SysML v2", "KerML", "Kernels", "语义基础", "语义建模", 
                     "SysML v2规范", "下一代系统工程"],
        "formal_language": "SysMLv2",
        "template_path": "templates/sysml_v2.json"
    },
    "mda_qvt": {
        "keywords": ["MDA", "模型驱动", "model-driven", "QVT", "模型转换", "model transformation", 
                     "PIM", "PSM", "映射规则", "mapping rule"],
        "formal_language": "MDA_QVT",
        "template_path": "templates/mda_qvt.json"
    },
    "idf3": {
        "keywords": ["IDEF3", "过程流", "process flow", "单元", "unit", "交汇点", "junction", 
                     "链接", "link", "时序", "sequence", "逻辑"],
        "formal_language": "IDEF3",
        "template_path": "templates/idef3.json"
    },
    "plcopen": {
        "keywords": ["PLCopen", "PLC", "功能块", "function block", "IEC 61131", "结构化文本", 
                     "ST", "梯形图", "LAD", "顺序功能图", "SFC"],
        "formal_language": "PLCopen",
        "template_path": "templates/plcopen.json"
    },
}
```

### 4.2 优先级与降级策略

```python
def classify_domain(node_text: str) -> DomainClassification:
    """领域识别与降级策略。
    
    优先级：
    1. 精确匹配：标题/关键词命中某个领域规则（ confidence >= 0.8 ）
    2. 模糊匹配：多个领域关键词部分命中（ confidence 0.5-0.8 ）
    3. 通用匹配：只命中通用元框架关键词（DEVS/范畴论/重写系统）
    4. 无匹配：降级到 LLM
    """
    scores = {}
    for domain_id, rule in DOMAIN_RULES.items():
        score = sum(1 for kw in rule["keywords"] if kw in node_text.lower())
        scores[domain_id] = score / len(rule["keywords"])
    
    best_domain = max(scores, key=scores.get)
    best_score = scores[best_domain]
    
    if best_score >= 0.8:
        return DomainClassification(
            layer=1,  # Layer 1: 领域原生标准
            domain_id=best_domain,
            confidence=best_score,
            formal_language=DOMAIN_RULES[best_domain]["formal_language"],
            template_path=DOMAIN_RULES[best_domain]["template_path"],
        )
    elif best_score >= 0.5:
        # 模糊匹配：尝试通用元框架
        return DomainClassification(
            layer=2,  # Layer 2: 通用元框架
            domain_id=best_domain,
            confidence=best_score,
            formal_language="UniversalMetaFramework",
            template_path="templates/universal_meta.json",
            fallback_reason="partial_match",
        )
    else:
        # 无匹配：降级到 LLM
        return DomainClassification(
            layer=3,  # Layer 3: LLM兜底
            domain_id="unknown",
            confidence=0.0,
            formal_language="LLM_Fallback",
            template_path="templates/llm_fallback.json",
            fallback_reason="no_match",
        )
```

---

## 5. 模板映射到五元组函数树

### 5.1 通用映射规则

所有领域原生模板最终都映射到统一五元组：

```json
{
  "function_tree": {
    "input": ["输入描述1", "输入描述2"],
    "output": ["输出描述1", "输出描述2"],
    "sub_functions": [
      {
        "id": "sub_1",
        "name": "子函数名称",
        "input": [...],
        "output": [...],
        "sub_functions": [...],  // 递归嵌套
        "constraints": [...]
      }
    ],
    "call_graph": [
      {"from": "sub_1", "to": "sub_2", "relation": "sequential"},
      {"from": "sub_2", "to": "sub_3", "relation": "conditional"}
    ],
    "constraints": [
      {"type": "equality", "expr": "input_dim == output_dim"},
      {"type": "inequality", "expr": "gain < 1.0"},
      {"type": "physical", "expr": "能量守恒"}
    ]
  }
}
```

### 5.2 示例：Bond Graph → 五元组

```
Bond Graph 原生结构:
  0-节点 (并联) → 势相等，流相加
  ├── R元件: R1 (阻尼) → 流 = 势/R
  ├── C元件: C1 (弹簧) → 流 = C * d(势)/dt
  └── I元件: I1 (质量) → 势 = I * d(流)/dt

五元组映射:
  Input: ["外部力 (势变量)", "初始速度 (流变量)"]
  Output: ["系统位移", "系统速度", "能量耗散率"]
  Sub-functions:
    - R1_Damping: 输入=势, 输出=流, 约束="流 = 势/R"
    - C1_Spring: 输入=势, 输出=流, 约束="流 = C * d(势)/dt"
    - I1_Mass: 输入=流, 输出=势, 约束="势 = I * d(流)/dt"
  Call-graph:
    - 0-节点 → 并联关系 → R1, C1, I1 同时接收输入
    - R1, C1, I1 输出汇聚到 1-节点（串联）
  Constraints:
    - 0-节点: 势相等
    - 1-节点: 流相等
    - 全局: 功率守恒 Σ(势×流) = 0
```

---

## 6. 与 v5.2c 形式化转译引擎的集成

```
v5.2d 粗匹配器 (本模块):
  → 输入：任意知识节点
  → 输出：领域原生形式化结构 + 统一五元组函数树
  → 核心：领域识别 + 模板匹配 + 映射转换

v5.2c 形式化转译引擎:
  → 接收 v5.2d 输出的统一五元组函数树
  → 执行 WL 子树同构测试
  → 执行逻辑规则校验
  → 输出结构同构判定 + 视角建议

v5.2a 对偶器:
  → 接收 v5.2c 的结构同构判定
  → 基于同构度生成锚点吸引
  → 更新节点视角
```

---

## 7. 实施计划与里程碑

### Phase 1：基础设施（1-2周）

| 任务 | 说明 |
|------|------|
| 创建 `templates/` 目录 | 30+ 领域模板文件 |
| 实现 `DomainClassifier` | 基于关键词的领域识别器 |
| 实现 `TemplateLoader` | 模板加载与解析 |
| 实现 `FiveTupleMapper` | 通用映射到五元组函数树 |

### Phase 2：核心领域覆盖（2-3周）

| 优先级 | 领域 | 说明 |
|--------|------|------|
| P0 | 键合图、信号流图、功能基 | 物理/工程核心，与当前项目直接相关 |
| P0 | SysML、IDEF0、Modelica | 系统工程，与机床项目直接相关 |
| P1 | SBML、CRN、GO | 生命科学，未来扩展 |
| P1 | Petri网、进程代数 | 计算机科学，通用 |
| P2 | 系统动力学、博弈论 | 社会经济 |
| P2 | 形式文法、ACT-R | 认知/人文 |
| P3 | 其余20+领域 | 按需逐步扩展 |

### Phase 3：通用元框架（1-2周）

| 任务 | 说明 |
|------|------|
| DEVS 通用模板 | 离散事件系统兜底 |
| 范畴论抽象模板 | 数学结构兜底 |
| 重写系统模板 | 规则演化兜底 |
| 系统动力学模板 | 反馈系统兜底 |

### Phase 4：LLM兜底与集成（1周）

| 任务 | 说明 |
|------|------|
| LLM fallback prompt | 五元组提取 prompt |
| 规则校验修正 | 维度/调用/约束一致性检查 |
| 人工审核队列 | 置信度 < 0.7 的产出进入 deconstruction_audit |
| 与 v5.2c 集成测试 | 端到端流程验证 |

---

## 8. 预期效果

| 指标 | 当前 (v5.2a) | v5.2d 目标 | 提升 |
|------|-------------|-----------|------|
| 跨域结构匹配精度 | 0.2-0.5 (关键词+邻居计数) | 0.8-0.95 (形式化归一+WL同构) | +300% |
| LLM 依赖比例 | 100% (对偶器无结构推理) | 5% (仅边缘领域兜底) | -95% |
| 可解释性 | 低 (Jaccard黑盒) | 高 (标准形式化语言全程可追溯) | 质变 |
| 领域覆盖数 | 1 (振动控制) | 30+ (全领域) | +3000% |
| 标准化程度 | 无 (自定义逻辑) | 工业级标准 (ISO/OMG/NIST) | 质变 |

---

## 9. 一句话总结

**v5.2d 粗匹配器不是发明新轮子，而是把各领域已经造好的60年标准轮子（键合图、功能基、SBML、SysML、DEVS...）统一组装成一台跨域结构同构判定机。LLM只负责把图纸交给这台机器，机器自己用工业级标准语言做精确匹配。从"在泥巴里找金子"升级为"用工业CT扫描金砖"。**

---

*设计方案版本: v5.2d-DRAFT*
*撰写日期: 2026-06-17*
*作者: 合作 (OpenClaw)*
*全领域形式化语言来源：用户提供的文献综述 + 学界/工业界标准规范*
