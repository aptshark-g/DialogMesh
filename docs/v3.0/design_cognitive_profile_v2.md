# DialogMesh 2.0 认知-画像架构升级设计

**版本**: v2.0  
**日期**: 2026-07-01  
**作者**: DialogMesh Contributors  
**状态**: 设计阶段  

---

## 1. 问题陈述

### 1.1 当前痛点

DialogMesh 1.x 的认知画像（`CognitiveProfile`）仅有 5 个维度：

```python
class CognitiveProfile:
    metacognition: float      # 元认知
    divergence: float         # 发散性
    tracking_depth: float     # 追踪深度
    stability: float          # 稳定性
    confidence: float           # 置信度
```

**问题**:

1. **画像太浅**：5 个纯数值维度无法支撑 LLM 的上下文推断。LLM 只能得到 `metacognition=0.7`，却不知道用户是程序员还是医生，不知道用户在加班还是休息。
2. **推断成本高**：每次对话 LLM 都需要从零推断用户背景、情绪状态、时间上下文，导致 prompt 膨胀、token 浪费、响应延迟。
3. **标签化信息缺失**：时间、天气、职业、领域等标签化信息是**强稳定信号**，可以大幅减少 LLM 的推断与困惑度。
4. **时间维度缺失**：没有处理对话间隔的时间衰减机制。用户 3 天后再来对话，系统无法判断记忆组块是否应被清理或降级。
5. **认知能力评估缺失**：没有 g 因子（一般认知能力）评估，导致系统无法判断用户能理解多复杂的回答。
6. **获取策略粗糙**：标签获取要么靠用户主动填写（体验差），要么靠 LLM 硬猜（准确率低），没有渐进式、非侵入式获取机制。

### 1.2 设计目标

构建**双轨用户画像架构**（Dual-Track User Profile Architecture）：

- **轨道 A — 底层认知动力学**：基于 rz.txt 框架直觉的抽象化（惯性、预期偏差、信任度、情绪单调度），动态演化，不可直接观测。
- **轨道 B — 标签化信息层**：时间、天气、职业、领域、g 因子等**强稳定信号**，静态或慢变，可直接观测或推断。

两条轨道**协同工作**：轨道 B 提供先验，降低轨道 A 的推断成本；轨道 A 提供动态修正，避免轨道 B 的标签僵化。

---

## 2. 双轨用户画像架构

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    Dual-Track User Profile                       │
├─────────────────────────────┬─────────────────────────────────────┤
│  轨道 A: 认知动力学层       │  轨道 B: 标签化信息层               │
│  (动态, 不可直接观测)       │  (静态/慢变, 可观测/推断)           │
├─────────────────────────────┼─────────────────────────────────────┤
│  • 认知惯性 (风格偏好)       │  • 基础标签: 时间、天气、职业、领域   │
│  • 信任度 T(S,O)            │  • 认知能力: g 因子、教育背景        │
│  • 情绪单调度 M_Em          │  • 交互偏好: 沟通风格、详细程度       │
│  • 注意力锚点 P             │  • 环境上下文: 设备、位置、日程       │
│  • 预期偏差 ΔE              │  • 社交图谱: 关系亲疏、角色定位       │
│  • 记忆点集 M               │  • 兴趣图谱: 话题权重、关注领域        │
│  • 自我价值感 V(S)          │  • 时间状态: 对话间隔、活跃时段        │
└─────────────────────────────┴─────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  融合层 (Fusion Layer)                                           │
│  轨道 A 提供动态权重 → 轨道 B 提供先验锚定 → 联合输入 LLM        │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 轨道 A: 认知动力学层（抽象自 rz.txt）

从 rz.txt 的公理化体系中提取**可工程化的行为特征**，扔掉所有 fMRI/神经科学/混沌理论。

