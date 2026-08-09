# Literature Cortex — 发散层设计草案 v0.1

**文档编号:** LC-DESIGN-DIVERGENT-v0.1  
**日期:** 2026-06-18 03:05  
**核心定位:** 收敛层的反面 — 不是验证，是怀疑；不是保持一致，是主动破坏  
**学术基础:** 反事实推理 + 溯因推理 + 类比推理 + BVSR 发散思维模型

---

## 1. 核心哲学：破坏即创造

收敛层追求 "A→B→C 是否成立"。  
发散层追问 "A→B→C 为什么必须成立？如果不成立，世界会怎样？"

> "发散层的本质不是生成更多正确路径，而是证明现有路径并非唯一。"

### 1.1 怀疑的三种形态

| 形态 | 问题 | 操作 | 学术对应 |
|------|------|------|----------|
| **链路破坏** | A→B→C 是否可被 A→D→C 替代？ | 移除/替换边，观察后果 | Counterfactual KG Reasoning (Zellinger 2024) |
| **节点溯因** | 给定 A 和 C，B 是否是唯一解释？ | 生成替代中间节点 | Abductive Reasoning (Bai 2024) |
| **跨域类比** | 其他领域是否存在 A'→B'→C' 的镜像？ | 结构同构映射 | Analogical Reasoning (Chan & Schunn 2014) |
| **倒置因果** | 假设太空是亮的，需要什么约束？ | 结果→约束反推 | Counterfactual Constraint Search + Inverse CSP |

---

## 2. 四层发散机制

### 2.0 扩散起点控制：ACT-R 双权重激活机制

**核心问题：** 四层发散如果全图遍历，必然落入穷举。人脑不是穷举机——它从"最近在想什么"和"最常想什么"出发，有偏采样。

**学术来源：** Anderson et al. (2004) *ACT-R: An Integrated Theory of the Mind*；engramai (tonitangpotato/engram-ai) 工程化实现。

**激活公式：**

```
Activation(n) = ln(freq_n + 1) − λ · ln(Δt_n + 1) + Σ w_i · Activation(n_i)
```

| 项 | 含义 | 参数 |
|----|------|------|
| `freq_n` | 节点累计访问次数 | 持久化记录 |
| `Δt_n` | 距上次访问的时间间隔（秒） | 持久化记录 |
| `λ` | 遗忘衰减系数，默认 0.5 | 可配置 |
| `Σ w_i · Activation(n_i)` | 传播激活（spreading activation） | Hebbian 共现权重 |

**判定规则：**

- 扩散起点：只从 `Activation > θ_start`（默认 0.3）的节点出发
- 扩散剪枝：邻居节点 `Activation < θ_prune`（默认 0.1）时停止扩散
- 遗忘阈值：`Activation < θ_forget`（默认 −1.0）的节点视为休眠，不触发发散

**与四层机制的耦合：**

| 发散层 | 双权重作用 |
|--------|-----------|
| Layer 1 反事实破坏 | 优先破坏激活度高的链路（用户最近验证过的） |
| Layer 2 溯因假设 | 从激活度最高的端节点出发搜索候选中间节点 |
| Layer 3 跨域类比 | 优先匹配最近被访问过的结构签名 |
| Layer 4 倒置因果 | 优先测试最近被质疑过的约束 |

**记忆效应：**

- **频率偏差**：高频节点即使很久未访问，基础激活度仍保持，确保核心知识不被遗忘
- **新近偏差**：最近访问的节点获得临时激活 boost，确保上下文连续性
- **两者耦合**：不是简单叠加，而是乘性调制——高频+新近 = 强扩散起点；高频+久远 = 弱但可达；低频+新近 = 临时关注；低频+久远 = 休眠

**工程实现：**

```python
class NodeActivationTracker:
    def __init__(self, db: sqlite3.Connection, lambda_decay: float = 0.5):
        self.db = db
        self.lambda_decay = lambda_decay
    
    def touch(self, node_id: str):
        """节点被访问时更新频率和新近性。"""
        self.db.execute('''
            INSERT INTO node_activation (node_id, access_count, last_accessed, base_activation)
            VALUES (?, 1, CURRENT_TIMESTAMP, 0.0)
            ON CONFLICT(node_id) DO UPDATE SET
                access_count = access_count + 1,
                last_accessed = CURRENT_TIMESTAMP,
                base_activation = ln(access_count + 1) - ? * ln(
                    (julianday('now') - julianday(last_accessed)) * 86400 + 1
                )
        ''', (node_id, self.lambda_decay))
        self.db.commit()
    
    def get_activation(self, node_id: str) -> float:
        """计算节点当前激活度。"""
        row = self.db.execute('''
            SELECT access_count, last_accessed, base_activation
            FROM node_activation WHERE node_id = ?
        ''', (node_id,)).fetchone()
        if not row:
            return -float('inf')  # 从未访问 = 休眠
        
        freq, last, base = row
        delta_t = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
        return math.log(freq + 1) - self.lambda_decay * math.log(delta_t + 1)
    
    def get_hot_nodes(self, limit: int = 10) -> list[tuple[str, float]]:
        """获取当前激活度最高的节点，作为发散起点。"""
        cursor = self.db.execute('''
            SELECT node_id, base_activation FROM node_activation
            WHERE base_activation > -1.0
            ORDER BY base_activation DESC LIMIT ?
        ''', (limit,))
        return [(row[0], row[1]) for row in cursor.fetchall()]
```

### 2.1 Layer 1: 反事实链路破坏 (Counterfactual Link Breaking)

**核心思想：** 给定收敛链路 A→B→C，主动破坏其中一环，观察系统是否崩溃。

**学术来源：** COULDD (Counterfactual Reasoning with Knowledge Graph Embeddings, Zellinger et al., 2024, University of Vienna)

**机制：**

```
输入：收敛链路 A→B→C（已通过收敛层验证）

Step 1: 假设破坏
  - 假设移除边 A→B
  - 或假设替换边 A→B 为 A→D
  - 或假设插入节点：A→B→D→C

Step 2: 嵌入更新
  - 基于假设场景，更新 KG 嵌入
  - 模型必须判断：C 的推导是否仍成立？

Step 3: 后果检测
  - 如果 C 仍可达 → A→B 非关键链路，存在替代路径
  - 如果 C 不可达 → A→B 是关键链路，但可追问：是否存在 A→D→C？

Step 4: 生成反事实报告
  {
    "original_path": "A→B→C",
    "counterfactual_operation": "remove A→B",
    "consequence": "C_unreachable",
    "alternative_hypothesis": "A→D→C?",
    "criticality_score": 0.95,  // A→B 是关键链路
    "confidence": 0.87
  }
```

**关键洞察：**  如果链路破坏后系统不崩溃，说明收敛层的"唯一正确路径"假设不成立。发散层的目的就是找到这些"隐藏的替代路径"。

---

### 2.2 Layer 2: 溯因假设生成 (Abductive Hypothesis Generation)

**核心思想：** 给定观察 A 和 C，推断最可能的中间节点 D，使得 A→D→C 成立。

**学术来源：** AbductiveKGR (Bai et al., 2024, HKUST) + DARK (Unifying Deductive and Abductive Reasoning, 2026, WWW)

**机制：**

```
输入：观察 O = {A 存在，C 存在，但 A→C 无直接链路}

Step 1: 候选生成
  - 从 A 的邻居中，找出所有可达 C 的候选节点 {D₁, D₂, D₃, ...}
  - 生成假设：A→Dᵢ→C

Step 2: 假设验证（RLF-KG 强化学习）
  - 对每个假设 Hᵢ = A→Dᵢ→C，用 KG 验证：
    - 从 A 出发，能否到达 Dᵢ？（前向验证）
    - 从 Dᵢ 出发，能否到达 C？（后向验证）
    - A→Dᵢ 和 Dᵢ→C 是否在知识图谱中有语义支撑？
  
Step 3: 奖励函数
  - 路径长度越短，奖励越高
  - 结构同构度越高，奖励越高
  - 与现有知识的冲突越少，奖励越高

Step 4: 输出最优假设
  {
    "observation": "A 与 C 关联但无直接路径",
    "best_hypothesis": "A→D→C",
    "alternative_paths": ["A→E→C", "A→F→G→C"],
    "confidence": 0.82,
    "reasoning": "D 在结构上与 B 同构，且 A→D 和 D→C 均有语义支撑"
  }
```

**与收敛层的关系：**  收敛层说 "A→B→C 成立"。发散层问："如果我不知道 B，只看到 A 和 C，我会推断出什么？"

---

### 2.3 Layer 3: 跨域类比发散 (Cross-Domain Analogical Divergence)

**核心思想：** 在其他领域寻找 A'→B'→C' 的镜像，质疑 "为什么这个结构只出现在当前领域？"

**学术来源：** The Impact of Analogies on Creative Concept Generation (Chan & Schunn, 2014, Pittsburgh) + BVSR Model (Simonton, 2013)

**机制：**

