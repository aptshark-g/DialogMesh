# DialogMesh BehaviorRewarder --- 工程实现文档

> **文档编号**: ENGINEERING-V3.3-REWARDER-005  
> **版本**: v1.0  
> **日期**: 2026-07-05  
> **状态**: 工程待实现  
> **对应算法文档**: DESIGN_V3_3_ALGORITHM.md S5  
> **依赖模块**: ENGINEERING_V3_3_BEHAVIOR_GRAPH.md  
> **前置算法**: v3.3 算法设计 S5 --- 奖励规则 + 时间衰减 + 噪声自适应 + ABL反思  
> **原则**: reward 不直接修改边权重, 而是通过 EMA 权重更新器间接影响。区分信号与噪声是核心。  

---

## 1. 文档目标与范围

为 BehaviorRewarder 提供完整的工程实现规范。
覆盖奖励规则表、时间衰减因子、噪声自适应策略、ABL反思向量、会话级全局衰减。

### 边界

| 边界 | 包含 | 不包含 |
|------|------|--------|
| 输入 | TrainingSignal + 用户反馈 | 用户原始输入 |
| 输出 | RewardSignal + ABLReflection | BehaviorGraph 的边权重直接修改 |
| 职责 | 计算奖励 + 生成反思 + 噪声判断 | 权重更新（由 WeightUpdater 负责） |

---

## 2. 架构总览

### 管线位置

```
TrainingFeedbackLoop -> [BehaviorRewarder] -> WeightUpdater (EMA 更新)
                              |
                              v
                        Cognitive Tree (ABL 反思写入 REFLECTION 节点)
```

### 内部架构

```
[RewardRuleTable] -- 规则匹配 -> raw_reward
   |
   v
[TimeDecay] -- 根据 delta_t 计算 decay_factor
   |
   v
[NoiseAdaptation] -- noise_level -> effective_reward = raw * (1-noise_level)
   |
   v
[ABLReflectionGenerator] -- 生成结构化反思
   |
   v
RewardSignal + ABLReflection -> WeightUpdater / CognitiveTree
```

### 文件结构

```
core/agent/v3_2/rewarder/
  __init__.py
  models.py              # RewardSignal, ABLReflection
  reward_rules.py        # RewardRuleTable
  time_decay.py          # TimeDecay
  noise_adaptation.py    # NoiseAdaptation
  abl_reflection.py      # ABLReflectionGenerator
  rewarder.py            # BehaviorRewarder 入口
```

---

## 3. 数据模型 (models.py)

```python
@dataclass
class RewardSignal:
    edge_key: str
    raw_reward: float       # [-0.20, 0.10]
    decay_factor: float     # [0, 1]
    noise_level: float      # [0, 1]
    effective_reward: float # raw * decay * (1-noise)
    timestamp: float
    session_end: bool = False
    correction_count: int = 0
    is_exploration: bool = False

    def compute_effective(self):
        if self.is_exploration:
            self.effective_reward = 0.0
            return
        self.effective_reward = self.raw_reward * self.decay_factor * (1 - self.noise_level)

@dataclass
class ABLReflection:
    edge_key: str
    error_type: str  # over_generalization | missing_step | wrong_entity | domain_mismatch
    correct_path: str
    why_wrong: str
    suggested_correction: str
    turn_count: int
    timestamp: float

    def to_dict(self) -> dict:
        return asdict(self)
```

## 4. 纠正检测器 (CorrectionDetector)

### 4.1 职责

在 BehaviorRewarder 之前检测纠正信号。Rewarder 不负责检测, 只负责收到信号后怎么处理。

### 4.2 三种纠正来源

| 来源 | 检测方式 | 示例 |
|------|---------|------|
| 显式纠正 | 文本中有明确否定词 + 替代路径 | 用户说\"不对\", \"不是这样\", \"不要 X 要 Y\" |
| 行为回退 | 用户执行 B 后立刻撤返回值/执行 C | A->B->A (回退) 或 A->B->C (跳过) |
| 连续失败 | 同一行为对连续触发 ERROR_TRIGGERED 3 次 | A->B 连续 3 次 failure, 无 success |

### 4.3 接口