| 概念 | 工程化抽象 | 计算方式 | 稳定性 |
|------|-----------|---------|--------|
| **认知惯性** | 对话风格惯性 | 用户偏好的详细/简洁、直接/委婉、结构化/自由，基于历史对话的皮尔逊自相关系数 | 中（慢变） |
| **身体惯性** | 反馈行为惯性 | 用户对系统建议的接受率、质疑率、澄清率，基于历史反馈序列 | 中（慢变） |
| **信任度 T(S,O)** | 系统信任度 | 预期兑现率 = 系统承诺执行且成功的次数 / 总承诺次数 | 高（慢变） |
| **情绪单调度 M_Em** | 情绪多样性 | 近期对话情绪极性的信息熵标准化值 | 低（快变） |
| **注意力锚点 P** | 核心话题维度 | 对话树中高频主题的权重分布 | 中（话题切换时变） |
| **预期偏差 ΔE** | 满意度偏差 | 系统输出 vs 用户预期反馈的历史偏差 | 低（每轮更新） |
| **记忆点集 M** | 高影响事件 | 强情绪/高满意度/高不满的对话事件，按时间衰减加权 | 中（幂律衰减） |
| **自我价值感 V(S)** | 自我肯定程度 | 对话中的自我肯定语言频率与强度 | 中（慢变） |
| **认知资源 C_max** | 用户当前耐心 | 从对话长度、回复速度、问题复杂度推断 | 低（快变） |

**关键原则**：所有概念都是**可计算的行为特征**，不依赖任何神经科学测量。

### 2.3 轨道 B: 标签化信息层

标签化信息分为**基础标签**、**认知能力**、**交互偏好**、**环境上下文**、**社交图谱**、**兴趣图谱**、**时间状态**七类。

#### 2.3.1 基础标签（Basic Tags）

| 标签 | 类型 | 来源 | 用途 | 稳定性 |
|------|------|------|------|--------|
| `occupation` | 职业 | 推断 / 暗示 / 询问 | 领域知识对齐、术语适配 | 高 |
| `domain` | 专业领域 | 推断 / 暗示 / 询问 | 技术深度调整、上下文推断 | 高 |
| `education_level` | 教育水平 | 推断 / 暗示 / 询问 | 认知复杂度适配 | 高 |
| `language_preference` | 语言偏好 | 观测（用户输入语言） | 回复语言选择 | 高 |
| `timezone` | 时区 | 系统获取（浏览器/系统 API） | 时间相关推断 | 高 |
| `location` | 地理位置 | 系统获取（IP / 用户授权） | 天气、本地事件、文化适配 | 高 |

#### 2.3.2 认知能力（Cognitive Capacity）

| 标签 | 类型 | 来源 | 用途 | 稳定性 |
|------|------|------|------|--------|
| `g_factor` | 一般认知能力（g 因子） | 推断 / 任务测试 | 回答复杂度、解释深度、隐喻使用 | 高 |
| `technical_depth` | 技术深度 | 推断（对话历史） | 技术术语密度、概念粒度 | 中 |
| `learning_speed` | 学习速度 | 推断（错误修正率） | 解释节奏、重复频率 | 中 |
| `abstraction_level` | 抽象偏好 | 推断（对话历史） | 具体例子 vs 抽象原理 | 中 |

**g 因子推断方式**：
- **间接推断**：用户理解复杂概念的速度、追问的深度、跨领域迁移能力
- **任务测试**：在对话中嵌入微型认知任务（如逻辑推理、模式识别），观察完成质量
- **LLM 评估**：让 LLM 基于对话历史评估用户的认知能力等级（低/中/高/专家）

**关键原则**：g 因子不用于**歧视或标签固化**，仅用于**动态调整回复复杂度**。用户认知能力可能在不同领域差异巨大（如程序员擅长技术但不懂金融），g 因子是**领域相对**的。

#### 2.3.3 交互偏好（Interaction Preferences）

| 标签 | 类型 | 来源 | 用途 | 稳定性 |
|------|------|------|------|--------|
| `communication_style` | 沟通风格 | 推断（对话历史） | 正式/ casual、直接/委婉 | 中 |
| `detail_level` | 详细程度偏好 | 推断（用户反馈） | 摘要 vs 详细、步骤粒度 | 中 |
| `clarity_tolerance` | 对模糊性的容忍度 | 推断（澄清频率） | 是否需要高度精确表达 | 中 |
| `humor_preference` | 幽默偏好 | 推断（用户反应） | 是否适合幽默回复 | 中 |
| `emoji_usage` | 表情符号使用 | 观测（用户输入） | 回复是否使用 emoji | 高 |