```
输入：控制系统链路 A→B→C（如 PID→FxLMS→ANC）

Step 1: 结构抽象
  - 将 A→B→C 抽象为 "控制器→自适应算法→执行器" 的通用模式
  - 提取结构签名：{feedback_loop, adaptive_filter, error_minimization}

Step 2: 跨域搜索
  - 在热控领域：是否存在 "温控器→在线补偿→执行阀" 的链路？
  - 在机械领域：是否存在 "阻尼器→模态调节→振动抑制" 的链路？
  - 在化学领域：是否存在 "催化剂→反应速率调节→产物控制" 的链路？

Step 3: 结构同构判定
  - 使用 v5.2a 对偶器或 v5.2c 形式化转译引擎
  - 判定：A→B→C 与 A'→B'→C' 是否拓扑/功能同构？

Step 4: 类比生成
  {
    "source_domain": "control_system",
    "source_path": "PID→FxLMS→ANC",
    "target_domain": "thermal_system",
    "target_path": "PID→OnlineThermalCompensation→ProportionalValve",
    "isomorphism_level": "FUNCTIONAL",
    "confidence": 0.78,
    "question": "如果热控系统可以借鉴 ANC 的自适应结构，为什么当前热控仍使用固定 PID？"
  }
```

**关键洞察：** 跨域类比不是"复制解决方案"，而是"暴露当前领域的假设盲区"。如果其他领域已经存在结构同构的链路，说明当前领域的"唯一路径"假设可能是局部最优，而非全局最优。

---

### 2.4 Layer 4: 倒置因果约束反推 (Inverted Causality Constraint Search)

**核心思想：** 先假设结果成立，然后反推"需要什么样的约束条件才能使这个假设成立"。不是从约束推导结果，而是从结果反推约束。

**学术来源：** Counterfactual Constraint Satisfaction (约束满足逆问题) + Pearl Do-Calculus (因果推断中的干预理论) + Abductive Learning (Zhou et al., 溯因学习中的约束修正)

**核心哲学：** 关联与因果的转换。

```
正常因果（收敛层）：
  约束集合 {空间膨胀, 光衰减} → 结果 "太空是黑的"
  逻辑：如果约束成立，则结果必然成立

倒置因果（发散层）：
  假设结果 "太空是亮的" → 反推约束集合 {空间不膨胀, 光不衰减, 或存在光源}
  逻辑：如果结果要成立，约束必须变成什么样？
```

**机制：**

```
输入：收敛层链路 A→B→C，及其约束集合 {c₁, c₂, c₃}
       例如：FxLMS→ANC 的约束 {μ<μ_max, S_est收敛, 延迟补偿}

Step 1: 假设结果反转
  - 假设目标结果不成立："ANC 不收敛" 或 "ANC 效果差"
  - 或假设目标结果以不同方式成立："ANC 用更少的传感器实现"
  - 或假设完全不同的结果："太空是亮的"（远离当前领域）

Step 2: 约束差异分析
  - 对比"当前约束"与"假设结果所需的约束"
  - 识别哪些约束必须改变、哪些约束必须新增、哪些约束可以移除
  - 示例：
    当前约束：μ < 0.001（小步长保守收敛）
    假设结果：ANC 速度提升 10 倍
    所需约束变化：μ → 变步长/归一化，或 S_est → 在线辨识，或引入并行结构

Step 3: 约束修正搜索
  - 对每条约束 cᵢ，尝试：
    a) 移除 cᵢ → 结果是否变成假设？
    b) 放松 cᵢ → 结果如何变化？
    c) 替换 cᵢ 为 cᵢ' → 结果是否匹配假设？
    d) 添加新约束 cⱼ → 结果是否稳定在假设？
  - 使用约束满足（CSP）求解器或梯度搜索

Step 4: 生成倒置因果报告
  {
    "original_result": "太空是黑的",
    "assumed_result": "太空是亮的",
    "current_constraints": ["空间膨胀", "光衰减", "宇宙年龄有限"],
    "required_constraint_changes": [
      {
        "operation": "remove",
        "constraint": "空间膨胀",
        "reason": "若空间不膨胀，远处星系不红移，光强不衰减"
      },
      {
        "operation": "add",
        "constraint": "全宇宙均匀光源",
        "reason": "弥补光衰减后的亮度不足"
      },
      {
        "operation": "replace",
        "constraint": "光不衰减",
        "original": "光衰减",
        "reason": "假设光在真空中不随距离衰减"
      }
    ],
    "feasibility_score": 0.15,  // 所需约束变化与现实差距极大
    "insight": "太空之所以黑，是因为空间膨胀和光衰减的组合难以同时规避"
  }
```

**与收敛层的关系：**  收敛层说 "给定约束，结果必然如此"。发散层问："如果我不接受这个结果，我需要挑战哪些约束？"

**关键洞察：** 倒置因果不是"否定现有知识"，而是"暴露约束的敏感性"。它回答："哪些约束是结果的必要前提？改变哪个约束最容易颠覆结论？"

**示例映射（技术文献场景）：**

| 场景 | 收敛层结论 | 发散层倒置因果 | 约束变化 |
|------|-----------|--------------|---------|
| 振动控制 | FxLMS 上限 10.82 dB | 假设要达到 14.2 dB | 需要 S_est 在线辨识 + 变步长 + 分谐波 MIMO |
| 热控 | 40路PT100实现精度 | 假设只需 10 路传感器 | 需要 PINN 模型预测 + 温度场插值 + 物理约束嵌入 |
| 机械设计 | HT300 铸件传统路线 | 假设用 IMCD4618 实现 | 需要材料阻尼率验证 + 灌注工艺 + 成本约束放松 |
| 数字孪生 | Vericut 依赖商业软件 | 假设完全自研 | 需要自定义机床功能 + 几何误差模型 + 切削力数据库 |

---

## 3. 发散层与收敛层的交互协议

### 3.1 交互模型：双循环结构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        应用层 (API / UI / Pipeline)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────┐        ┌──────────────────────┐          │
│  │    收敛层循环         │        │    发散层循环         │          │
│  │  (Convergent Loop)   │  ↔    │  (Divergent Loop)    │          │
│  │                      │        │                      │          │
│  │  A→B→C 验证          │        │  A→B→C 破坏          │          │
│  │  一致性检查            │        │  替代路径生成          │          │
│  │  规则校验              │        │  反事实推理            │          │
│  │  判定输出              │        │  跨域类比              │          │
│  │                      │        │                      │          │
│  │  输出：确认/修正        │  ←────│  输出：怀疑/假设        │          │
│  │                      │        │                      │          │
│  │  输入：收敛链路        │  ────→│  输入：收敛链路        │          │
│  └──────────────────────┘        └──────────────────────┘          │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              元认知仲裁层 (Meta-Cognitive Arbiter)              │  │
│  │                                                              │  │
│  │  职责：决定何时收敛、何时发散、何时切换视角                    │  │
│  │  输入：收敛层结果 + 发散层假设 + 系统状态                      │  │
│  │  输出：执行指令（收敛/发散/暂停/切换）                         │  │
│  │                                                              │  │
│  │  触发发散的条件：                                              │  │
│  │  1. 收敛链路停滞（depth=3 无新假设）                          │  │
│  │  2. 用户主动要求"质疑"                                        │  │
│  │  3. 多视角冲突（同一节点不同视角结论矛盾）                      │  │
│  │  4. 跨域检测到结构同构但结论不同                               │  │
│  │                                                              │  │
│  │  触发收敛的条件：                                              │  │
│  │  1. 发散假设过多（超过预算）                                   │  │
│  │  2. 假设验证通过率低于阈值                                     │  │
│  │  3. 用户主动要求"确认"                                        │  │
│  │  4. 系统资源不足                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              验证反馈循环 (Validation Feedback Loop)             │  │
│  │                                                              │  │
│  │  发散层生成的假设 → 送回收敛层验证 → 结果反馈到发散层           │  │
│  │  高通过率的假设 → 提升权重 → 增加预算                          │  │
│  │  低通过率的假设 → 降低权重 → 减少预算                          │  │
│  │  被证伪的假设 → 归档 → 记录矛盾原因                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                    持久化层 (Persistence Layer)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ nodes_v2 │  │ edges_v2 │  │ hypo_arch│  │ dual_mat │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │counterfact│  │abductive  │  │analogical│  │direction │           │
│  │_log      │  │_hypothesis│  │_matches  │  │_stats    │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 数据流向

