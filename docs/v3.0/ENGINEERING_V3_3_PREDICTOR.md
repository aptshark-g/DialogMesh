# DialogMesh BehaviorPredictor --- 工程实现文档

> **文档编号**: ENGINEERING-V3.3-PREDICTOR-004  
> **版本**: v1.0  
> **日期**: 2026-07-05  
> **状态**: 工程待实现  
> **对应算法文档**: DESIGN_V3_3_ALGORITHM.md S4  
> **依赖模块**: ENGINEERING_V3_3_BEHAVIOR_GRAPH.md  
> **前置算法**: v3.3 算法设计 S4 --- LLM+四维排序  
> **原则**: LLM 负责提出可能性, 四维排序负责判断好坏  

---

## 1. 文档目标与范围

为 BehaviorPredictor 提供工程实现规范。
覆盖 LLM 候选生成、四维价值排序、训练闭环、三态回退。

### 边界

| 边界 | 包含 | 不包含 |
|------|------|--------|
| 输入 | 最近 5 步行为链 + 画像 + 图权重 | 原始用户输入 |
| 输出 | Top-3 候选 + 期望价值 + 分解 | 最终决策 |
| 职责 | 预测用户下一步最可能的行为 | 融合器中的冲突仲裁 |

---

## 2. 架构总览

### 管线位置

```
BehaviorGraph -> [BehaviorPredictor] -> FusionEngine
                    |
                    v
              BehaviorRewarder (接收训练闭环) 
```

### 内部架构

```
[CandidateGenerator] -- LLM 生成 3-5 个候选 + 因果概率
   |
   v
[ValueRanker]
   |-- 0.4 * llm_prob (来自 CandidateGenerator)
   |-- 0.3 * success_rate (来自 BehaviorGraph)
   |-- 0.2 * (1 - cognitive_load) (来自 CognitiveLoadEstimator)
   |-- 0.1 * profile_match (来自 ProfileMatcher)
   |
   v
Top-3 候选 + 分解
   |
   v
[TrainingFeedbackLoop] -- 接收用户实际行为 -> reward -> BehaviorRewarder
```

### 文件结构

```
core/agent/v3_2/predictor/
  __init__.py
  models.py              # PredictionResult, Candidate, ValueBreakdown
  candidate_generator.py # CandidateGenerator (LLM)
  value_ranker.py        # ValueRanker (四维排序)
  cognitive_load.py      # CognitiveLoadEstimator
  profile_matcher.py     # ProfileMatcher
  training_loop.py       # TrainingFeedbackLoop
  predictor.py           # BehaviorPredictor 入口
```

---

## 3. 数据模型 (models.py)

```python
@dataclass
class Candidate:
    action_summary: str
    action_type: str
    llm_probability: float = 0.0
    success_rate: float = 0.5
    cognitive_load: float = 0.0
    profile_match: float = 0.0
    expected_value: float = 0.0

    def compute_value(self):
        self.expected_value = (
            self.llm_probability * 0.4
            + self.success_rate * 0.3
            + (1 - self.cognitive_load) * 0.2
            + self.profile_match * 0.1
        )
        return self.expected_value

@dataclass
class ValueBreakdown:
    llm_prob: float; success_rate: float
    cognitive_load: float; profile_match: float
    expected_value: float

@dataclass
class PredictionResult:
    candidates: list[Candidate]
    breakdowns: dict[str, ValueBreakdown]
    query_mode: str  # full | no_graph | no_llm | fallback
    predicted_top1: str | None
    ask_clarification: bool = False
    latency_ms: float = 0.0

    @property
    def top3(self) -> list[Candidate]:
        return sorted(self.candidates, key=lambda c: -c.expected_value)[:3]

@dataclass
class TrainingSignal:
    predicted: list[Candidate]
    actual_action: str
    reward: float = 0.0
    is_correction: bool = False

    def compute_reward(self):
        top3 = sorted(self.predicted, key=lambda c: -c.expected_value)[:3]
        top1 = top3[0] if top3 else None
        actual_in_top3 = any(c.action_summary == self.actual_action for c in top3)
        actual_is_top1 = top1 and top1.action_summary == self.actual_action
        if actual_is_top1: self.reward = 0.10
        elif actual_in_top3: self.reward = 0.05
        else: self.reward = -0.15
        return self.reward
```