#### 2.3.4 环境上下文（Environmental Context）

| 标签 | 类型 | 来源 | 用途 | 稳定性 |
|------|------|------|------|--------|
| `time_of_day` | 当前时段 | 系统获取 | 推断用户状态（早晨/深夜） | 低（实时） |
| `day_of_week` | 星期 | 系统获取 | 工作日 vs 周末推断 | 低（实时） |
| `weather` | 天气 | API 获取（基于位置） | 情绪推断、活动建议 | 低（实时） |
| `device_type` | 设备类型 | 系统获取（User-Agent） | 移动端精简回复 vs 桌面端详细 | 高 |
| `session_context` | 会话上下文 | 系统获取 | 是快速查询还是深度对话 | 低（实时） |

#### 2.3.5 社交图谱（Social Graph）

| 标签 | 类型 | 来源 | 用途 | 稳定性 |
|------|------|------|------|--------|
| `relationship_depth` | 关系深度 | 推断（对话历史） | 新用户/老用户/核心用户 | 中 |
| `role_perception` | 角色感知 | 推断（用户语言） | 用户视系统为工具/顾问/伙伴 | 中 |
| `trust_level` | 信任等级 | 轨道 A 计算 | 是否可以直接给建议还是需要论证 | 中 |

#### 2.3.6 兴趣图谱（Interest Graph）

| 标签 | 类型 | 来源 | 用途 | 稳定性 |
|------|------|------|------|--------|
| `topic_weights` | 话题权重 | 推断（对话历史） | 对话树分支权重、推荐优先级 | 中 |
| `skill_areas` | 技能领域 | 推断 / 暗示 / 询问 | 技术栈、专业领域 | 中 |
| `pain_points` | 痛点 | 推断（高频问题/抱怨） | 主动服务、预测性建议 | 中 |
| `goals` | 目标 | 推断 / 暗示 / 询问 | 长期对话方向对齐 | 高 |

#### 2.3.7 时间状态（Temporal State）

| 标签 | 类型 | 来源 | 用途 | 稳定性 |
|------|------|------|------|--------|
| `last_interaction` | 上次交互时间 | 系统记录 | 记忆衰减计算 | 低（实时） |
| `session_interval` | 会话间隔 | 系统计算 | 记忆组块清理判断 | 低（实时） |
| `active_hours` | 活跃时段 | 推断（历史时间戳） | 最佳回复时间、异步通知 | 中 |
| `conversation_frequency` | 对话频率 | 推断（历史统计） | 用户粘性、流失预警 | 中 |
| `memory_decay_factor` | 记忆衰减因子 | 系统计算 | 旧记忆的权重调整 | 低（实时） |

---

## 3. 时间衰减机制（Memory Decay）

### 3.1 核心问题

用户与系统的对话不是连续流，而是**离散事件**。两次对话之间的间隔从几秒到几个月不等。时间间隔越久，旧记忆的**可用性**越低。

当前系统没有处理这个问题。用户 3 天后再来对话，系统仍然把 3 天前的上下文当作"热记忆"处理，导致：
- 过时信息干扰当前对话
- 用户需要反复重新解释背景
- 系统无法判断用户是否"忘记"了之前的对话

### 3.2 记忆衰减模型

采用**双指数衰减 + 阶梯跃迁**模型：

```
记忆权重 W(t) = W_0 * [α * exp(-t/τ_1) + (1-α) * exp(-t/τ_2)]

其中:
  W_0 = 初始权重（由事件重要性决定）
  t = 距上次交互的时间（小时）
  τ_1 = 短时衰减常数（24小时，日常对话衰减）
  τ_2 = 长时衰减常数（720小时，30天，长期记忆衰减）
  α = 短时权重比例（0.7，大部分记忆在日常尺度衰减）
```