```
收敛层输出：
  {
    "path": "A→B→C",
    "verdict": "CONFIRMED",
    "confidence": 0.95
  }
  ↓
元认知仲裁层判断："是否需要发散？"
  → 是（触发条件满足）
  ↓
发散层输入：
  {
    "path": "A→B→C",
    "divergent_mode": "counterfactual_breaking"  // 或 "abductive", "analogical", "inverted_causality"
  }
  ↓
发散层输出：
  {
    "original_path": "A→B→C",
    "doubt_report": [
      {
        "type": "link_breaking",
        "operation": "remove A→B",
        "consequence": "C_unreachable",
        "criticality": 0.95,
        "alternative": "A→D→C?"
      },
      {
        "type": "abductive_gap",
        "observation": "A and C exist",
        "best_hypothesis": "A→D→C",
        "confidence": 0.82
      },
      {
        "type": "cross_domain_analogy",
        "source": "A→B→C (control)",
        "target": "A'→B'→C' (thermal)",
        "isomorphism": "FUNCTIONAL",
        "question": "Why not use adaptive structure in thermal control?"
      },
      {
        "type": "inverted_causality",
        "original_result": "ANC converges to 10.82dB",
        "assumed_result": "ANC reaches 14.2dB",
        "required_changes": [
          {"operation": "add", "constraint": "online S_est identification"},
          {"operation": "replace", "constraint": "fixed step size → adaptive step size"}
        ],
        "feasibility": 0.35,
        "insight": "14.2dB requires violating at least 3 current constraints simultaneously"
      }
    ]
  }
  ↓
验证反馈循环：
  - 将 doubt_report 送回收敛层验证
  - 收敛层对 A→D→C 执行完整验证流程
  - 如果验证通过 → A→D→C 成为新收敛链路
  - 如果验证失败 → 记录失败原因，归档假设
  - 对倒置因果的约束变化 → 收敛层验证约束变化后的结果是否匹配假设
  - 如果约束变化可行 → 升级为实验方案
  - 如果约束变化不可行 → 记录不可行原因，归档
```

---

## 4. 持久化层扩展

### 4.1 新增表：counterfactual_log

