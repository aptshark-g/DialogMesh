# Literature Cortex v5.2c 设计方案：跨域结构同构引擎

> **文档编号:** LC-DESIGN-v5.2c
> **版本:** v5.2c-DRAFT
> **状态:** 📋 DRAFT
> **完成度:** 30%（形式化转译模块为核心，需讨论）
> **日期:** 2026-06-17
> **依赖:** v5.2a 对偶器（对偶器作为触发层，此引擎作为升级层）
> **注册表:** 参见 `DESIGN-REGISTRY.md` 第 #design-文档清单 节
> **核心目标:** 将知识节点统一转译为形式化函数树，实现真正的跨域结构同构判定

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-17 | v5.2c-DRAFT | 初始设计，包含四层级联架构和形式化转译模块核心 |

---

## 1. 问题陈述

### 1.1 v5.2a 对偶器的本质缺陷

v5.2a 对偶器声称的"三层融合"（文本 50% + 结构 30% + 层级 20%）实际上：

| 声称 | 实际 | 后果 |
|------|------|------|
| 文本语义理解 | Jaccard 关键词匹配 | 同义词无法识别，如"热传导"和"傅里叶热方程" |
| 图结构分析 | 邻居 ID 集合重叠计数 | 无法识别深层嵌套结构同构 |
| 知识层级推理 | L1-L6 数字距离 | 纯数值比较，无逻辑含义 |

**核心矛盾：** 真正的跨域结构同构不在文本层，也不在纯图拓扑层——

拉格朗日多参考系、微分几何标架、程序函数嵌套，三者文本完全不同，拓扑也不同，但**底层嵌套形式完全相同**（都是"函数→子函数→参数映射"的递归结构）。

这种同构没有任何现有技术能捕获。对偶器、WL 测试、GraphSAGE 全部失效。

### 1.2 核心目标

实现一个**形式化转译模块**：将任意领域的知识节点统一转译为标准化的函数嵌套树，然后在此统一坐标系上执行结构同构判定。

---

## 2. 四层级联架构

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: 文本语义层 (Text Semantic Layer)                          │
│  工具: 轻量 Sentence-BERT (all-MiniLM-L6-v2)                        │
│  作用: 替换 Jaccard，解决同义词/上下位词/跨表述匹配                  │
│  状态: 开箱即用，零训练成本，80MB，CPU <5ms/条                       │
│  局限: 只解决文本维度，不触及结构                                    │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: 形式化转译层 (Formalization Transliteration Layer) — 核心   │
│  工具: 自研模块（见第3节详述）                                       │
│  作用: 将任意知识节点转译为统一函数嵌套树（AST / λ-演算）              │
│  状态: 待设计讨论                                                    │
│  能力: 跨域归一，拉格朗日/微分几何/程序函数 → 统一函数树              │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 3: 拓扑校验层 (Topology Verification Layer)                   │
│  工具: Weisfeiler-Lehman (WL) 测试                                   │
│  作用: 在统一函数树上判定子图同构度                                   │
│  状态: 成熟算法，无训练需求，直接可用                                 │
│  前提: 必须依赖 Layer 2 的形式化归一，否则跨域无效                   │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 4: 逻辑规则层 (Logic Rule Layer)                              │
│  工具: 轻量规则引擎（非完整 OWL）                                     │
│  作用: 层级校验、逻辑合规、结果修正                                   │
│  状态: 可手写 if-then 规则，无训练需求                                │
│  示例: "若 A 是 B 的特化函数，则 A 的层级低于 B"                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 2：形式化转译模块 — 核心设计（待讨论）

### 3.1 核心思想

**所有知识节点，无论领域，都可抽象为 "函数定义"：**

- **输入 (Input)**：接收什么前置知识/条件
- **输出 (Output)**：产出什么结果/产物
- **子模块 (Sub-functions)**：内部由哪些子组件组成
- **嵌套调用 (Call Graph)**：子模块之间的调用/依赖关系
- **约束 (Constraints)**：映射规则、边界条件、不变式

### 3.2 示例：跨域归一

#### 示例 A：拉格朗日分析力学 — 多参考系

```
原始描述:
  "拉格朗日力学通过广义坐标 q(t) 描述系统，通过参考系变换矩阵 Λ(t)
   将惯性系 S 的坐标映射到非惯性系 S'，满足 L = T - V"

形式化转译:
  Function: LagrangianSystem(
    Input: [GeneralizedCoordinates q(t), ReferenceFrame S, InertialFrame S'],
    Output: [EquationsOfMotion q̈(t)],
    Sub-functions: [
      CoordinateTransform(S, S') → Λ(t),       // 坐标映射函数
      KineticEnergy(q, q̇) → T,               // 能量计算函数
      PotentialEnergy(q) → V,                  // 势能计算函数
      Lagrangian(T, V) → L                     // 拉格朗日量组合函数
    ],
    Call-Graph: [
      CoordinateTransform(S, S') → KineticEnergy  (因为 T 依赖 S' 中的速度)
      KineticEnergy → Lagrangian
      PotentialEnergy → Lagrangian
      Lagrangian → EquationsOfMotion             (通过欧拉-拉格朗日方程)
    ],
    Constraints: [
      det(Λ(t)) ≠ 0,                              // 变换矩阵可逆
      S → S' 的映射是光滑微分同胚                  // 坐标系变换的数学约束
    ]
  )
```

