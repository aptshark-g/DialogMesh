# DialogMesh V4.0 — 认知坐标路由器 (Cognitive Coordinate Router)

> 2026-07-22 · 范式跃迁: 意图分类器 → 三维意图流形投影
>
> 吸收: STC句法复杂度 + 贝叶斯多源融合 + 文献12篇
> 前置: DESIGN_V3.2_ROUTING_MATRIX.md + DESIGN_MULTI_SIGNAL_INTENT.md

---

## 一、范式跃迁

```
V3.2 及之前:
  输入 → 特征提取 → 离散标签 (TOOL/ADVISOR/COMPANION/UNKNOWN)
  问题: 离散标签无法表达意图的连续性, 硬编码列表永远不够

V4.0:
  输入 → 特征提取 → 连续坐标 (X,Y,Z) → 空间区域 → 路由策略
  优势: 无数个意图点映射到同一个坐标系, 标签体系自动泛化
```

**核心**: 系统不再判断"这是 TOOL 还是 ADVISOR"，而是判断"这个点在三维空间的哪个区域"。

---

## 二、三维坐标系定义

三个轴正交且不可再分——穷尽了"输入→过程→输出"的整个闭环。

```mermaid
graph TD
    subgraph AXES["三维认知坐标"]
        X["X轴: 认知距离<br/>0=母语级常识 → 1=外星人黑话<br/>Input: 系统存了相关知识吗？"]
        Y["Y轴: 操作粒度<br/>0=单细胞动作 → 1=千层饼逻辑<br/>Process: 需要多少步推理？"]
        Z["Z轴: 反馈期望<br/>-1=镜子 → 0=探索 → +1=求解<br/>Output: 产出的主观价值是什么？"]
    end

    X --> SPACE["三维意图流形<br/>Intent Manifold"]
    Y --> SPACE
    Z --> SPACE
    
    SPACE --> ROUTE["路由决策<br/>坐标点 → 最近区域 → 预设策略"]
```

---

## 三、三轴计算公式

### 3.1 X轴: 认知距离 (0.0 ~ 1.0)

**骨架映射**: S1-a (SVO语义引力) + 词汇罕见度修正

```
Step 1: BGE 编码主语(S) 和 宾语(O)
Step 2: 语义引力 G = 1 - Cosine(S_vec, O_vec)

Step 3: IDF 修正 (论文: TF-IDF比纯语义更敏感)
  IDF_avg = 当前对话日志中 S 和 O 的 IDF 均值

X = Clip( G × 0.7 + IDF_avg × 0.3, 0, 1 )
```

物理含义:
- X=0.1: "打开文件" (同域, 常见词)
- X=0.5: "用量子退火优化物流" (跨域, 有一定关联)
- X=0.9: "费马大定理在椭圆曲线加密中的应用" (远跨域, 罕见术语)

---

### 3.2 Y轴: 操作粒度 (0.0 ~ 1.0)

**骨架映射**: S1-b (句法地形复杂度 STC) → 计算节点熵

```
Step 1: Stanza 依存解析
Step 2: 提取三个特征:
  D = 最大嵌套深度 (Root → Leaf 最长路径)
  C = 并列连词数 ("且/或/并/and/or")
  P = 约束密度 (介词/状语数量 / 总Token数)

Step 3: 计算节点熵
Y = Sigmoid( D×0.4 + C×0.4 + P×10×0.2 )
```

物理含义:
- Y=0.05: "查天气" (无依存关系, 原子查询)
- Y=0.6: "重构并测试代码" (D=4, C=1, 中度流程)
- Y=0.95: "虽然延迟飙升但若监控未报错且历史基线正常则检查网络" (D=7, C=3)

---

### 3.3 Z轴: 反馈期望 (-1.0 ~ +1.0)

**骨架映射**: 句法语气 + 探针峭度 + 认知节律 (三信号联合解码)

```
信号A (50%): 句法语气
  - 首词=吗/多少/Is/Are/Do → +1 (求解)
  - 疑问词=如何/为什么/怎么 → 0 (启发)
  - 情绪密集=烂透了/太棒了/太烦了 → -1 (镜子)

信号B (30%): 探针峭度 K
  - K极高(概率尖锐) → 偏向求解 (+1方向)
  - K极低(概率平坦) → 偏向探索 (0方向)

信号C (20%): 认知节律 λ
  - 高觉醒(am 9-11) → 偏向求解
  - 低觉醒(pm 14-16) → 偏向探索/倾诉

Z = A×0.5 + K_norm×0.3 + λ_bias×0.2
```

物理含义:
- Z=+0.9: "这个地址是不是虚函数表指针？给出确切答案" (求解)
- Z=0.0: "有没有什么思路来分析这个加密算法？" (探索)
- Z=-0.8: "做了三天逆向整个人都废了，太难了" (镜子)

---

## 四、路由决策: 坐标→区域→策略