**阶梯跃迁（Step Transition）**：

| 时间间隔 | 状态 | 记忆处理策略 |
|---------|------|------------|
| < 1小时 | 连续会话 | 完整记忆，无衰减 |
| 1-24小时 | 同日延续 | 轻衰减（α=0.9），保留上下文 |
| 1-7天 | 短期间隔 | 标准衰减，摘要树压缩，丢弃细节 |
| 7-30天 | 中期间隔 | 强衰减，仅保留一级摘要 + 关键实体 |
| > 30天 | 长期间隔 | 阶梯跃迁，记忆组块标记为"冷记忆"，LLM 需主动确认 |

### 3.3 记忆组块清理策略

```python
class MemoryChunk:
    """对话记忆组块。"""
    chunk_id: str
    created_at: float           # 创建时间
    last_accessed: float        # 上次访问时间
    importance: float           # 重要性（0-1，由情绪强度 + 任务完成度决定）
    summary_level: int          # 摘要级别：0=原始, 1=一级摘要, 2=二级摘要
    
    def get_effective_weight(self, current_time: float) -> float:
        t = (current_time - self.last_accessed) / 3600  # 小时
        if t < 1:
            return self.importance
        
        # 双指数衰减
        W = self.importance * (0.7 * exp(-t/24) + 0.3 * exp(-t/720))
        
        # 重要性保护：高重要性记忆的衰减更慢
        if self.importance > 0.8:
            W *= 1.5
        
        return min(W, 1.0)
    
    def should_cleanup(self, current_time: float) -> bool:
        """是否应被清理或降级。"""
        t_days = (current_time - self.last_accessed) / 86400
        
        if t_days > 30 and self.importance < 0.3:
            return True  # 30天以上的低重要性记忆，清理
        if t_days > 7 and self.summary_level == 0 and self.importance < 0.5:
            return True  # 7天以上的中等重要性原始记忆，压缩为摘要
        
        return False
```

### 3.4 对话恢复时的上下文重建

当用户间隔较久再次对话时，系统需要**主动恢复上下文**而非被动加载：

```
用户输入: "继续之前的工作"

系统处理:
  1. 识别 "继续" → 时间锚定请求
  2. 查询冷记忆组块（>30天），按重要性排序
  3. LLM 生成上下文恢复摘要（不是原始对话，而是"上次我们在做 X，到 Y 阶段"）
  4. 向用户确认："您是指上周讨论的 [主题] 吗？我们当时完成了 [阶段]。"
  5. 用户确认后，标记该组块为 "热记忆"，重置衰减时钟
```

---

## 4. 标签获取策略（Tag Acquisition Strategy）

### 4.1 核心矛盾

- **标签越多 → LLM 推断成本越低**（先验充足）
- **标签获取 → 用户侵入感越强**（体验差）
- **标签错误 → 误导 LLM**（质量风险）

### 4.2 三级获取策略

```
┌─────────────────────────────────────────────────────────────┐
│  标签获取策略（三级渐进式）                                    │
├─────────────────────────────────────────────────────────────┤
│  L1: 被动观测（Passive Observation）                         │
│      ├── 系统 API 获取: 时间、天气、位置、设备                  │
│      ├── 用户输入分析: 语言、emoji、技术术语、领域关键词         │
│      └── 零侵入，用户无感知                                   │
├─────────────────────────────────────────────────────────────┤
│  L2: 间接推断（Indirect Inference）                          │
│      ├── LLM 基于对话历史推断职业、领域、技术深度               │
│      ├── 对话模式分析推断沟通风格、详细程度偏好                 │
│      └── 低侵入，用户无直接感知                                 │
├─────────────────────────────────────────────────────────────┤
│  L3: 暗示与试探（Tactical Elicitation）                       │
│      ├── 自然对话中嵌入暗示性问题（"您平时用什么语言？"）       │
│      ├── 微型任务测试（嵌入式认知任务）                         │
│      └── 低侵入，但用户可能感知到 "被了解"                     │
├─────────────────────────────────────────────────────────────┤
│  L4: 主动询问（Active Inquiry）                                │
│      ├── 直接询问（"您的工作是什么？"）— 仅当高价值且低获取率  │
│      ├── 澄清引导（"您提到的 X 是指 A 还是 B？"）               │
│      └── 中侵入，仅在必要时使用                                 │
└─────────────────────────────────────────────────────────────┘
```