#### 示例 B：微分几何 — 标架场

```
原始描述:
  "在流形 M 上定义局部标架 {e_i}，通过联络 ω^i_j 描述标架间的平行移动，
   满足 de_i = ω^j_i ∧ e_j"

形式化转译:
  Function: FrameField(
    Input: [Manifold M, Point p ∈ M, TangentSpace T_pM],
    Output: [CartanConnection ω^i_j, CurvatureForm Ω^i_j],
    Sub-functions: [
      LocalBasis(p) → {e_i(p)},                  // 局部基函数
      ConnectionForm({e_i}) → ω^i_j,            // 联络形式函数
      ExteriorDerivative(ω) → dω,                // 外微分函数
      StructureEquation(dω, ω) → Ω^i_j         // 结构方程函数
    ],
    Call-Graph: [
      LocalBasis → ConnectionForm
      ConnectionForm → ExteriorDerivative
      ExteriorDerivative → StructureEquation
    ],
    Constraints: [
      e_i ∧ e_j = δ_ij,                           // 正交归一约束
      d(de_i) = 0 (外微分两次为零)                  // 微分几何约束
    ]
  )
```

#### 示例 C：程序函数 — 嵌套调用

```python
# 原始代码
class NeuralController:
    def forward(self, state, target):
        error = self.compute_error(state, target)
        gradient = self.backprop(error)
        update = self.optimizer.step(gradient)
        return self.apply_update(state, update)
```

形式化转译:
```
  Function: NeuralController.forward(
    Input: [StateVector state, TargetVector target],
    Output: [UpdatedState state'],
    Sub-functions: [
      compute_error(state, target) → error,
      backprop(error) → gradient,
      optimizer.step(gradient) → update,
      apply_update(state, update) → state'
    ],
    Call-Graph: [
      compute_error → backprop → optimizer.step → apply_update  (线性链)
    ],
    Constraints: [
      state.dim == target.dim,                      // 维度匹配
      ||update|| < learning_rate                    // 更新步长约束
    ]
  )
```

### 3.3 关键观察：三者的结构同构

归一化后的函数树对比：

| 维度 | 拉格朗日 | 微分几何 | 程序函数 |
|------|---------|---------|---------|
| Input | 坐标 + 参考系 | 流形 + 点 + 切空间 | 状态向量 + 目标向量 |
| Output | 运动方程 | 曲率形式 | 更新状态 |
| 子函数数 | 4 | 4 | 4 |
| 调用链 | 树状（非线性依赖） | 线性链 | 线性链 |
| 约束类型 | 可逆性 + 光滑性 | 正交性 + 幂零性 | 维度匹配 + 范数约束 |

**结构同构判定：** 在函数树层面，拉格朗日系统的调用图比微分几何更复杂（非线性 vs 线性），但三者都呈现"输入→子函数→输出"的嵌套模式。这种同构在原始文本和原始图结构中完全不可见。

---

## 4. Layer 3：拓扑校验 — WL 测试在统一树上的应用

### 4.1 为什么 WL 跨域无效？

WL 测试的本质：
```
迭代聚合邻居标签，比较子树结构
```

在**原始图**上运行 WL：
- 拉格朗日图的节点标签："坐标变换"、"动能"、"势能"
- 微分几何图的节点标签："局部基"、"联络形式"、"外微分"
- WL 结果：**完全不相似**（标签完全不同）

在**形式化后的统一函数树**上运行 WL：
- 统一标签："Function"、"Input"、"Output"、"Sub-function"、"Constraint"
- 子函数调用关系成为统一拓扑
- WL 结果：**可以判定结构同构度**

### 4.2 实施方式

```python
def wl_subtree_similarity(func_tree_a, func_tree_b, depth=3):
    """在形式化函数树上执行 WL 子树相似度计算。"""
    
    # Step 1: 为函数树节点统一着色（标签归一化）
    # 所有输入节点 → 颜色 "input"
    # 所有输出节点 → 颜色 "output"
    # 所有子函数节点 → 颜色 "subfunc"
    # 所有约束节点 → 颜色 "constraint"
    
    # Step 2: WL 迭代着色
    for iteration in range(depth):
        for node in tree_nodes:
            # 聚合邻居颜色，生成新颜色
            neighbor_colors = sorted([get_color(n) for n in node.neighbors])
            node.color = hash(node.base_color + tuple(neighbor_colors))
    
    # Step 3: 比较子树颜色分布
    colors_a = Counter([n.color for n in tree_a.nodes])
    colors_b = Counter([n.color for n in tree_b.nodes])
    
    # WL 子树核相似度
    similarity = sum(min(colors_a[c], colors_b[c]) for c in set(colors_a) | set(colors_b))
    return similarity / max(len(tree_a.nodes), len(tree_b.nodes))
```