---

## 4. CandidateGenerator

### 4.1 职责

LLM 生成 3-5 个候选行为 + 每个的因果概率。注入 BehaviorGraph Top-3 作为参考。

### 4.2 接口

```python
class CandidateGenerator:
    def __init__(self, llm_provider, max_retries=1):
        self.llm = llm_provider
        self.max_retries = max_retries

    async def generate(
        self, chain_summary: str,
        profile: dict, graph_hints: list[tuple[str, float]]
    ) -> list[tuple[str, float]]:
        prompt = self._build_prompt(chain_summary, profile, graph_hints)
        for _ in range(self.max_retries + 1):
            raw = await self.llm.generate(prompt, max_tokens=200)
            parsed = self._parse(raw)
            if parsed:
                return parsed
        return []

    def _build_prompt(self, chain, profile, hints) -> str:
        return (
            "用户最近行为链: " + chain
            + "\n用户画像: " + str(profile)
            + "\nBehaviorGraph Top-3 高权重后继: " + str(hints)
            + "\n请生成 3-5 个用户下一步最可能的行为 + 每个的因果概率[0,1]。只输出JSON。"
            + "\n[{\"action\": \"...\", \"probability\": 0.xx, \"reason\": \"...\"}]"
        )

    def _parse(self, raw: str) -> list[tuple[str, float]] | None:
        import json
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1: return None
        try:
            data = json.loads(raw[start:end+1])
            return [(d["action"], max(0, min(1, float(d["probability"])))) for d in data]
        except: return None
```

### 4.3 Prompt 注入的 Graph 提示

BehaviorGraph 中当前行为节点的 Top-3 高权重后继作为参考注入。
LLM 以这些为参考但不被限制。

```python
def get_graph_hints(graph: BehaviorGraph, current_step_id: str) -> list[tuple[str, float]]:
    successors = []
    for edge_key, edge in graph.edges.items():
        if edge.from_step_id == current_step_id and not edge.is_deprecated:
            to_step = graph.nodes.get(edge.to_step_id)
            if to_step:
                successors.append((to_step.action_summary, edge.weight))
    successors.sort(key=lambda x: -x[1])
    return successors[:3]
```

### 4.4 边界

| 场景 | 处理 |
|------|------|
| LLM 输出非 JSON | 重试 1 次, 失败 -> 空列表 |
| probability 超出 [0,1] | clamp 到合法范围 |
| 候选 < 3 个 | 用冷启动种子补全 |

---

## 5. ValueRanker (四维排序)

### 5.1 职责

对每个候选行为计算期望价值 = 0.4*llm + 0.3*success + 0.2*(1-load) + 0.1*profile

### 5.2 接口