**策略原则**：
- 优先 L1 和 L2，L3 谨慎使用，L4 仅在标签价值高且无法通过其他方式获取时使用
- L3 和 L4 的触发必须满足**侵入-收益比**约束：`标签价值 / 用户侵入感 > 阈值`
- 用户反感检测：如果用户对暗示/询问表现出回避（转移话题、简短回复），停止获取并标记该标签为"敏感"

### 4.3 标签获取的具体实现

#### 4.3.1 职业获取（示例）

**L2 推断**：
```
用户输入: "我在做 CNN-LSTM 的时序预测，但是 loss 不收敛"
LLM 推断: 技术深度=高, 领域=深度学习/时序分析, 职业=AI研究员/工程师
```

**L3 暗示**：
```
系统回复: "CNN-LSTM 的时序预测确实 tricky。您是在研究场景用还是工程落地？"
（暗示获取：研究 vs 工程，进一步推断职业类型）
```

**L4 主动询问**（仅当 L2/L3 失败且职业标签对当前对话高价值）：
```
系统回复: "为了更好地帮您调整模型，能否告诉我您的使用场景？是学术研究、工业落地，还是个人项目？"
```

#### 4.3.2 g 因子获取（示例）

**L2 推断**：
```
观察指标:
  - 用户理解复杂概念的速度（从初次接触到正确使用的轮次）
  - 追问的深度（是表面问题还是触及底层机制）
  - 跨领域迁移能力（能否将一个领域的概念应用到另一个领域）
  - 错误修正率（犯错后能否快速理解并纠正）
  
LLM 评估（基于最近 10 轮对话）:
  "用户展现出的认知特征：快速理解抽象概念，能提出深层追问，
   跨领域迁移能力强，错误修正快。g 因子评估：高。"
```

**L3 微型任务测试**（嵌入式）：
```
系统回复: "在调整学习率之前，先确认一下：如果学习率太高，
  优化器会在损失曲面上'跳过'最小值；太低则会'爬得太慢'。
  您现在的情况是哪种？"
  
（这不是直接测试，而是观察用户是否理解"损失曲面"这一抽象概念，
  从而推断其抽象推理能力）
```

### 4.4 标签置信度与更新机制

每个标签都有**置信度**和**更新策略**：

```python
class UserTag:
    name: str
    value: Any
    confidence: float           # 置信度（0-1）
    source: str                 # 来源：L1/L2/L3/L4
    last_updated: float         # 上次更新时间
    verification_count: int     # 验证次数（被其他证据确认的次数）
    
    def update(self, new_value: Any, new_confidence: float, new_source: str):
        """贝叶斯更新：新证据与旧证据融合。"""
        if new_source in ["L1", "L4"]:  # 直接观测或用户明确回答，置信度高
            self.confidence = 0.8 + 0.2 * new_confidence
            self.value = new_value
        elif new_source == "L2":  # 推断，需要多次验证
            self.verification_count += 1
            if self.verification_count >= 3:
                self.confidence = min(0.9, self.confidence + 0.15)
        elif new_source == "L3":  # 暗示获取，需要确认
            self.confidence = min(0.7, self.confidence + 0.1)
        
        self.last_updated = time.time()
```

---

## 5. 与双轨认知架构的融合

### 5.1 融合层（Fusion Layer）