不再离散标签，改为球面区域匹配:

```python
def route(x: float, y: float, z: float) -> RoutingDecision:
    """三维坐标 → 最近路由区域 → 预设策略"""
    
    # 原子域: 极近 + 极简
    if x < 0.2 and y < 0.2:
        return RoutingDecision(
            zone="ATOMIC",
            strategy="cache_or_rule",
            llm="none",
            cost="~0ms",
        )
    
    # 深渊域: 极远 + 极深 + 求解
    if x > 0.7 and y > 0.7 and z > 0.5:
        return RoutingDecision(
            zone="ABYSS",
            strategy="full_react_cot",
            llm="primary_model",
            max_recursion=5,
            cost="500-2000ms",
        )
    
    # 心理域: 镜子模式
    if z < -0.5:
        return RoutingDecision(
            zone="PSYCHE",
            strategy="empathetic_listening",
            llm="local_small_model",
            forbid_technical=True,
            cost="50-200ms",
        )
    
    # 精密域: 近 + 深 + 求解
    if x < 0.5 and y > 0.5 and z > 0:
        return RoutingDecision(
            zone="PRECISION",
            strategy="planner_agent",
            llm="primary_model",
            output_format="structured_json",
            cost="200-800ms",
        )
    
    # 探索域: 远 + 浅 + 探索
    if x > 0.5 and y < 0.5 and z <= 0:
        return RoutingDecision(
            zone="EXPLORE",
            strategy="socratic_heuristic",
            llm="primary_model",
            temperature=0.7,
            cost="100-400ms",
        )
    
    # 默认: 混合域
    return RoutingDecision(
        zone="MIXED",
        strategy="balanced",
        llm="primary_model",
        cost="100-500ms",
    )
```

---

## 五、后验校准: 用户反馈→系数微调

```
不调语义模型。调三个公式的线性权重。

用户点踩时:
  当前路由: zone=EXPLORE (远+浅+探索)
  但实际应该是: zone=PRECISION (近+深+求解)
  
→ 反向传播:
  1. X轴: IDF权重 +0.02 (语义距离被低估了)
  2. Y轴: 并列词权重 +0.03 (操作粒度被低估了)
  3. Z轴: 句法语气权重 +0.01 (求解信号被低估了)
  
→ 下次相似输入, 坐标自动修正到 PRECISION 区域
```

**本质**: 在拟合用户个人的"主观认知空间"。两个月后, 你的系统对你的映射,和张三对他的系统的映射,是不同的——因为它们各自学习了你/张三的个人偏置。

---

## 六、论文映射 (12篇文献支撑)

| 设计维度 | 文献支撑 |
|:---|:---|
| X轴 STC + IDF修正 | 语法树复杂度【8】 + TF-IDF查询分类【15】 |
| Y轴 依存深度+并列词 | 人类阅读时间预测 + 中间结构复杂度 |
| Z轴 峭度+语气+节律 | 认知负荷语言线索【14】【16】 + LLM Router语义-复杂度鸿沟【12】 |
| 三维投影 | 贝叶斯动态网络【6】 + CatSignal Product-of-Experts【7】 |
| 后验校准 | LLMRank 特征归因【13】 + StR 级联路由【10】 |
| 路由决策 | SELECT-THEN-ROUTE 两层框架【10】 + 动态模型路由综述【19】 |

---

## 七、代码变化

```
移除:
  - PCR._TOOL_KEYWORDS, _ADVISOR_KEYWORDS, _COMPANION_KEYWORDS
  - UnifiedParser._derive_behavior_label (硬编码 if-else)
  - 所有 discrete expectation labels (TOOL/ADVISOR/COMPANION/UNKNOWN)

新增:
  - SyntacticTerrain.from_stanza() → STC 提取器
  - coordinate_projector.py → (X,Y,Z) 投影器  
  - routing_zones.py → 六区域路由决策
  - calibration_tracker.py → 用户系数追踪

保留:
  - StructuralFeatures (语法结构, 零硬编码)
  - Stanza 依存解析
  - BGE embedding (用于 SVO 语义距离)
  - Kurtosis 峭度 (用于 Z 轴)
  - CognitiveProfile (用户状态, 节律)
```

---

## 八、实施路线

| 阶段 | 内容 | 状态 |
|:---:|------|:---:|
| P0 | Staza STC 提取器 (D/C/P 三特征) | stanza 已装 ✅ |
| P0 | SVO + BGE 语义距离 (X轴) | 需装 bge-small |
| P0 | 句法语气分类器 (Z轴信号A) | 纯规则, 即写 |
| P1 | 坐标投影器 (XYZ 三维投影) | 公式就绪 |
| P1 | 路由区域决策器 | 六区域定义就绪 |
| P2 | 后验校准追踪器 | 需累���用户反馈数据 |
| P2 | 系数微调反向传播 | 需多轮交互数据 |