```sql
CREATE TABLE IF NOT EXISTS counterfactual_log (
    id TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,  -- 如 "A→B→C"
    operation TEXT NOT NULL,      -- "remove", "replace", "insert"
    target_edge TEXT,             -- 被破坏的边，如 "A→B"
    replacement_edge TEXT,        -- 替换后的边（如 replace 操作）
    consequence TEXT,             -- "reachable", "unreachable", "ambiguous"
    criticality_score REAL,       -- 0-1，越高说明该边越关键
    alternative_hypothesis TEXT,  -- 如 "A→D→C"
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 新增表：abductive_hypothesis

```sql
CREATE TABLE IF NOT EXISTS abductive_hypothesis (
    id TEXT PRIMARY KEY,
    observation TEXT NOT NULL,    -- 如 "A 与 C 关联但无直接路径"
    hypothesis TEXT NOT NULL,     -- 如 "A→D→C"
    candidate_nodes TEXT,         -- JSON: ["D", "E", "F"]
    confidence REAL,
    verification_status TEXT CHECK(verification_status IN ('pending', 'verified', 'falsified', 'ambiguous')),
    verification_result TEXT,     -- 验证后的详细结果
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP
);
```

### 4.3 新增表：analogical_matches

```sql
CREATE TABLE IF NOT EXISTS analogical_matches (
    id TEXT PRIMARY KEY,
    source_domain TEXT NOT NULL,
    source_path TEXT NOT NULL,
    target_domain TEXT NOT NULL,
    target_path TEXT NOT NULL,
    isomorphism_level TEXT CHECK(isomorphism_level IN ('TOPOLOGICAL', 'FUNCTIONAL', 'PHYSICAL')),
    confidence REAL,
    critical_question TEXT,       -- 如 "Why not use adaptive structure in thermal control?"
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.4 新增表：inverted_causality

```sql
CREATE TABLE IF NOT EXISTS inverted_causality (
    id TEXT PRIMARY KEY,
    original_result TEXT NOT NULL,     -- 如 "太空是黑的"
    assumed_result TEXT NOT NULL,      -- 如 "太空是亮的"
    original_path TEXT,                -- 关联的收敛链路，如 "A→B→C"
    current_constraints TEXT,          -- JSON: ["空间膨胀", "光衰减"]
    required_changes TEXT,             -- JSON: [{"operation": "remove", "constraint": "...", "reason": "..."}]
    feasibility_score REAL,            -- 0-1，约束变化与现实差距
    sensitivity_ranking TEXT,          -- JSON: [{"constraint": "...", "sensitivity": 0.95}]
    insight TEXT,                      -- 自然语言洞察
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.6 新增表：node_activation（双权重激活记录）

```sql
CREATE TABLE IF NOT EXISTS node_activation (
    node_id TEXT PRIMARY KEY,
    access_count INTEGER DEFAULT 0,           -- 累计访问频率
    last_accessed TIMESTAMP,                  -- 上次访问时间
    base_activation REAL DEFAULT 0.0,         -- 基础激活度（预计算缓存）
    spreading_weight REAL DEFAULT 0.0,        -- 传播激活权重（Hebbian累积）
    FOREIGN KEY (node_id) REFERENCES nodes(id)
);

CREATE INDEX idx_activation_base ON node_activation(base_activation);
CREATE INDEX idx_activation_last ON node_activation(last_accessed);
```

**触发时机：**
- 收敛层验证通过某节点 → `touch(node_id)` 频率+1
- 发散层引用某节点作为假设 → `touch(node_id)` 频率+1
- 用户显式查询某节点 → `touch(node_id)` 频率+1
- 心跳/定时任务 → 批量衰减 `base_activation`（模拟遗忘）

### 4.5 新增表：constraint_sensitivity

```sql
CREATE TABLE IF NOT EXISTS constraint_sensitivity (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    constraint_name TEXT NOT NULL,
    constraint_type TEXT,              -- "hard", "soft", "assumed"
    current_value TEXT,
    result_if_removed TEXT,            -- 移除该约束后的结果
    result_if_relaxed TEXT,            -- 放松该约束后的结果
    result_if_replaced TEXT,           -- 替换该约束后的结果
    sensitivity_score REAL,            -- 0-1，该约束对结果的敏感程度
    is_necessary INTEGER DEFAULT 0,    -- 是否为必要约束（移除则结果不成立）
    is_sufficient INTEGER DEFAULT 0,   -- 是否为充分约束（单独即可保证结果）
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_constraint_node ON constraint_sensitivity(node_id);
CREATE INDEX idx_constraint_name ON constraint_sensitivity(constraint_name);
```

---

## 5. 发散层的 CLI 接口

```bash
# 对指定链路执行反事实破坏
lcortex doubt --path "A→B→C" --mode counterfactual

# 对指定节点执行溯因假设生成
lcortex hypothesize --from A --to C --mode abductive

# 跨域类比搜索
lcortex analogy --path "A→B→C" --domain control_system --target-domain thermal_system

# 倒置因果：假设不同结果，反推约束变化
lcortex invert --path "A→B→C" --assume "太空是亮的"

# 约束敏感性分析：哪些约束最关键
lcortex sensitivity --path "A→B→C" --analyze all

# 综合发散：对链路执行全部四种怀疑
lcortex diverge --path "A→B→C" --all

# 查看发散历史
lcortex divergence-log --node A

# 查看被归档的假设
lcortex hypothesis-archive --status falsified

# 查看倒置因果报告
lcortex invert-log --path "A→B→C" --limit 10

# 查看约束敏感性排名
lcortex sensitivity-rank --node A --top 5

# 双权重激活管理
lcortex activation-touch --node A          # 手动标记节点被访问
lcortex activation-hot --limit 10          # 查看当前最活跃的节点
lcortex activation-forget --node A         # 手动将节点置为休眠
lcortex activation-decay --batch 100       # 批量执行遗忘衰减（定时任务用）
lcortex activation-stats --node A          # 查看节点激活度统计
```

---

## 6. 最小可运行原型 (MVP)

### 6.1 目标

在现有收敛层基础上，实现最小发散层：
- 输入：收敛层验证通过的链路
- 输出：1-3 个怀疑报告（链路破坏、溯因假设、跨域类比）
- 不依赖真实 LLM，使用规则+嵌入实现

### 6.2 实现范围

| 组件 | 实现方式 | 工作量 |
|------|---------|--------|
| 反事实链路破坏 | 基于嵌入的边移除模拟 | 1-2 天 |
| 溯因假设生成 | 候选节点搜索 + 前向/后向验证 | 2-3 天 |
| 跨域类比 | 结构签名匹配（复用 v5.2a 对偶器） | 1-2 天 |
| **倒置因果约束反推** | **约束差异分析 + 敏感性排序** | **2-3 天** |
| 元认知仲裁触发 | 规则判断（停滞检测 + 用户指令） | 0.5 天 |
| 双权重激活机制 | 频率/新近性记录 + ACT-R 激活计算 + 遗忘衰减 | 1-2 天 |
| 持久化表 | SQLite 表创建（6 个新表） | 0.5 天 |

**总计：8-13 天**


### 6.3 关键技术点

**反事实链路破坏：**
```python
def counterfactual_break(path: str, edge_to_remove: str, kg: KnowledgeGraph) -> BreakReport:
    """
    1. 保存当前 KG 状态
    2. 移除指定边
    3. 重新计算目标节点嵌入/可达性
    4. 恢复原状态
    5. 返回破坏报告
    """
    original_state = kg.snapshot()
    kg.remove_edge(edge_to_remove)
    
    target_node = path.split("→")[-1]
    source_node = path.split("→")[0]
    
    is_reachable = kg.is_reachable(source_node, target_node)
    
    kg.restore(original_state)
    
    return BreakReport(
        original_path=path,
        removed_edge=edge_to_remove,
        target_still_reachable=is_reachable,
        criticality=1.0 if not is_reachable else 0.3,
        alternative_hypotheses=find_alternative_paths(source_node, target_node, kg) if not is_reachable else []
    )
```

**溯因假设生成：**
```python
def abductive_hypothesize(source: str, target: str, kg: KnowledgeGraph) -> Hypothesis:
    """
    1. 找出 source 的所有邻居 {N₁, N₂, ...}
    2. 对每个 Nᵢ，检查 Nᵢ 是否可达 target
    3. 对可达的 Nᵢ，计算路径质量（长度、同构度、语义支撑）
    4. 返回最优假设
    """
    neighbors = kg.get_neighbors(source)
    candidates = []
    
    for neighbor in neighbors:
        if kg.is_reachable(neighbor, target):
            path = kg.shortest_path(neighbor, target)
            quality = compute_path_quality(path, kg)
            candidates.append((neighbor, quality))
    
    candidates.sort(key=lambda x: x[1], reverse=True)
    best = candidates[0] if candidates else None
    
    return Hypothesis(
        observation=f"{source} 与 {target} 关联但无直接路径",
        best_hypothesis=f"{source}→{best[0]}→{target}" if best else None,
        confidence=best[1] if best else 0.0,
        alternatives=[f"{source}→{c[0]}→{target}" for c in candidates[1:4]]
    )
```

**倒置因果约束反推：**
```python
def inverted_causality(path: str, assumed_result: str, kg: KnowledgeGraph) -> InvertReport:
    """
    1. 获取当前路径的约束集合 {c₁, c₂, c₃}
    2. 对每条约束，执行三种操作：移除/放松/替换
    3. 检查结果是否趋近 assumed_result
    4. 返回约束敏感性排序和修正建议
    """
    current_constraints = kg.get_constraints(path)
    original_result = kg.evaluate(path)
    
    changes = []
    sensitivity_scores = []
    
    for constraint in current_constraints:
        # 测试移除
        kg.remove_constraint(path, constraint)
        result_without = kg.evaluate(path)
        sensitivity = compute_result_distance(result_without, original_result)
        
        # 测试放松
        kg.relax_constraint(path, constraint, factor=0.5)
        result_relaxed = kg.evaluate(path)
        
        # 恢复
        kg.restore_constraint(path, constraint)
        
        changes.append({
            "constraint": constraint.name,
            "current_value": constraint.value,
            "if_removed": result_without,
            "if_relaxed": result_relaxed,
            "sensitivity": sensitivity,
            "is_necessary": (result_without != original_result)
        })
        
        sensitivity_scores.append((constraint.name, sensitivity))
    
    # 找出使结果趋近 assumed_result 的约束变化
    required_changes = find_changes_toward_target(
        current_constraints, original_result, assumed_result, kg
    )
    
    return InvertReport(
        original_result=original_result,
        assumed_result=assumed_result,
        current_constraints=[c.name for c in current_constraints],
        required_changes=required_changes,
        sensitivity_ranking=sorted(sensitivity_scores, key=lambda x: x[1], reverse=True),
        feasibility=compute_feasibility(required_changes),
        insight=generate_insight(required_changes, sensitivity_scores)
    )
```

---

## 7. 与收敛层的兼容性

| 方面 | 收敛层 | 发散层 | 兼容性 |
|------|--------|--------|--------|
| 数据模型 | nodes_v2 / edges_v2 | 新增 counterfactual_log / abductive_hypothesis / analogical_matches / inverted_causality / constraint_sensitivity / **node_activation** | 完全兼容，新增表不影响旧表 |
| 判定输出 | IsomorphismVerdict | DoubtReport / Hypothesis / AnalogyMatch | 独立数据类型，不冲突 |
| 验证流程 | 正向演绎 | 反事实/溯因/类比 → 送回收敛层验证 | 闭环，发散层不替代收敛层 |
| 持久化 | SQLite | SQLite（新增表） | 同一数据库 |

---

## 8. 风险与边界

| 风险 | 描述 | 缓解 |
|------|------|------|
| 发散爆炸 | 假设生成过多，系统无法收敛 | 元认知仲裁层预算控制 |
| 虚假怀疑 | 对明显正确的链路也生成怀疑 | 临界值过滤（criticality > 0.8 才报告） |
| 循环发散 | 发散 → 收敛 → 再发散，无限循环 | 单次发散最多 3 轮，记录历史避免重复 |
| 无节点支撑 | 17 节点太少，溯因找不到候选 | 先扩展节点到 50+，或降低候选阈值 |
| 跨域无数据 | 当前只有振动控制域，类比无目标 | LLM 常识补全 + 爬虫验证（见 8.5.2） |
| **倒置因果过度发散** | **假设结果过于荒谬，约束变化不切实际** | **feasibility_score 过滤（<0.1 直接丢弃）+ CVE 价值评估（见 8.5.1）** |
| **约束敏感性误判** | **移除约束后结果变化不明显，误判为不敏感** | **多次测试+统计显著性检验** |
| **双权重参数敏感** | **λ 过大导致所有节点快速休眠，过小导致无剪枝** | **默认 λ=0.5，提供调参接口，按领域校准** |
| **激活度局部最优** | **高频节点垄断扩散起点，新节点永无机会** | **引入探索-利用权衡：ε-greedy 随机采样低激活节点** |
| **遗忘过度** | **长期项目中断后重新启动，核心知识已休眠** | **关键节点（L1 公理）标记为 permanent，不遗忘** |
| **LLM 幻觉污染** | **LLM 生成的类比/评估缺乏事实锚点** | **强制爬取验证，标记 is_hypothetical（见 8.5.2）** |
| **规则与 LLM 冲突** | **规则引擎和 LLM 给出矛盾决策** | **加权融合 + 历史准确率自适应调整权重（见 8.5.3）** |

---

## 8.5 深层问题与升级方案

### 8.5.1 约束价值评估器 (CVE)

**问题：约束修改容易落入"自欺欺人"**

Layer 4 的约束修改目前只判断"是否可行"，不判断"是否有价值"。典型陷阱：

| 调整类型 | 示例 | 问题 | 应归类 |
|---------|------|------|--------|
| 环境简化 | "将多频振动简化为单频" | 问题变简单了，不是解决了 | Type-C：条件作弊 |
| 预算提升 | "传感器从4路增加到40路" | 用资源堆砌替代算法创新 | Type-C：条件作弊 |
| 要求降低 | "精度从1μm放宽到10μm" | 降低标准不等于提升能力 | Type-C：条件作弊 |
| 算法升级 | "FxLMS → 分谐波MIMO" | 真正的结构创新 | Type-A：技术创新 |
| 工艺优化 | "FPGA时钟从50MHz提升到100MHz" | 工程调优，非核心突破 | Type-B：工程优化 |

**CVE 三维度评估：**

```python
class ConstraintValueEvaluator:
    def evaluate(self, change: ConstraintChange, context: DomainContext) -> ValueVerdict:
        """
        1. 创新度 (novelty): 是否引入新的物理机制、数学结构或算法范式
        2. 代价比 (cost_ratio): 收益提升 vs 资源增加的比率
        3. 通用性 (generality): 调整是否仅适用于特定条件，还是可推广
        """
        novelty = self._check_novelty(change, context)
        # - 引入新的物理原理 → high
        # - 在现有框架内调参 → low
        # - 降低要求/简化环境 → zero/negative
        
        cost_ratio = self._compute_cost_ratio(change, context)
        # - 收益+3dB，成本×1.2 → 优良
        # - 收益+0.5dB，成本×10 → 劣化
        
        generality = self._check_generality(change, context)
        # - 适用于任意环境 → high
        # - 仅适用于特定条件 → low
        # - 仅适用于理想化简化条件 → zero
        
        if novelty > 0.6 and cost_ratio > 1.0 and generality > 0.4:
            return ValueVerdict.TYPE_A_TECHNOLOGY
        elif novelty < 0.3 and cost_ratio > 1.5 and generality > 0.6:
            return ValueVerdict.TYPE_B_ENGINEERING
        elif novelty < 0.1 or cost_ratio < 0.5 or generality < 0.2:
            return ValueVerdict.TYPE_C_CHEATING
        else:
            return ValueVerdict.TYPE_D_UNCERTAIN  # 送LLM深度评估
```

**LLM 协同判定（针对 Type-D 不确定）：**

```python
def llm_value_judge(change: ConstraintChange, context: DomainContext) -> ValueVerdict:
    prompt = f"""
    领域：{context.domain}
    当前约束：{change.current_constraint}
    提议修改：{change.proposed_change}
    预期收益：{change.expected_gain}
    所需资源：{change.required_resources}
    
    请判断此约束修改的类型：
    A. 技术创新 —— 引入新的物理/数学/算法原理
    B. 工程优化 —— 在现有框架内的调参/工艺改进
    C. 条件作弊 —— 简化问题、降低标准、堆砌资源
    D. 无法判断 —— 信息不足
    
    要求：
    1. 说明判定理由（2-3句话）
    2. 引用类似历史案例（如有）
    3. 如果选C，明确指出"这在本质上等于把问题变简单"
    """
    return parse_verdict(llm.generate(prompt))
```

**与倒置因果的耦合：**

```json
{
  "feasibility_score": 0.35,
  "value_score": 0.72,
  "value_verdict": "TYPE_A",
  "value_reason": "分谐波MIMO引入新的物理结构，非简单调参"
}
```

只有 `feasibility > 0.2` 且 `value_verdict != TYPE_C` 的假设才会进入报告。

---

### 8.5.2 跨域类比：LLM 补全 + 爬取验证

**问题：多域数据稀疏，Layer 3 空转**

**方案：**

```python
class CrossDomainAnalogyWithLLM:
    def generate_analogy(self, source_path: str, source_domain: str) -> list[AnalogyMatch]:
        # Step 1: LLM 基于常识生成候选目标域
        prompt = f"""
        源领域：{source_domain}
        源结构：{source_path}
        结构签名：{self._extract_signature(source_path)}
        
        问题：哪些其他领域可能存在拓扑或功能同构的结构？
        请列出3-5个候选领域，并说明同构理由。
        """
        candidates = llm.generate(prompt)
        
        # Step 2: 对每个候选，爬取验证
        for candidate in candidates:
            query = f"{candidate.domain} {candidate.proposed_structure}"
            papers = crawler.search(query, limit=5)
            
            if papers:
                candidate.confidence = min(0.8, 0.5 + len(papers) * 0.1)
                candidate.evidence = papers
            else:
                candidate.confidence = 0.3
                candidate.is_hypothetical = True
        
        return [c for c in candidates if c.confidence > 0.3]
```

**关键约束：**
- LLM 生成的类比必须经爬取验证，否则标记 `is_hypothetical=True`
- 假设性类比不进入核心报告，只进入"待验证假设"队列
- 用户可选择"接受假设性类比"作为发散提示，但不作为结论

---

### 8.5.3 元认知仲裁：规则 + LLM 协同

**问题：纯规则判断缺少概率推理和领域知识**

**混合仲裁器架构：**

```
┌─────────────────────────────────────────────────────────────┐
│                    元认知仲裁层 v2.0                         │
├─────────────────────────────────────────────────────────────┤
│  规则引擎（确定性层）          LLM 评估器（概率层）          │
│  ├─ 停滞检测 (depth≥3)        ├─ 发散价值预判              │
│  ├─ 用户指令                  ├─ 领域可行性评估            │
│  ├─ 预算硬上限                ├─ 创新度预评分              │
│  └─ 视角冲突                  └─ 历史成功率加权            │
│                                                             │
│  ↓                    ↓                                     │
│   final_score = w_rule × rule_out + w_llm × llm_prob       │
│   默认: w_rule=0.6, w_llm=0.4                               │
└─────────────────────────────────────────────────────────────┘
```

**LLM 仲裁器输入：**

```python
class LLMArbiter:
    def evaluate(self, ctx: ArbitrationContext) -> float:
        prompt = f"""
        当前领域：{ctx.domain}
        用户问题：{ctx.user_query}
        收敛结论：{ctx.convergent_result.path}，置信度 {ctx.convergent_result.confidence}
        历史发散：{ctx.divergent_history}
        系统状态：预算 {ctx.system_state.budget}，已发散 {ctx.system_state.divergence_rounds} 轮
        
        请判断：此时应该继续发散，还是收敛确认？
        输出0-1的概率（0=立即收敛，1=全力发散），并说明理由。
        """
        return parse_probability(llm.generate(prompt, temperature=0.3))
```

**动态权重调整：**

```python
if history_accuracy("rule") > history_accuracy("llm"):
    w_rule = min(0.9, w_rule + 0.05)
else:
    w_llm = min(0.9, w_llm + 0.05)
w_llm = 1.0 - w_rule
```

**关键约束：**
- LLM 不替代规则硬约束（预算上限、用户指令优先级最高）
- LLM 只影响"软决策"（是否值得发散、发散深度、预算分配）
- 所有 LLM 决策记录日志，定期 review 准确率

---

**收敛层是"法官"——判定 A→B→C 是否有罪。发散层是"辩护律师"——质问"为什么不是 A→D→C？""B 和 D 之间差了什么？""其他领域是否已有 A'→D'→C' 的先例？""如果我不接受这个判决，我需要挑战哪些证据？"两者缺一不可：没有法官，世界混乱；没有律师，正义盲目。**

---

*版本: v0.3-REV*  
*日期: 2026-06-18*  
*学术基础: Counterfactual KG Reasoning (Zellinger 2024) + AbductiveKGR (Bai 2024) + DARK (2026) + Analogical Reasoning (Chan & Schunn 2014) + BVSR (Simonton 2013) + ACT-R (Anderson 2004) + Inverse CSP + Pearl Do-Calculus + Abductive Learning (Zhou et al.)*  
*升级: 双权重激活 + CVE约束价值评估 + LLM协同跨域类比 + 混合仲裁器 + 约束空间映射引擎 + 概念退化机制 + 协同层展望*  
*状态: 草案，已整合评审意见*

---

## 8.6 约束空间映射引擎 (Constraint Space Mapper, CSM)

### 8.6.1 元哲学声明

**"两个领域最大的区别就是约束的调整。"**

这不是说"所有问题都一样"——那是空洞的废话。而是说：

> **问题的结构由其约束集合定义。领域A与领域B的差异，等价于它们约束集合在约束空间中的距离。跨域创新的本质，是在约束空间中寻找一条可行路径，将领域A连续变形到领域B的邻域。**

### 8.6.2 形式化框架

**定义 1：约束空间**

```
Ω = {C | C = {c₁, c₂, ..., cₙ}，每个 cᵢ 是一个约束条件}
```

**定义 2：可行域**

```
F ⊂ Ω = {C ∈ Ω | C 对应真实可实现的物理/工程条件}
```

关键区分：
- `C ∈ F`：约束对应真实世界（如"4路加速度传感器"）
- `C ∉ F`：约束是虚构的（如"忽略重力"在地面系统中）

**定义 3：约束距离**

```
d(C₁, C₂) = 1 − cosine_sim(embedding(C₁), embedding(C₂))
```

其中 `embedding(C)` 通过 LLM 将约束集合编码为语义向量。

**定义 4：约束变形路径**

```
γ: [0,1] → Ω，γ(0) = C_s（源领域），γ(1) = C_t（目标领域）
```

**命题：领域可打通性**

```
D_s 与 D_t 可打通 ⇔ ∃ γ: [0,1] → F，使得 γ(0) = C_s，γ(1) = C_t
                      且 ∀ t∈[0,1]，CVE(γ(t) − γ(t−ε)) ≠ TYPE_C
```

即：两个领域之间存在一条完全落在可行域内的约束变形路径，且路径上的每一步调整都不是"条件作弊"。

### 8.6.3 机制设计

```python
class ConstraintSpaceMapper:
    """
    约束空间映射引擎：发现"调整后的源领域 ≈ 已知目标领域"的匹配。
    """
    
    def __init__(self, domain_library: dict[str, ConstraintSet], 
                 embedding_model: EmbeddingModel,
                 cve: ConstraintValueEvaluator):
        self.domain_lib = domain_library
        self.embed = embedding_model
        self.cve = cve
    
    def map(self, source_domain: str, source_constraints: ConstraintSet,
            delta_candidates: list[ConstraintChange]) -> list[ConstraintMatch]:
        """
        输入：源领域 + Layer 4 生成的 ΔC 候选
        输出：跨域匹配列表，按匹配质量排序
        """
        matches = []
        
        for delta in delta_candidates:
            # Step 1: CVE 预过滤 —— 只处理 Type-A/B 的调整
            value = self.cve.evaluate(delta, DomainContext(source_domain))
            if value.verdict == ValueVerdict.TYPE_C_CHEATING:
                continue
            
            # Step 2: 计算调整后的约束集合
            adjusted = source_constraints.apply(delta)
            
            # Step 3: 与领域库匹配
            for domain_name, target_constraints in self.domain_lib.items():
                if domain_name == source_domain:
                    continue
                
                distance = self._constraint_distance(adjusted, target_constraints)
                
                if distance < self.match_threshold:
                    matches.append(ConstraintMatch(
                        source_domain=source_domain,
                        target_domain=domain_name,
                        delta=delta,
                        adjusted_constraints=adjusted,
                        distance=distance,
                        value_verdict=value.verdict,
                        path_feasible=self._check_path_feasibility(
                            source_constraints, adjusted, target_constraints
                        )
                    ))
        
        matches.sort(key=lambda m: m.distance)
        return matches
    
    def _constraint_distance(self, c1: ConstraintSet, c2: ConstraintSet) -> float:
        v1 = self.embed.encode(c1.to_text())
        v2 = self.embed.encode(c2.to_text())
        return 1.0 - cosine_similarity(v1, v2)
    
    def _check_path_feasibility(self, start: ConstraintSet, 
                                mid: ConstraintSet, 
                                end: ConstraintSet) -> bool:
        for alpha in [0.0, 0.25, 0.5, 0.75, 1.0]:
            interpolated = start.interpolate(end, alpha)
            if not interpolated.is_physically_realizable():
                return False
        return True
```

### 8.6.4 与现有模块的耦合

```
Layer 4（倒置因果）
    ↓ 输出 ΔC 候选
CVE（约束价值评估）
    ↓ 过滤 Type-C，保留 Type-A/B
CSM（约束空间映射）
    ↓ 发现 "C_s + ΔC ≈ C_t"
DAE（差异分析引擎）← 新增
    ↓ 分析未对齐约束的"差异类型"
Layer 3（跨域类比）
    ↓ 验证结构同构 + 爬取支撑
元认知仲裁
    ↓ 决定是否深入探索
报告输出
```

---

### 8.6.5 差异分析引擎 (Difference Analysis Engine, DAE)

#### 学术基础：Structure-Mapping Theory (Gentner, 1983)

**核心洞察：** 类比不是简单的相似匹配，而是**结构对齐**（structural alignment）。对齐完成后，真正有价值的不是"匹配了什么"，而是**未匹配的部分**——它们定义了迁移需要克服的障碍。

> "The output of SME includes a structural evaluation score and **candidate inferences** which are conjectures about the target using expressions from the base which, while unmapped in their entirety, have subcomponents that participate in the mapping's correspondences."  
> — Klenk et al. (2009), *Domain Transfer via Cross-Domain Analogy*

#### 机制设计

```python
class DifferenceAnalysisEngine:
    """
    差异分析引擎：识别对齐后的未匹配约束，分类差异类型，生成推理策略。
    对应 SMT 中的 "candidate inferences" 阶段。
    """
    
    def __init__(self, physics_knowledge_base: PhysicsKB):
        self.physics_kb = physics_knowledge_base
    
    def analyze(self, match: ConstraintMatch) -> DifferenceReport:
        """
        输入：CSM 生成的匹配结果
        输出：差异分析报告，包含未匹配约束的分类和推理策略
        """
        source = match.source_constraints
        target = match.target_constraints
        
        # Step 1: 精确对齐 —— 找出约束一一对应
        aligned_pairs, unmatched_source, unmatched_target = self._align(source, target)
        
        # Step 2: 对未匹配约束分类差异类型
        discrepancies = []
        
        for c in unmatched_source + unmatched_target:
            d_type = self._classify_discrepancy(c, aligned_pairs, match)
            discrepancies.append(Discrepancy(
                constraint=c,
                type=d_type,
                severity=self._severity(d_type, c),
                strategy=self._reasoning_strategy(d_type, c, match)
            ))
        
        # Step 3: 按严重程度排序
        discrepancies.sort(key=lambda d: d.severity, reverse=True)
        
        return DifferenceReport(
            match=match,
            aligned_pairs=aligned_pairs,
            discrepancies=discrepancies,
            transfer_feasibility=self._compute_transfer_feasibility(discrepancies),
            key_blockers=[d for d in discrepancies if d.severity > 0.8]
        )
    
    def _align(self, source: ConstraintSet, target: ConstraintSet) -> tuple:
        """
        基于语义+量纲的精确对齐。对应 SMT 的 "one-to-one correspondence" 约束。
        """
        aligned = []
        unmatched_src = []
        unmatched_tgt = list(target.constraints)
        
        for s in source.constraints:
            best_match = None
            best_score = 0.0
            
            for t in unmatched_tgt:
                score = self._alignment_score(s, t)
                if score > 0.7 and score > best_score:  # 阈值
                    best_match = t
                    best_score = score
            
            if best_match:
                aligned.append((s, best_match))
                unmatched_tgt.remove(best_match)
            else:
                unmatched_src.append(s)
        
        return aligned, unmatched_src, unmatched_tgt
    
    def _alignment_score(self, c1: Constraint, c2: Constraint) -> float:
        """
        对齐评分：语义相似度 + 量纲兼容性 + 物理角色一致性。
        """
        semantic = cosine_sim(self.embed(c1.description), self.embed(c2.description))
        dimensional = self._dimensional_compatibility(c1.physics_type, c2.physics_type)
        role = 1.0 if c1.role == c2.role else 0.3  # 角色：传感器/执行器/控制器...
        
        return 0.5 * semantic + 0.3 * dimensional + 0.2 * role
    
    def _classify_discrepancy(self, c: Constraint, aligned_pairs: list, match: ConstraintMatch) -> DiscrepancyType:
        """
        差异类型分类：对应 "candidate inferences" 的触发条件。
        """
        # 查找对齐对中最相似的约束，作为参照
        ref = self._find_most_similar(c, aligned_pairs)
        
        if ref and c.physics_type == ref.physics_type:
            # 物理类型相同，仅参数不同
            return DiscrepancyType.TYPE_A_PARAMETRIC
        
        elif ref and c.physics_type != ref.physics_type:
            # 物理类型不同，但功能角色相同（如加速度计 vs 压力传感器）
            return DiscrepancyType.TYPE_B_DIMENSIONAL
        
        elif not ref and c.role == "structural":
            # 无对应参照，且是结构性约束
            return DiscrepancyType.TYPE_C_STRUCTURAL
        
        else:
            # 目标域有但源域无，或反之
            return DiscrepancyType.TYPE_D_MISSING
    
    def _reasoning_strategy(self, d_type: DiscrepancyType, c: Constraint, match: ConstraintMatch) -> ReasoningStrategy:
        """
        针对差异类型，生成推理策略。对应 SMT 的 "candidate inferences"。
        """
        if d_type == DiscrepancyType.TYPE_A_PARAMETRIC:
            return ReasoningStrategy(
                action="参数重校准",
                method=f"将 {c.name} 的参数从 {c.current_value} 调整到目标域推荐值",
                confidence=0.85,
                evidence="物理类型相同，仅需数值调参",
                effort="低（1-2天）"
            )
        
        elif d_type == DiscrepancyType.TYPE_B_DIMENSIONAL:
            return ReasoningStrategy(
                action="物理量转换",
                method=f"建立 {c.physics_type} ↔ {self._find_ref(c).physics_type} 的物理转换模型",
                confidence=0.60,
                evidence=f"{c.name} 与 {self._find_ref(c).name} 功能角色相同但量纲不同，需通过物理模型桥接",
                effort="中（1-2周）",
                risk="量纲转换可能引入非线性失真"
            )
        
        elif d_type == DiscrepancyType.TYPE_C_STRUCTURAL:
            return ReasoningStrategy(
                action="架构重构",
                method=f"解耦/重构 {c.name} 相关的系统结构，从 {match.source_domain} 模式迁移到 {match.target_domain} 模式",
                confidence=0.40,
                evidence="结构性差异通常涉及多组件耦合，需要重新设计信号流",
                effort="高（1-2月）",
                risk="架构重构可能破坏现有收敛性保证"
            )
        
        elif d_type == DiscrepancyType.TYPE_D_MISSING:
            return ReasoningStrategy(
                action="组件引入",
                method=f"在源域中引入 {c.name} 等价组件，或证明该组件非必要",
                confidence=0.50,
                evidence="目标域存在而源域缺失的组件，可能是关键使能技术",
                effort="中-高（2-4周）",
                risk="新增组件可能引入未建模动态"
            )
    
    def _compute_transfer_feasibility(self, discrepancies: list[Discrepancy]) -> float:
        """
        综合迁移可行性：基于差异类型和严重程度加权。
        """
        weights = {
            DiscrepancyType.TYPE_A_PARAMETRIC: 0.1,
            DiscrepancyType.TYPE_B_DIMENSIONAL: 0.3,
            DiscrepancyType.TYPE_C_STRUCTURAL: 0.6,
            DiscrepancyType.TYPE_D_MISSING: 0.4
        }
        
        total_penalty = sum(
            weights[d.type] * d.severity 
            for d in discrepancies
        )
        
        return max(0.0, 1.0 - total_penalty)
```

#### 差异类型说明

| 类型 | 描述 | 示例 | 推理策略 | 置信度 | 工作量 |
|------|------|------|---------|--------|--------|
| **Type-A 参数差异** | 物理类型相同，仅数值不同 | 采样率 10kHz vs 50kHz | 参数重校准 | 高 (0.85) | 低 |
| **Type-B 量纲差异** | 功能角色相同，物理量不同 | 加速度计 vs 压力传感器 | 物理量转换模型 | 中 (0.60) | 中 |
| **Type-C 结构差异** | 系统架构不同 | 单轴 ANC vs 多轴 MIMO | 架构重构 | 低 (0.40) | 高 |
| **Type-D 缺失差异** | 目标域有但源域无 | 源域无温度补偿模块 | 组件引入或必要性证明 | 中 (0.50) | 中-高 |

#### 与 FxLMS 案例的映射

```
CSM 匹配：机床振动控制 + 在线辨识 ≈ 航空发动机主动减振（distance=0.22）

DAE 分析：

对齐对（aligned）：
  ├─ 宽频随机激励 ≈ 宽频随机激励（Type-A，参数微调）
  ├─ 实时性要求 <100μs ≈ 实时性要求 <50μs（Type-A，参数调整）
  └─ 多轴耦合 ≈ 多轴耦合（Type-A，轴数不同）

未匹配约束（discrepancies）：
  ├─ [源域] 切削热时变温度场 → [目标域] 燃烧室高温梯度
  │   └── Type-B（量纲差异：温度场梯度 vs 高温梯度）
  │   └── 策略：建立温度-热变形的统一物理模型
  │   └── 置信度：0.65
  │
  ├─ [源域] 机械迟滞非线性 → [目标域] 叶片气动弹性非线性
  │   └── Type-B（量纲差异：机械迟滞 vs 气动弹性）
  │   └── 策略：非线性建模框架迁移（Lyapunov 稳定性通用）
  │   └── 置信度：0.70
  │
  ├─ [目标域] 转速同步触发（源域无）
  │   └── Type-D（缺失差异）
  │   └── 策略：引入编码器同步触发，或证明切削过程无需转速同步
  │   └── 置信度：0.50
  │
  └─ [源域] 4路加速度计 → [目标域] 多通道压力+应变传感器融合
      └── Type-B（量纲差异：加速度 vs 压力/应变）
      └── 策略：建立多传感器融合框架（Kalman 滤波通用）
      └── 置信度：0.60

迁移可行性：0.68（有3个Type-B + 1个Type-D，无Type-C）
关键障碍：传感器量纲转换（Type-B × 3）
核心洞察：航空发动机的 Kalman 多传感器融合策略可直接适配机床的加速度+温度+力传感器融合
```

#### 持久化扩展

```sql
CREATE TABLE IF NOT EXISTS difference_analysis (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    constraint_name TEXT NOT NULL,
    discrepancy_type TEXT CHECK(discrepancy_type IN ('TYPE_A_PARAMETRIC', 'TYPE_B_DIMENSIONAL', 'TYPE_C_STRUCTURAL', 'TYPE_D_MISSING')),
    severity REAL,                    -- 0-1
    strategy_action TEXT,             -- 推理策略：参数重校准/物理量转换/架构重构/组件引入
    strategy_method TEXT,             -- 具体方法描述
    confidence REAL,                  -- 策略置信度
    effort_estimate TEXT,             -- 工作量估计
    risk_note TEXT,                   -- 风险说明
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES constraint_space_matches(id)
);

CREATE INDEX idx_diff_type ON difference_analysis(discrepancy_type);
CREATE INDEX idx_diff_severity ON difference_analysis(severity);
```

---

**源领域：机床振动控制**

```
C_s = {
  "多轴耦合 (X/Y/Z/A/C五轴)",
  "宽频随机激励 (20-500Hz)",
  "时变温度场 (切削热+环境)",
  "机械迟滞非线性",
  "传感器受限 (4路加速度计)",
  "实时性要求 (<100μs控制周期)"
}
```

**Layer 4 生成 ΔC 候选：**

| ΔC | 操作 | 调整后约束 | CVE判定 | 说明 |
|----|------|-----------|---------|------|
| ΔC₁ | 移除:多轴耦合 | 单轴+单频 | **TYPE_C** | 机床不可能变单轴 |
| ΔC₂ | 替换:宽频→窄带 | 单频正弦激励 | **TYPE_C** | 实际切削是宽频 |
| ΔC₃ | 添加:恒温控制 | 温度恒定 | TYPE_B | 工程可行，成本增加 |
| ΔC₄ | 替换:机械迟滞→线性 | 线性模型 | **TYPE_C** | 物理上不存在 |
| ΔC₅ | 添加:在线辨识 | S_est实时更新 | TYPE_A | 算法创新 |
| ΔC₆ | 替换:4路→40路 | 传感器冗余 | TYPE_B | 工程优化 |

**CSM 匹配（仅处理 Type-A/B）：**

```
C_s + ΔC₃ = {
  "多轴耦合",
  "宽频随机激励",
  "温度恒定 ← 新增",
  "机械迟滞",
  "4路加速度计",
  "<100μs"
}

匹配目标域：精密光学平台振动控制（distance=0.28）
  - 同样有宽频激励
  - 同样有传感器受限
  - 但光学平台通常恒温
  - 洞察：温度控制可能是机床振动控制被忽视的关键

C_s + ΔC₅ = {
  "多轴耦合",
  "宽频随机激励",
  "时变温度",
  "机械迟滞",
  "4路加速度计",
  "<100μs",
  "S_est在线辨识 ← 新增"
}

匹配目标域：航空发动机主动减振（distance=0.22）
  - 时变工况（转速变化）→ 必须在线辨识
  - 多传感器融合
  - 宽频随机 + 时变 → 与机床高度相似
  - 洞察：航空发动机的在线辨识策略可能直接适用于机床
```

**关键洞察：**

不是"机床振动 = ANC"——那是错误的简化。而是：

> **"机床振动控制 + 在线辨识约束 ≈ 航空发动机主动减振"**
>
> 这个等式在约束空间中有精确的距离度量（0.22），且变形路径上的每一步（添加在线辨识模块）都是 Type-A 技术创新，不是 Type-C 条件作弊。

这意味着：航空发动机领域已经验证的在线辨识策略，可以被"迁移"到机床振动控制中，而不需要重新发明。

### 8.6.6 与"打通两者约束差距"的关系

**"打通" ≠ "等同"**

- 错误理解："机床和ANC是一样的，只是约束不同" → 无视领域特殊性
- 正确理解："机床和ANC在约束空间中的距离是 d，存在一条可行路径 γ 连接它们，路径长度 = 需要调整的创新点数量"

**"打通"的价值度量：**

```
打通价值 = 目标域的成功经验价值 / (路径长度 × 路径可行性)
```

- 路径短 + 可行 → 高价值（直接迁移）
- 路径长 + 可行 → 中等价值（需要系列创新）
- 路径短但不可行（含Type-C）→ 零价值（自欺欺人）

### 8.6.7 持久化扩展

```sql
CREATE TABLE IF NOT EXISTS constraint_space_matches (
    id TEXT PRIMARY KEY,
    source_domain TEXT NOT NULL,
    target_domain TEXT NOT NULL,
    source_constraints TEXT,
    delta_change TEXT,
    adjusted_constraints TEXT,
    distance REAL,
    path_feasible INTEGER,
    value_verdict TEXT,
    insight TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_csm_distance ON constraint_space_matches(distance);
CREATE INDEX idx_csm_source ON constraint_space_matches(source_domain);
```

---

## 8.7 概念退化机制与协同层展望

### 8.7.1 问题陈述

当前 ACT-R 激活机制处理的是"高频+新近 = 保留，低频+久远 = 遗忘"。但这忽略了一个关键问题：**被遗忘的概念怎么办？**

简单删除是最粗暴的方案。人类遗忘不是彻底抹除——复杂概念衰退为基础元素，"模糊化"后回归更原始的认知结构。

> 例如：你学了 "Kalman Filter"，长期不用后，你不是忘记了"滤波"这个概念，而是忘记了 Kalman Filter 的具体推导和实现细节。但"用观测修正估计"这个核心直觉，会回归到更基础的 "反馈" 概念中。

### 8.7.2 概念退化机制

**核心思想：** 当一个复合概念长期激活计数不增长时，不直接删除，而是将其"分解退化"为其组成元素。

**形式化定义：**

```
概念 C = f(A, B)  （如 KalmanFilter = Compose(Prediction, ObservationUpdate)）

if activation(C) < θ_forget and access_count(C) 连续 N 个周期零增长:
    → 触发退化操作 Decompose(C)
    → C 的语义属性分配到 A 和 B 中
    → C 作为独立节点被标记为 "degraded"
    → A 和 B 的激活度获得 boost（因为继承了 C 的部分语义）
```

**退化策略：**

| 概念类型 | 退化方向 | 示例 |
|---------|---------|------|
| 复合算法 | 回归组成算子 | Kalman Filter → Prediction + Observation Update |
| 派生定理 | 回归基础公理 | 中心极限定理 → 大数定律 + 独立同分布 |
| 工程实现 | 回归算法抽象 | FPGA定点实现 → FxLMS算法 + 定点数约束 |
| 跨域类比 | 回归源域结构 | 热控→ANC类比 → 保留至热控/ANC各自域内 |

**退化与遗忘的区别：**

| 操作 | 结果 | 可逆性 |
|------|------|--------|
| 遗忘 | 节点删除，信息丢失 | 不可逆 |
| 退化 | 节点拆解，语义归并 | 部分可逆（通过检索历史可重建） |

### 8.7.3 协同层定位

概念退化不是收敛层的功能（收敛层只管验证），也不是发散层的功能（发散层只管怀疑和生成）。它属于**协同层**——一个尚未完整设计的、负责"系统健康维护"的层次。

**协同层的职责：**

1. **概念健康监测**：追踪每个节点的激活趋势，识别"僵尸概念"（长期无增长）
2. **退化调度**：决定何时退化、退化成什么、退化的粒度
3. **跨层协调**：确保退化后的概念在收敛层和发散层中同步更新
4. **记忆压缩**：类似人脑的睡眠 consolidation——将短期活跃模式压缩为长期结构化知识

**与现有层的关系：**

```
┌─────────────────────────────────────────────────┐
│                 应用层 (API / UI)                │
├─────────────────────────────────────────────────┤
│  收敛层 (Convergent)    发散层 (Divergent)       │
│  ────────────────       ────────────────        │
│  A→B→C 验证             A→B→C 破坏              │
│  规则校验               替代路径生成              │
├─────────────────────────────────────────────────┤
│  协同层 (Coordinative) —— 概念退化 + 系统健康    │
│  ─────────────────────────────────────────────   │
│  激活监测 → 退化判断 → 跨层同步 → 压缩归档       │
├─────────────────────────────────────────────────┤
│              持久化层 (Persistence)              │
└─────────────────────────────────────────────────┘
```

**协同层不是独立的"第三层"——它是渗透层。**

它不替代收敛或发散，而是在两者背后运行，像操作系统中的内存管理器：你不知道它在工作，直到它停止工作。

### 8.7.4 当前实现策略

协同层是一个**远期架构目标**。当前版本（v0.1）仅实现最基础的"计数监测"：

```python
# 伪代码——当前版本
class ConceptHealthMonitor:
    def check(self, node_id: str) -> str:
        """返回概念健康状态。"""
        activation = tracker.get_activation(node_id)
        count = tracker.get_access_count(node_id)
        
        if activation < theta_forget and count == 0:
            return "DEGRADED_CANDIDATE"  # 标记，不执行退化
        
        return "HEALTHY"
```

真正的退化逻辑（Decompose、语义归并、跨层同步）在 **v0.3+** 中实现。

### 8.7.5 持久化预留

```sql
-- 概念退化记录（v0.3+ 启用）
CREATE TABLE IF NOT EXISTS concept_degradation (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    degradation_type TEXT,       -- "decompose" | "merge" | "archive"
    source_concept TEXT,         -- 退化前的概念描述
    target_concepts TEXT,        -- JSON: ["A", "B"] 退化后的目标
    semantic_transfer TEXT,      -- JSON: 转移的语义属性
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    restored_at TIMESTAMP,       -- 如被恢复
    FOREIGN KEY (node_id) REFERENCES nodes(id)
);

-- 概念健康监控日志
CREATE TABLE IF NOT EXISTS concept_health_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    activation REAL,
    access_count INTEGER,
    status TEXT,                 -- "healthy" | "declining" | "degraded"
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 9. 一句话总结

**收敛层是"法官"——判定 A→B→C 是否有罪。发散层是"辩护律师"——质问"为什么不是 A→D→C？""B 和 D 之间差了什么？""其他领域是否已有 A'→D'→C' 的先例？""如果我不接受这个判决，我需要挑战哪些证据？"两者缺一不可：没有法官，世界混乱；没有律师，正义盲目。**

**约束空间映射引擎是"地质勘探队"——它不声称"所有山脉都一样"，而是测量"从这座山到那座山需要经过哪些地形、距离多远、路径是否可行"。**

---

## 10. 竞争力评估

### 10.1 现有方案全景

| 系统 | 核心定位 | 记忆模型 | 推理能力 | 开源 | Stars |
|------|---------|---------|---------|------|-------|
| **Mem0** | 轻量级记忆层 | 向量DB + 图提取 | 被动检索 | 是 | 51k |
| **Zep** | 时序知识图谱 | 时序KG (Graphiti) | 时间推理 | 是 | 4k |
| **Letta** | 分层内存OS | core/recall/archival | LLM分页管理 | 是 | 21k |
| **Cognee** | 自定义知识图谱 | 本体定义 + 图 | 结构化查询 | 是 | - |
| **KAG** | 逻辑推理引擎 | SPG + LLM | 混合推理 | 是 | - |
| **SAKE** | RL驱动知识外推 | KG triplets | 类比推理 | 是 | - |
| **AdaMKG** | 多模态企业KG | 多模态融合 | 跨模态检索 | 否 | - |
| **engramai** | 神经科学记忆 | ACT-R + Hebbian | 认知激活 | 是 | - |
| **A-MEM** | Zettelkasten笔记 | 原子笔记 + 链接 | 自动演化 | 是 | - |

### 10.2 差异化定位

**不是记忆系统，是认知引擎。**

Mem0/Zep/Letta 解决的是"记住什么"和"怎么记住"。当前设计解决的是"如何怀疑已记住的"和"如何在约束空间中发现新路径"。

| 维度 | 现有方案 | 当前设计 |
|------|---------|---------|
| **核心操作** | 存储 → 检索 → 生成 | 验证 → 怀疑 → 破坏 → 再验证 |
| **知识表示** | 实体-关系-属性 | 六层解构 (L1物理→L6失效) + 因果语义 |
| **跨域能力** | 向量相似匹配 | 约束空间映射 + 差异分析 |
| **防幻觉机制** | 引用溯源 | CVE价值评估 + 爬取验证 + 收敛层闭环 |
| **认知模型** | 无明确模型 | ACT-R + SMT + 溯因推理 |
| **目标用户** | 通用对话Agent | 工程师/研究者（需要物理可实现性） |

### 10.3 竞争力矩阵

| 能力 | 当前设计 | Mem0 | Zep | Letta | KAG | SAKE |
|------|---------|------|-----|-------|-----|------|
| 长期记忆 | ★★★☆☆ | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★☆☆ | ★★★☆☆ |
| 跨域推理 | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★★☆ |
| 结构怀疑 | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ | ★☆☆☆☆ | ★★☆☆☆ | ★★★☆☆ |
| 防自欺 | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★☆☆ |
| 物理可实现性 | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ | ★☆☆☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| 工程易用性 | ★★☆☆☆ | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ |
| 社区生态 | ★☆☆☆☆ | ★★★★★ | ★★★☆☆ | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ |

### 10.4 核心优势（不可替代性）

**1. CVE 防自欺机制 —— 独一无二**

现有系统没有"条件作弊"检测。Mem0 会忠实记录"用户喜欢简化问题"，但不会质疑"这是不是一种逃避"。当前设计的 Type-C 过滤是工程理性主义在 AI 系统中的首次形式化。

**2. 约束空间映射 —— 理论深度**

SAKE 也有类比推理，但它是基于 KG triplet 的语义相似。当前设计将领域差异定义为约束集合的距离，并引入可行域 F 的硬边界——这是物理/engineering-first 的思维方式，不是纯语义游戏。

**3. 六层解构 + 因果语义 —— 知识深度**

v5.0 的 L1-L6 知识模型要求每个概念回答"物理基础是什么、数学推导在哪、工程怎么实现、什么情况下会失败"。这比标准的 entity-relation-attribute 深一个数量级。

### 10.5 核心劣势（必须面对的）

**1. 工程复杂度极高**

Mem0 接入只需 5 行代码。当前设计需要：
- SQLite 6+ 张新表
- 4 个引擎（CVE/CSM/DAE/混合仲裁）
- LLM 调用链路（每轮发散至少 2-3 次 LLM 调用）
- 爬取验证基础设施

这不是"快速集成"的方案，是"深度改造"的方案。

**2. 无评估基准**

Mem0 有 LOCOMO，Zep 有 LongMemEval，Letta 有 Terminal-Bench。当前设计没有 benchmark。"防自欺"怎么量化？"约束空间距离"怎么验证？这是最大的学术/工程缺口。

**3. 依赖 LLM 的脆弱性**

CVE 的 Type-D 不确定需要 LLM 判定，DAE 的推理策略需要 LLM 生成，混合仲裁需要 LLM 评估。如果 LLM 本身产生幻觉，整个链条的置信度会级联衰减。

### 10.6 特殊性总结

| 特性 | 是否特殊 | 说明 |
|------|---------|------|
| 双权重激活 | ★★★☆☆ | engramai 也有 ACT-R，不是独创 |
| 四层发散 | ★★★★☆ | 组合了多种推理模式，但每层单独都有文献 |
| CVE 价值评估 | ★★★★★ | **独创**——工程理性主义的防自欺形式化 |
| 约束空间映射 | ★★★★★ | **独创**——将领域差异定义为约束距离 |
| DAE 差异分析 | ★★★★☆ | Gentner SMT 的扩展应用，有理论基础 |
| 六层解构 | ★★★★☆ | 独创框架，但层级思想（DIKW）是经典的 |

### 10.7 结论

当前设计在**理论层面**具备强竞争力——CVE + CSM + DAE 的组合在现有开源/商业方案中找不到直接对标。但在**工程层面**竞争力不足——实现复杂度过高、无 benchmark、社区生态为零。

**建议定位：**

不要与 Mem0/Letta 竞争"通用记忆层"。瞄准**工程师/研究者的认知副驾驶**——一个会质疑、会暴露约束盲区、会防止自欺的专用推理引擎。这个市场目前没有成熟产品。