```python
class FusionContext:
    """融合轨道 A 和轨道 B，生成 LLM 可用的上下文。"""
    
    def __init__(self, track_a: CognitiveDynamics, track_b: TagLayer):
        self.track_a = track_a
        self.track_b = track_b
    
    def build_prompt_context(self) -> str:
        """构建 LLM 提示词上下文。"""
        parts = []
        
        # 轨道 B 先验（稳定信息，减少推断成本）
        if self.track_b.basic_tags.occupation:
            parts.append(f"用户职业: {self.track_b.basic_tags.occupation}")
        if self.track_b.basic_tags.domain:
            parts.append(f"用户领域: {self.track_b.basic_tags.domain}")
        if self.track_b.cognitive_capacity.g_factor:
            parts.append(f"用户认知能力: {self.track_b.cognitive_capacity.g_factor} "
                        f"(回复复杂度应相应调整)")
        if self.track_b.environmental_context.time_of_day:
            parts.append(f"当前时段: {self.track_b.environmental_context.time_of_day}")
        
        # 轨道 A 动态（实时状态，影响当前回复策略）
        parts.append(f"用户信任度: {self.track_a.trust_level:.2f}")
        parts.append(f"用户情绪单调度: {self.track_a.emotion_monotony:.2f} "
                    f"({'情绪单调，需补充' if self.track_a.emotion_monotony > 0.6 else '情绪丰富'})")
        parts.append(f"用户认知资源: {self.track_a.cognitive_resource:.2f} "
                    f"({'耐心充足' if self.track_a.cognitive_resource > 0.7 else '可能疲劳'})")
        
        # 时间衰减状态
        if self.track_b.temporal_state.session_interval > 7 * 86400:
            parts.append(f"注意：用户已 {self.track_b.temporal_state.session_interval/86400:.1f} 天未对话，"
                        f"可能需要上下文恢复。")
        
        return "\n".join(parts)
```

### 5.2 双轨道协同规则

| 场景 | 轨道 A 作用 | 轨道 B 作用 | 协同效果 |
|------|-----------|-----------|---------|
| 新用户首次对话 | 冷启动，仅基础推断 | 提供职业/领域先验（如果通过 L1/L2 获取） | 快速进入有效对话 |
| 老用户常规对话 | 动态调整回复策略（信任度、情绪） | 提供稳定上下文（职业、领域不变） | 个性化 + 稳定性 |
| 用户长期未对话 | 记忆衰减，旧上下文降级 | 时间状态触发 "上下文恢复" 流程 | 避免过时信息干扰 |
| 用户情绪异常 | 情绪单调度检测，触发情绪补足 | 环境上下文（天气、时段）辅助推断 | 多维情绪感知 |
| 用户质疑系统 | 信任度下降，预期偏差增大 | 职业/领域标签帮助定位问题根源 | 精准修复信任 |
| 复杂技术问题 | 认知资源评估（是否疲劳） | g 因子评估（技术深度） | 自适应复杂度调整 |

### 5.3 认知画像 v2.0 数据结构