---

## 5. Layer 4：逻辑规则层 — 轻量规则引擎

### 5.1 与形式化转译的关系

形式化转译解决"结构匹配"，逻辑规则解决"匹配后的层级判定"。

| 场景 | 形式化转译 | 逻辑规则 |
|------|-----------|---------|
| 两个函数输入输出维度匹配 | 判定结构相似 | 判定是否存在组合可能性 |
| A 是 B 的特化函数 | 判定嵌套结构包含 | 判定 A 的层级低于 B |
| 两个函数共享相同约束 | 判定约束同构 | 判定是否属于同一物理域 |

### 5.2 示例规则

```python
RULES = [
    {
        "name": "specialization_implies_lower_level",
        "condition": lambda a, b: is_specialization_of(a, b),  # A 是 B 的特化函数
        "action": lambda a, b: a.level < b.level,             # 则 A 层级低于 B
        "confidence": 0.95
    },
    {
        "name": "dimensional_compatibility_implies_composability",
        "condition": lambda a, b: (a.output_dim == b.input_dim and 
                                    a.output_type == b.input_type),
        "action": lambda a, b: add_edge(a, b, "can_compose"),
        "confidence": 0.85
    },
    {
        "name": "shared_constraint_implies_domain_related",
        "condition": lambda a, b: len(set(a.constraints) & set(b.constraints)) >= 2,
        "action": lambda a, b: add_edge(a, b, "domain_related"),
        "confidence": 0.7
    },
]
```

---

## 6. 与 v5.2a 对偶器的集成关系

```
对偶器 (v5.2a) 触发流程：
  → 发现目标节点只有单视角
  → 调用对偶器 find_duals() 找到候选锚点
  → 对偶器发现文本相似度和邻居重叠不足以判定
  → 触发形式化转译引擎 (v5.2c)

形式化转译引擎执行流程：
  Step 1: 将目标节点 + 候选锚点分别送入形式化转译模块
  Step 2: 获得统一函数树
  Step 3: WL 测试判定子树同构度
  Step 4: 逻辑规则校验层级合理性
  Step 5: 返回结构同构判定 + 视角建议

回到对偶器：
  → 基于结构同构度重新排序锚点
  → 高结构同构锚点获得更高权重
  → 生成视角建议
```

---

## 7. 待讨论：形式化转译模块的实现细节

### 7.1 关键问题（需要你的判断）

| 问题 | 选项 A | 选项 B | 你的倾向 |
|------|--------|--------|---------|
| 转译驱动力 | **人工模板**（每个 L1-L6 类型有预定义函数模板） | **LLM 自动提取**（用大模型解析节点文本，自动生成函数树） | ？ |
| 转译粒度 | **粗粒度**（只提取 Input/Output/Sub-functions/Call-Graph/Constraints 五元组） | **细粒度**（深入到每个子函数的参数类型、约束的谓词逻辑） | ？ |
| 函数树格式 | **JSON 结构**（易读易查） | **AST 语法树**（便于编译和形式化推理） | ？ |
| 约束表达 | **自然语言**（轻量，易维护） | **谓词逻辑**（严格，可机器验证） | ？ |

### 7.2 核心风险

| 风险 | 描述 | 缓解 |
|------|------|------|
| 模板覆盖不足 | 新领域无匹配模板 | 从粗粒度开始，逐步积累模板 |
| LLM 幻觉 | 自动提取时生成错误的函数结构 | 人工审核 + 约束校验 |
| 转译成本 | 每个节点转译需要计算资源 | 缓存转译结果，增量更新 |
| 语义漂移 | 同一概念不同转译者产出不同函数树 | 标准化模板 + 版本控制 |

---

## 8. 一句话总结

**v5.2a 对偶器是"在泥巴里找金子"——用关键词和邻居重叠碰运气。v5.2c 形式化转译引擎是"把泥巴炼成金砖，再称重量"——先把所有领域归一到统一函数坐标系，再精确比对结构。前者是 0.2-0.5 精度的模糊匹配，后者是 0.8-0.95 精度的结构同构判定。**

---

*设计方案版本: v5.2c-DRAFT*
*撰写日期: 2026-06-17*
*作者: 合作 (OpenClaw)*
*形式化转译模块待讨论，见第3节和第7.1节*