```python
class ValueRanker:
    W_LLM = 0.4; W_SUCCESS = 0.3; W_COGNITIVE = 0.2; W_PROFILE = 0.1

    def __init__(self, graph, load_estimator=None, profile_matcher=None):
        self.graph = graph
        self.load_est = load_estimator or CognitiveLoadEstimator()
        self.prof_matcher = profile_matcher or ProfileMatcher()

    async def rank(
        self, candidates: list[Candidate],
        profile: dict
    ) -> list[Candidate]:
        for c in candidates:
            c.success_rate = self._get_success_rate(c)
            c.cognitive_load = self.load_est.estimate(c.action_type)
            c.profile_match = await self.prof_matcher.match(c.action_type, c.action_summary, profile)
            c.compute_value()
        candidates.sort(key=lambda c: -c.expected_value)
        return candidates

    def _get_success_rate(self, candidate: Candidate) -> float:
        """从 BehaviorGraph 获取历史成功率"""
        total = 0; success = 0
        for edge in self.graph.edges.values():
            to_step = self.graph.nodes.get(edge.to_step_id)
            if to_step and to_step.action_summary == candidate.action_summary:
                total += edge.success_count + edge.failure_count
                success += edge.success_count
        return success / total if total > 0 else 0.5

    def get_breakdowns(self, candidates: list[Candidate]) -> dict[str, ValueBreakdown]:
        return {
            c.action_summary: ValueBreakdown(
                llm_prob=c.llm_probability, success_rate=c.success_rate,
                cognitive_load=c.cognitive_load, profile_match=c.profile_match,
                expected_value=c.expected_value
            ) for c in candidates
        }
```

---

## 6. CognitiveLoadEstimator

### 6.1 职责

根据行为类型预定义复杂度。用户越累越应推荐简单操作。

### 6.2 接口

```python
class CognitiveLoadEstimator:
    """认知负载估计"""

    LOAD_MAP = {
        "TOOL_EXEC": 0.2,
        "CODE_RUN": 0.3,
        "LOG_CHECK": 0.1,
        "ENTITY_ANALYZE": 0.4,
        "CONFIG_MODIFY": 0.3,
        "EXPLORATION": 0.3,
    }
    DEFAULT_LOAD = 0.3

    def estimate(self, action_type: str) -> float:
        return self.LOAD_MAP.get(action_type, self.DEFAULT_LOAD)

    def adjust_by_turn_count(self, load: float, turn_count: int) -> float:
        """越轮越多, 认知负载越高"""
        fatigue = min(0.3, turn_count * 0.01)
        return min(1.0, load + fatigue)
```

---

## 7. ProfileMatcher

### 7.1 职责

从用户认知画像中获取偏好行为模式, 计算候选行为与画像的匹配度。

### 7.2 接口

```python
class ProfileMatcher:
    """画像匹配度计算"""

    async def match(
        self, action_type: str,
        action_summary: str,
        profile: dict
    ) -> float:
        """
        返回 [0,1] 匹配度。
        从 profile 中获取偏好行为模式 (preferred_patterns),
        计算 action_type 和 action_summary 与模式的匹配。
        """
        patterns = profile.get("preferred_patterns", [])
        if not patterns:
            return 0.0

        matched = 0
        for p in patterns:
            if p.get("type") == action_type:
                matched += 1
            if p.get("action", "") in action_summary:
                matched += 1

        score = matched / (len(patterns) * 2) if patterns else 0
        return min(1.0, score)
```

---

## 8. TrainingFeedbackLoop

### 8.1 职责

预测 -> 用户实际行为 -> 计算 reward -> 传给 BehaviorRewarder

### 8.2 接口

```python
class TrainingFeedbackLoop:
    """训练闭环"""

    def __init__(self, rewarder=None):
        self.rewarder = rewarder

    def on_user_action(
        self, prediction: PredictionResult,
        actual_action: str,
        actual_type: str,
        is_correction: bool = False
    ) -> TrainingSignal:
        signal = TrainingSignal(
            predicted=prediction.candidates,
            actual_action=actual_action,
            is_correction=is_correction
        )
        signal.compute_reward()
        if signal.is_correction:
            signal.reward = -0.20
        if self.rewarder:
            self.rewarder.on_reward(signal)
        return signal

    def update_graph_weights(self, graph: BehaviorGraph, signal: TrainingSignal):
        """根据训练信号更新 BehaviorGraph 边权重"""
        for edge in graph.edges.values():
            to_step = graph.nodes.get(edge.to_step_id)
            if to_step and to_step.action_summary == signal.actual_action:
                edge.record_observation(success=True, correction=signal.is_correction)
```