```python
@dataclass
class CognitiveProfileV2:
    """DialogMesh 2.0 双轨认知画像。"""
    
    # ── 轨道 A: 认知动力学（动态演化）──────────────────────────
    track_a: CognitiveDynamics = field(default_factory=CognitiveDynamics)
    
    # ── 轨道 B: 标签化信息（静态/慢变）────────────────────────
    track_b: TagLayer = field(default_factory=TagLayer)
    
    # ── 时间状态（实时计算）──────────────────────────────────
    temporal_state: TemporalState = field(default_factory=TemporalState)
    
    # ── 融合状态（派生）─────────────────────────────────────
    fusion_state: FusionState = field(default_factory=FusionState)
    
    # 版本控制（乐观锁）
    version: int = 1
    updated_at: float = field(default_factory=time.time)


@dataclass
class CognitiveDynamics:
    """轨道 A: 认知动力学（基于 rz.txt 抽象化）。"""
    
    # 双惯性
    cognitive_inertia: float = 0.5       # 认知惯性（风格偏好稳定性）
    behavioral_inertia: float = 0.5      # 行为惯性（反馈模式稳定性）
    
    # 信任与预期
    trust_level: float = 0.5           # 信任度 T(S,O)
    expectation_bias: float = 0.0      # 预期偏差 ΔE
    
    # 情绪与认知资源
    emotion_monotony: float = 0.5      # 情绪单调度 M_Em
    cognitive_resource: float = 1.0    # 认知资源 C_max
    
    # 注意力与价值
    attention_anchor: str = ""         # 注意力锚点 P（当前核心话题）
    self_worth: float = 0.5            # 自我价值感 V(S)
    
    # 记忆点集（高影响事件）
    memory_points: List[MemoryPoint] = field(default_factory=list)
    
    # 历史版本（用于回溯）
    history: List[Dict] = field(default_factory=list)


@dataclass
class TagLayer:
    """轨道 B: 标签化信息层。"""
    
    # 基础标签
    basic_tags: BasicTags = field(default_factory=BasicTags)
    
    # 认知能力
    cognitive_capacity: CognitiveCapacity = field(default_factory=CognitiveCapacity)
    
    # 交互偏好
    interaction_prefs: InteractionPreferences = field(default_factory=InteractionPreferences)
    
    # 环境上下文
    environmental_context: EnvironmentalContext = field(default_factory=EnvironmentalContext)
    
    # 社交图谱
    social_graph: SocialGraph = field(default_factory=SocialGraph)
    
    # 兴趣图谱
    interest_graph: InterestGraph = field(default_factory=InterestGraph)


@dataclass
class BasicTags:
    occupation: Optional[UserTag] = None      # 职业
    domain: Optional[UserTag] = None            # 领域
    education_level: Optional[UserTag] = None # 教育水平
    language_preference: Optional[UserTag] = None
    timezone: Optional[UserTag] = None
    location: Optional[UserTag] = None


@dataclass
class CognitiveCapacity:
    g_factor: Optional[UserTag] = None          # 一般认知能力
    technical_depth: Optional[UserTag] = None  # 技术深度
    learning_speed: Optional[UserTag] = None # 学习速度
    abstraction_level: Optional[UserTag] = None # 抽象偏好


@dataclass
class TemporalState:
    """时间状态（实时计算，不持久化）。"""
    last_interaction: float = 0.0
    session_interval: float = 0.0
    memory_decay_factor: float = 1.0
    context_recovery_needed: bool = False
```

---

## 6. 实现路线图

### 阶段 1: 标签化信息层（基础）

- [ ] 实现 `TagLayer` 数据结构
- [ ] 实现 L1 被动观测（时间、天气、设备 API）
- [ ] 实现 L2 间接推断（LLM-based 职业/领域推断）
- [ ] 实现标签置信度与贝叶斯更新
- [ ] 集成到 `CognitiveProfileV2`

### 阶段 2: 时间衰减机制

- [ ] 实现双指数记忆衰减模型
- [ ] 实现阶梯跃迁（连续/短期/中期/长期）
- [ ] 实现记忆组块清理策略
- [ ] 实现上下文恢复流程（冷记忆 → 热记忆）
- [ ] 集成到 `AsyncSessionManager` 的 eviction 逻辑

### 阶段 3: 认知动力学层（轨道 A）

- [ ] 基于对话历史计算认知惯性（风格偏好）
- [ ] 实现信任度 T(S,O) 的跟踪
- [ ] 实现情绪单调度 M_Em（信息熵）
- [ ] 实现记忆点集 M（高影响事件检测）
- [ ] 实现认知资源 C_max 推断

### 阶段 4: g 因子与认知能力

- [ ] 实现 g 因子推断（基于对话质量指标）
- [ ] 实现嵌入式微型认知任务
- [ ] 实现 LLM-based 认知能力评估
- [ ] 实现回复复杂度自适应（基于 g_factor）

### 阶段 5: 标签获取策略（L3/L4）

- [ ] 实现暗示生成器（自然对话中嵌入暗示性问题）
- [ ] 实现用户反感检测（回避模式识别）
- [ ] 实现侵入-收益比决策
- [ ] 实现标签获取策略的 A/B 测试框架

### 阶段 6: 融合层与集成

- [ ] 实现 `FusionContext.build_prompt_context()`
- [ ] 将融合上下文注入 LLM 提示词
- [ ] 实现双轨道协同规则（6 大场景）
- [ ] 端到端集成测试
- [ ] 性能基准测试（标签获取对 token 消耗的影响）