```python
@dataclass
class CorrectionSignal:
    is_correction: bool
    correction_type: str  # explicit | rollback | consecutive_failure
    correct_path: str | None  # 替代路径 (如果用户指定了)
    confidence: float         # 检测置信度 [0,1]
    edge_key: str | None
    source_text: str = \"\"    # 触发源文本

class CorrectionDetector:
    def __init__(self):
        self.failure_counts: dict[str, int] = {}
        self.NEGATION_PATTERNS = [\"不对\", \"不是\", \"不要\", \"换一个\", \"错了\"]

    def detect(self, current_text: str, prev_actions: list[str],
               current_action: str, edge_history: dict) -> CorrectionSignal | None:
        # 1. 显式纠正
        for pattern in self.NEGATION_PATTERNS:
            if pattern in current_text:
                return CorrectionSignal(True, \"explicit\", None, 0.9, None, current_text)

        # 2. 行为回退
        if len(prev_actions) >= 2 and prev_actions[-1] == current_action:
            return CorrectionSignal(True, \"rollback\", None, 0.7, None, \"\")

        # 3. 连续失败
        if edge_history:
            key = f\"{prev_actions[-1] if prev_actions else \"?\"}->{current_action}\"
            if current_action.endswith(\"failure\"):
                self.failure_counts[key] = self.failure_counts.get(key, 0) + 1
                if self.failure_counts[key] >= 3:
                    return CorrectionSignal(True, \"consecutive_failure\", None, 0.6, key, \"\")
            else:
                self.failure_counts[key] = 0  # reset on success

        return None
```

### 4.4 流式预标记

文本中出现否定词时, 立即触发预标记 (不等轮次结束):
- IntentParser 在解析过程中检测到否定词 -> 写入 ParseContext.correction_hint
- BehaviorRewarder 在轮次结束时读取 CorrectionDetector 的输出, 结合预标记决定是否触发纠正处理
- 预标记不阻塞当前轮, 只存储为上下文状态供后续使用

---

---

## 4. RewardRuleTable

### 4.1 职责

根据预测结果与实际行为的匹配程度, 确定 raw_reward 值。

### 4.2 接口

```python
class RewardRuleTable:
    RULES = [
        ("top1_hit", 0.10, "精准预测"),
        ("top3_hit", 0.05, "方向对但不够精准"),
        ("partial_match", 0.03, "行为不对但实体对"),
        ("complete_miss", -0.15, "预测完全失败"),
        ("user_correction", -0.20, "用户明确纠正"),
        ("correction_with_alternative", -0.20, "纠正+指定正确行为"),
        ("no_feedback", 0.00, "不更新"),
    ]

    def evaluate(
        self, prediction, actual_action: str,
        is_correction: bool = False,
        has_alternative: bool = False
    ) -> float:
        if is_correction:
            return -0.20  # 纠正
        if not prediction or not prediction.candidates:
            return 0.0
        top3 = sorted(prediction.candidates, key=lambda c: -c.expected_value)[:3]
        top1 = top3[0].action_summary if top3 else None
        top3_actions = [c.action_summary for c in top3]

        if top1 and top1 == actual_action:
            return 0.10  # Top-1 命中
        if actual_action in top3_actions:
            return 0.05  # Top-3 命中
        return -0.15  # 完全失败

    def get_rule_description(self, reward: float) -> str:
        for _, val, desc in self.RULES:
            if abs(reward - val) < 0.001:
                return desc
        return "unknown"
```

---

## 5. TimeDecay

### 5.1 职责

根据预测与用户实际行为之间的时间差, 计算衰减因子。

### 5.2 接口

```python
class TimeDecay:
    NO_DECAY_THRESHOLD = 30      # 30s 内无衰减
    MODERATE_DECAY_TAU = 300     # 30s-5min: tau=300s
    STRONG_DECAY_TAU = 3600      # >60min: tau=3600s
    MODERATE_MAX = 300           # 5min
    STRONG_MIN = 3600            # 60min

    def compute_decay(self, delta_t: float) -> float:
        if delta_t <= self.NO_DECAY_THRESHOLD:
            return 1.0
        if delta_t <= self.MODERATE_MAX:
            return math.exp(-delta_t / self.MODERATE_DECAY_TAU)
        if delta_t >= self.STRONG_MIN:
            return math.exp(-delta_t / self.STRONG_DECAY_TAU)
        return math.exp(-delta_t / self.STRONG_DECAY_TAU)

    def explain(self, delta_t: float) -> str:
        if delta_t <= 30: return "no_decay"
        if delta_t <= 300: return "moderate_decay"
        return "strong_decay"
```