### 8.3 奖励映射

| 场景 | reward |
|------|--------|
| 精准预测 (Top-1) | +0.10 |
| 方向对 (Top-3) | +0.05 |
| 预测失败 | -0.15 |
| 用户纠正 | -0.20 |
| 纠正+指定正确行为 | -0.20 + 提升正确路径 |

---

## 9. BehaviorPredictor (入口)

### 9.1 职责

编排两步算法 + 三态回退, 返回最终预测结果。

### 9.2 接口

```python
class BehaviorPredictor:
    """行为预测器入口"""

    MODE_FULL = "full"      # LLM + Graph
    MODE_NO_GRAPH = "no_graph"  # 只有 LLM
    MODE_NO_LLM = "no_llm"   # 只有 Graph
    MODE_FALLBACK = "fallback"  # 都不行

    def __init__(
        self, graph: BehaviorGraph,
        candidate_gen: CandidateGenerator,
        value_ranker: ValueRanker,
        profile_matcher: ProfileMatcher,
        cold_start=None
    ):
        self.graph = graph
        self.gen = candidate_gen
        self.ranker = value_ranker
        self.prof = profile_matcher
        self.cold_start = cold_start
        self.training = TrainingFeedbackLoop()

    async def predict(
        self, chain_summary: str,
        current_step_id: str,
        profile: dict
    ) -> PredictionResult:
        start = time.monotonic()
        hints = get_graph_hints(self.graph, current_step_id)

        # Position 1: LLM + Graph 完整模式
        llm_candidates = await self.gen.generate(chain_summary, profile, hints)
        if llm_candidates and hints:
            candidates = await self._build_candidates(llm_candidates)
            ranked = await self.ranker.rank(candidates, profile)
            return self._make_result(ranked, "full", start)

        # Position 2: 只有 LLM (无图数据)
        if llm_candidates:
            candidates = await self._build_candidates(llm_candidates, use_graph=False)
            for c in candidates:
                c.llm_probability *= 0.7  # 调高 LLM 权重
                c.profile_match = await self.prof.match(c.action_type, c.action_summary, profile)
                c.expected_value = c.llm_probability * 0.7 + c.profile_match * 0.3
            return self._make_result(candidates, "no_graph", start)

        # Position 3: 只有 Graph (无 LLM)
        if hints:
            candidates = [Candidate(h[0], "", 0, 0.5, 0, 0, h[1]) for h in hints]
            return self._make_result(candidates, "no_llm", start)

        # Position 4: 全部退避
        fallback = self._get_fallback_candidates()
        result = self._make_result(fallback, "fallback", start)
        result.ask_clarification = True
        return result

    async def _build_candidates(
        self, raw: list[tuple[str, float]], use_graph=True
    ) -> list[Candidate]:
        result = []
        for action, prob in raw:
            c = Candidate(action_summary=action, llm_probability=prob)
            if use_graph:
                c.success_rate = self.ranker._get_success_rate(c)
            result.append(c)
        return result

    def _get_fallback_candidates(self) -> list[Candidate]:
        """退避: 冷启动种子 + 全局高频行为"""
        if self.cold_start:
            seeds = self.cold_start.get_active_seeds()
            return [Candidate(s.to_summary, s.to_type, 0.5, s.initial_weight) for s in seeds[:5]]
        return [Candidate("ask_clarification", "", 0, 0.5)]

    def _make_result(self, candidates, mode, start) -> PredictionResult:
        breakdowns = self.ranker.get_breakdowns(candidates) if candidates else {}
        top1 = candidates[0].action_summary if candidates else None
        low_quality = all(c.expected_value < 0.3 for c in candidates)
        return PredictionResult(
            candidates=candidates, breakdowns=breakdowns,
            query_mode=mode, predicted_top1=top1,
            ask_clarification=low_quality,
            latency_ms=(time.monotonic()-start)*1000
        )

    def on_user_action(self, prediction, actual_action, actual_type, is_correction=False):
        return self.training.on_user_action(prediction, actual_action, actual_type, is_correction)
```