---

## 7. 关键设计决策

### 决策 1: 轨道 B 不替代轨道 A

轨道 B（标签化信息）是**先验**，不是**替代**。标签不能描述动态状态（如用户当前情绪），也不能处理个性化细节（如用户今天的耐心度）。两条轨道必须共存。

### 决策 2: g 因子不用于歧视

g 因子仅用于**动态调整回复复杂度**，不用于：
- 拒绝服务（"您太笨了，我不回答"）
- 标签固化（"您永远是低认知能力"）
- 跨领域泛化（用户技术强但可能金融弱）

g 因子是**领域相对**的，每次评估基于特定领域的对话历史。

### 决策 3: 时间衰减是默认行为

所有对话记忆都必须经过时间衰减。没有"永久记忆"——只有"衰减极慢的高重要性记忆"。这是 rz.txt 中"惯性成本"的工程化体现：旧记忆的检索成本（惯性成本）随时间增加。

### 决策 4: 标签获取以用户体验为先

标签获取策略的侵入-收益比必须实时监控。如果用户对暗示表现出反感，立即降级到 L2（纯推断），甚至暂停标签获取。用户体验 > 标签完整度。

---

## 8. 与现有架构的兼容性

### 8.1 向后兼容

`CognitiveProfileV2` 可以序列化为旧版的 `CognitiveProfile`（仅保留 track_a 的核心维度），确保现有持久化数据不丢失。

### 8.2 升级路径

1. 先部署轨道 B（标签化信息）—— 对现有系统影响最小，纯新增功能
2. 再部署时间衰减机制 —— 修改 `AsyncSessionManager` 的 eviction 逻辑
3. 最后部署轨道 A 的完整动力学 —— 需要替换 PCR 的画像输入

---

## 9. 附录

### 9.1 rz.txt 概念映射表

| rz.txt 概念 | 工程化抽象 | 实现模块 | 伪科学成分 |
|-----------|-----------|---------|----------|
| 双网络激活比 R_D/E | 认知模式（理性/感性） | `CognitiveDynamics.cognitive_inertia` | ❌ fMRI 丢弃 |
| 情绪指数 Em | 满意度/情绪极性 | `TurnRecord.sentiment` + 信息熵 | ⚠️ 前景理论保留直觉 |
| 不确定性系数 U | 预期波动 | `ParseResult.confidence` | ✅ 变异系数可行 |
| 信任度 T(S,O) | 系统信任度 | `CognitiveDynamics.trust_level` | ✅ 兑现率可计算 |
| 惯性成本 C_inertia | 模式切换代价 | `MemoryChunk.get_effective_weight()` | ⚠️ 抽象化可计算 |
| 认知补足/情绪补足 | 双轨道处理 | `FusionContext` | ✅ 抽象为 LLM 提示词策略 |
| 记忆点集 M | 高影响事件 | `MemoryPoint` | ✅ 行为特征可计算 |
| 注意力锚点 P | 核心话题 | `TopicTree.topic_weights` | ✅ 频率统计 |
| 群体层（全部） | 不适用 | — | ❌ 当前版本不实现 |

### 9.2 术语表

| 术语 | 定义 |
|------|------|
| g 因子 | 一般认知能力（general cognitive ability），工程化定义为"用户理解复杂概念、跨领域迁移、快速学习的综合表现" |
| 记忆组块 | 一组关联的对话轮次，按主题/任务聚合，可独立进行摘要和衰减 |
| 阶梯跃迁 | 时间间隔超过阈值时，记忆状态从"热"到"温"到"冷"的离散跳跃 |
| 侵入-收益比 | 标签获取策略的决策指标：`标签信息价值 / 用户感知侵入度` |
| 上下文恢复 | 用户长期未对话后，系统主动生成摘要并请求确认的机制 |

---

**本文档是 DialogMesh 2.0 认知-画像架构的设计蓝图，涵盖双轨用户画像、时间衰减机制、标签获取策略三大核心升级。实现需按阶段推进，以用户体验为最高优先级。**