### 5.3 衰减曲线示例

| delta_t | decay_factor | 说明 |
|---------|-------------|------|
| 10s | 1.000 | 无衰减 |
| 60s | 0.819 | 温和衰减 |
| 300s | 0.368 | 5min 后显著衰减 |
| 3600s | 0.368 | 1h 后较强衰减 |
| 7200s | 0.135 | 2h 后大幅衰减 |

---

## 6. NoiseAdaptation

### 6.1 职责

区分信号与噪声。上线初期统一 noise_level=0.5, 攒 2-4 周数据后启用自适应。

### 6.2 接口

```python
class NoiseAdaptation:
    INITIAL_NOISE = 0.5
    ADAPTATION_MIN_SAMPLES = 500  # 最少样本数才启用自适应

    def __init__(self):
        self.noise_level = self.INITIAL_NOISE
        self.correction_history: dict[str, list[dict]] = {}  # edge_key -> events
        self.total_corrections = 0
        self.observation_window = 3  # 默认 3 轮

    def get_effective_reward(self, signal: RewardSignal) -> float:
        signal.noise_level = self.noise_level
        signal.compute_effective()
        return signal.effective_reward

    def record_correction(
        self, edge_key: str,
        correction_text: str = ""
    ):
        if edge_key not in self.correction_history:
            self.correction_history[edge_key] = []
        self.correction_history[edge_key].append({
            "text": correction_text,
            "timestamp": time.time()
        })
        self.total_corrections += 1

    def analyze_and_adjust(self):
        if self.total_corrections < self.ADAPTATION_MIN_SAMPLES:
            return  # 数据不足
        self._analyze_contradiction()
        self._analyze_effectiveness()
        self._analyze_signal_strength()

    def _analyze_contradiction(self):
        """检查纠正是否在 3 轮内被再次纠正 -> 自我矛盾 = 噪声"""
        contradictions = 0
        for edge_key, events in self.correction_history.items():
            for i in range(1, len(events)):
                dt = events[i]["timestamp"] - events[i-1]["timestamp"]
                if dt < 180:  # 3 分钟内
                    contradictions += 1
        ratio = contradictions / max(self.total_corrections, 1)
        if ratio > 0.3:  # 超过 30% 的自我矛盾
            self.noise_level = min(1.0, self.noise_level + 0.1)
            self.observation_window = 7

    def _analyze_effectiveness(self):
        """纠正后是否持续沿用新路径 -> 有效学习 = 信号"""
        # 由外部调用方提供 follow_through 数据
        # 此处留桩
        pass

    def _analyze_signal_strength(self):
        """纠正文本中是否有明确否定词 -> 强化信号"""
        NEGATION_KEYWORDS = ["不对", "不是", "重新", "错了", "换一个"]
        strong_signals = 0
        for events in self.correction_history.values():
            for event in events:
                text = event.get("text", "")
                if any(kw in text for kw in NEGATION_KEYWORDS):
                    strong_signals += 1
        ratio = strong_signals / max(self.total_corrections, 1)
        if ratio > 0.5:
            self.noise_level = max(0.0, self.noise_level - 0.1)  # 信号更清晰
```

---

## 7. ABLReflectionGenerator

### 7.1 职责

当用户纠正时, 生成结构化反思向量, 写入 Cognitive Tree 的 REFLECTION 节点。

### 7.2 接口