---

## 10. 三态回退策略

| 模式 | 触发条件 | 权重分布 |
|------|---------|---------|
| full | LLM 可用 + Graph 有数据 | 0.4*LLM + 0.3*success + 0.2*(1-load) + 0.1*profile |
| no_graph | LLM 可用 + Graph 无数据 | 0.7*LLM + 0.3*profile |
| no_llm | LLM 不可用 + Graph 有数据 | 仅 Graph.weight + profile |
| fallback | 都不可用 | 冷启动种子 Top-5 |

---

## 11. 测试策略

### 单元测试

| 测试 | 内容 | 优先级 |
|------|------|--------|
| test_candidate | LLM 候选生成, JSON 解析, 重试, 空列表 | P0 |
| test_value_ranker | 四维排序, success_rate 查询, 中性先验 | P0 |
| test_cognitive_load | 各类型负载, 疲劳调整 | P0 |
| test_profile_matcher | 画像匹配, 无画像 | P0 |
| test_training_loop | 精准/方向对/失败/correction reward | P0 |
| test_predictor | 四模式切换, 低质量检测, ask_clarification | P0 |

### 集成测试

| 场景 | 预期 |
|------|------|
| LLM+Graph 完整 | 四维排序 Top-3 |
| 只有 LLM | 0.7*LLM + 0.3*profile |
| 只有 Graph | 仅 Graph 权重排序 |
| 都不可用 | ask_clarification |
| Top-1 命中 -> reward +0.10 | 训练闭环 |
| Top-3 命中 -> reward +0.05 | 训练闭环 |
| 完全失败 -> reward -0.15 | 训练闭环 |
| 用户纠正 -> reward -0.20 | 训练闭环 |
| 所有 expected_value < 0.3 | ask_clarification=True |

### 测试数据

```python
test_chain = "运行程序 -> 查看日志 -> 分析错误 -> 修改代码"
test_profile = {"preferred_patterns": [
    {"type": "LOG_CHECK", "action": "查看"},
    {"type": "CODE_RUN", "action": "修改"},
]}
# 预期预测: 修改代码 -> [运行测试, 查看结果, 搜索文档]
```

---

## 12. 附录

### A. 对照

| 算法 S4 | 实现 | 状态 |
|---------|------|------|
| Step1: LLM 生成候选 | CandidateGenerator | 待实现 |
| Step2: 四维排序 | ValueRanker | 待实现 |
| 认知负载 | CognitiveLoadEstimator | 待实现 |
| 画像匹配 | ProfileMatcher | 待实现 |
| 训练闭环 | TrainingFeedbackLoop | 待实现 |
| 三态回退 | BehaviorPredictor | 待实现 |

### B. 优先级

P0: models -> CognitiveLoadEstimator -> ProfileMatcher -> ValueRanker
P1: CandidateGenerator -> BehaviorPredictor
P2: TrainingFeedbackLoop

### C. 依赖

```
CandidateGenerator -> LLM provider
CognitiveLoadEstimator -> 无
ProfileMatcher -> Cognitive Profile
ValueRanker -> CognitiveLoadEstimator + ProfileMatcher + BehaviorGraph
TrainingFeedbackLoop -> BehaviorRewarder
BehaviorPredictor -> CandidateGenerator + ValueRanker + ColdStartManager
```

### D. 待讨论

1. 四维权重 (0.4/0.3/0.2/0.1) 是否需要上线后动态调整?
2. 认知负载的疲劳系数 0.01/turn 是否太高? 50 轮后 +0.5 会显著改变排序。
3. ProfileMatcher 的简单关键词匹配是否够? 是否需要语义匹配?
4. fallback 模式返回 ask_clarification 后, 下游如何处理?

--- END OF DOCUMENT ---