```python
class ABLReflectionGenerator:
    ERROR_TYPES = [
        "over_generalization",
        "missing_step",
        "wrong_entity",
        "domain_mismatch",
    ]

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def generate(
        self, edge_key: str, predicted_action: str,
        actual_action: str, context: str, turn_count: int
    ) -> ABLReflection | None:
        if self.llm:
            return self._llm_generate(edge_key, predicted_action, actual_action, context, turn_count)
        return self._rule_generate(edge_key, predicted_action, actual_action, turn_count)

    def _llm_generate(self, edge_key, predicted, actual, ctx, turn) -> ABLReflection:
        prompt = (
            "分析预测偏差: 预测=" + predicted + " 实际=" + actual
            + " 上下文=" + ctx
            + ' 输出JSON: {"error_type": "...", "correct_path": "...", "why_wrong": "...", "suggested_correction": "..."}'
        )
        raw = await self.llm.generate(prompt, max_tokens=150)
        # 解析 LLM 输出...
        return self._parse_llm_output(raw, edge_key, turn)

    def _rule_generate(self, edge_key, predicted, actual, turn) -> ABLReflection:
        """基于规则的反思生成（LLM 不可用时）"""
        error_type = "wrong_entity"  # 默认
        if predicted and actual and predicted[:2] == actual[:2]:
            error_type = "missing_step"
        return ABLReflection(
            edge_key=edge_key, error_type=error_type,
            correct_path=actual, why_wrong="", suggested_correction="",
            turn_count=turn, timestamp=time.time()
        )

    def _parse_llm_output(self, raw, edge_key, turn):
        import json
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return self._rule_generate(edge_key, "", "", turn)
        try:
            d = json.loads(raw[start:end+1])
            return ABLReflection(
                edge_key=edge_key,
                error_type=d.get("error_type", "wrong_entity"),
                correct_path=d.get("correct_path", ""),
                why_wrong=d.get("why_wrong", ""),
                suggested_correction=d.get("suggested_correction", ""),
                turn_count=turn, timestamp=time.time()
            )
        except:
            return self._rule_generate(edge_key, "", "", turn)
```

---

## 8. BehaviorRewarder (入口)

### 8.1 职责

编排奖励计算流程: 规则匹配 -> 时间衰减 -> 噪声自适应 -> ABL反思。

### 8.2 接口

```python
class BehaviorRewarder:
    """奖励器入口"""

    def __init__(
        self, graph: BehaviorGraph,
        rules: RewardRuleTable = None,
        decay: TimeDecay = None,
        noise: NoiseAdaptation = None,
        abl: ABLReflectionGenerator = None
    ):
        self.graph = graph
        self.rules = rules or RewardRuleTable()
        self.decay = decay or TimeDecay()
        self.noise = noise or NoiseAdaptation()
        self.abl = abl or ABLReflectionGenerator()
        self.correction_counts: dict[str, int] = {}

    def on_prediction_result(
        self, prediction, actual_action: str,
        is_correction: bool = False,
        has_alternative: bool = False,
        delta_t: float = 0.0,
        context: str = "",
        turn_count: int = 0
    ) -> tuple[RewardSignal, ABLReflection | None]:
        edge_key = self._find_edge_key(actual_action)
        if not edge_key:
            return (RewardSignal("", 0, 1, 0, 0, 0), None)

        # 检查 EXPLORATION
        edge = self.graph.edges.get(edge_key)
        from_step = self.graph.nodes.get(edge.from_step_id) if edge else None
        is_exploration = from_step and from_step.action_type == "EXPLORATION"

        # 累计纠正次数
        if is_correction:
            self.correction_counts[edge_key] = self.correction_counts.get(edge_key, 0) + 1

        raw = self.rules.evaluate(prediction, actual_action, is_correction, has_alternative)
        decay = self.decay.compute_decay(delta_t)
        signal = RewardSignal(
            edge_key=edge_key, raw_reward=raw, decay_factor=decay,
            noise_level=self.noise.noise_level, effective_reward=0,
            timestamp=time.time(), is_exploration=is_exploration,
            correction_count=self.correction_counts.get(edge_key, 0)
        )
        effective = self.noise.get_effective_reward(signal)

        # 连续 3 次相同路径纠正 -> 标记持久错误
        if self.correction_counts.get(edge_key, 0) >= 3:
            self._mark_persistent_error(edge_key)

        # ABL 反思
        reflection = None
        if is_correction or raw < 0:
            top1 = prediction.top3[0].action_summary if prediction and prediction.top3 else ""
            reflection = self.abl.generate(
                edge_key, top1, actual_action, context, turn_count
            )

        # 更新 WeightUpdater
        self._apply_to_graph(edge_key, effective)

        return (signal, reflection)

    def on_session_end(self):
        """会话结束: 全局权重衰减 ×0.95"""
        for edge in self.graph.edges.values():
            edge.weight *= 0.95
        self.correction_counts.clear()

    def _find_edge_key(self, action_summary: str) -> str | None:
        for key, edge in self.graph.edges.items():
            to_step = self.graph.nodes.get(edge.to_step_id)
            if to_step and to_step.action_summary == action_summary:
                return key
        return None

    def _mark_persistent_error(self, edge_key: str):
        edge = self.graph.edges.get(edge_key)
        if edge:
            edge.correction_mode = True  # 快速纠正模式
            edge.weight = 0.3 * edge.weight  # 硬覆盖

    def _apply_to_graph(self, edge_key: str, effective_reward: float):
        edge = self.graph.edges.get(edge_key)
        if edge:
            edge.weight = max(0.0, min(1.0, edge.weight + effective_reward))
```

---

## 9. 会话级全局衰减

### 9.1 触发时机

session 结束时调用 on_session_end()。所有边权重 ×0.95, 模拟长期记忆衰减。

### 9.2 原因

行为因果关联随 session 间隙自然弱化。无此衰减时, 旧 session 的高频行为会持续主导预测, 导致对新 session 的行为模式敏感度降低。

---

## 10. 测试策略

### 单元测试

| 测试 | 内容 | 优先级 |
|------|------|--------|
| test_reward_rules | 7 种场景的奖励值, EXPLORATION 特殊处理 | P0 |
| test_time_decay | 30s 内无衰减, 5min~0.368, 1h+ 强衰减 | P0 |
| test_noise_adaptation | 初始 0.5, 自我矛盾检测, 否定词检测 | P0 |
| test_abl_reflection | LLM/规则两种模式, JSON 解析, 非法输入 | P0 |
| test_rewarder | 完整流程: 规则->衰减->噪声->ABL, 全局衰减 | P0 |

### 集成测试

| 场景 | 预期 |
|------|------|
| Top-1 命中 | reward=+0.10, decay=1.0, effective=+0.05 |
| 用户纠正 | reward=-0.20, 生成 ABLReflection |
| EXPLORATION | effective_reward=0.0 |
| 同路径纠正 3 次 | correction_mode=True, weight=0.3*old |
| session 结束 | 所有权重 ×0.95 |
| 连续 3 轮自我矛盾 | noise_level 上调, 窗口拉长到 7 轮 |
| 明确否定词 > 50% | noise_level 下调 |

---

## 11. 附录

### A. 对照

| 算法 S5 | 实现 | 状态 |
|---------|------|------|
| 奖励规则表 | RewardRuleTable | 待实现 |
| 时间衰减 exp(-dt/tau) | TimeDecay | 待实现 |
| 噪声自适应 | NoiseAdaptation | 待实现 |
| ABL 反思向量 | ABLReflectionGenerator | 待实现 |
| 入口 | BehaviorRewarder | 待实现 |

### B. 优先级

P0: models -> RewardRuleTable -> TimeDecay -> BehaviorRewarder
P1: NoiseAdaptation (初始固定 0.5, 自适应等数据)
P2: ABLReflectionGenerator (首期用规则, LLM 模式延后)

### C. 依赖

```
RewardRuleTable -> TrainingSignal (来自 Predictor)
TimeDecay -> 无
NoiseAdaptation -> 无 (自主分析)
ABLReflectionGenerator -> LLM provider (可选)
BehaviorRewarder -> RewardRuleTable + TimeDecay + NoiseAdaptation + ABLReflectionGenerator
```

### D. 待讨论

1. effective_reward = raw * decay * (1-noise), 这个公式是否合理? 噪声高时完全压制 reward?
2. 全局衰减 0.95/session 是否太快? 活跃用户一天多个 session 权重会快速趋近 0。
3. ABL 反思的 4 种 error_type 是否覆盖了所有常见偏差模式?
4. NoiseAdaptation 的 500 样本下限是否合理?

--- END OF DOCUMENT ---