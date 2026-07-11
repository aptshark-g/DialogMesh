# DialogMesh 约束补全编译器 --- 工程实现文档

> **文档编号**: ENGINEERING-V3.3-COMPILER-001  
> **版本**: v1.0  
> **日期**: 2026-07-05  
> **状态**: 工程待实现  
> **对应算法文档**: DESIGN_V3_3_ALGORITHM.md S1  
> **对应设计文档**: DESIGN_V3_2.md  
> **原则**: NL -> {语义槽位, 置信度, 稳定性}  

---

## 1. 文档目标与范围

为约束补全编译器(HybridCompiler)提供完整的工程实现规范。
覆盖数据模型、LLM伪拆解器、规则约束引擎、稳定性评分器、降级路径、流式验证。

### 边界

| 边界 | 包含 | 不包含 |
|------|------|--------|
| 输入 | NL + ParseContext | 行为链、系统状态 |
| 输出 | {slots, stability, degraded} | 意图分类、预测、决策 |
| 异常 | LLM不可用->降级 | 不向上传播 |

---

## 2. 架构总览

### 三步流水线

```
输入: sentence + ParseContext
  |
  v
[Step1: LLM伪拆解] -> {slot: {value, confidence}}
  |
  v
[Step2: 规则选择性深挖] -> 覆盖 low-confidence 槽位
  |
  v
[Step3: 稳定性评分] -> stability = mean(ci) * (1-var(ci))
  |
  v
输出: ParseResult
```

### 降级路径
LLM可用->三步流水线 | LLM不可用->纯规则 | 连续3次失败->纯规则模式

### 文件结构

```
core/agent/v3_2/compiler/
  __init__.py
  models.py          # SlotValue, ParseResult, ParseContext, ConstraintRule
  llm_pseudo_parser.py  # LLMPseudoParser
  rule_engine.py     # FrameLibrary, RuleConstraintEngine
  stability_scorer.py  # StabilityScorer
  streaming_validator.py # StreamingValidator
  degradation_manager.py # DegradationManager
  hybrid_compiler.py # HybridCompiler 入口
```

---

## 3. 数据模型 (models.py)

```python
@dataclass
class SlotValue:
    value: str
    confidence: float = 0.5
    source: str = "llm"  # llm|rule|hybrid
    overridden: bool = False

@dataclass
class ParseContext:
    entities: dict[str, list[str]] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    prev_stability: float = 0.0
    turn_count: int = 0

    def add_entity(self, category: str, value: str):
        ...

@dataclass
class ParseResult:
    slots: dict[str, SlotValue] = field(default_factory=dict)
    stability: float = 0.0
    utterance_type: str = "statement"
    degraded: bool = False
    undefined: bool = False
    reasons: list[str] = field(default_factory=list)
    latency_ms: float = 0.0

    @property
    def is_reliable(self) -> bool:
        return self.stability >= 0.6 and not self.undefined

@dataclass
class ConstraintRule:
    frame_name: str
    slot_name: str
    candidates: list[str]
    incompatible_with: dict[str, list[str]] = field(default_factory=dict)
    priority: int = 0
    condition: str = ""

    def is_applicable(self, ctx: ParseContext) -> bool:
        return True if not self.condition else self._eval(ctx)
```

### 标准槽位

| agent | action | patient | result | cause |
动态扩展：非标准槽位名保留不做过滤。

---

## 4. LLMPseudoParser

职责: 调用LLM将NL映射为{slot->{value, confidence}}。
不做推理，不做规则检查。

```python
class LLMPseudoParser:
    def __init__(self, llm_provider, max_retries=1):
        self.llm = llm_provider
        self.max_retries = max_retries

    async def parse(self, sentence: str, context: ParseContext = None) -> dict | None:
        prompt = self._build_prompt(sentence, context)
        for attempt in range(self.max_retries + 1):
            raw = await self.llm.generate(prompt, max_tokens=120)
            parsed = self._parse_response(raw)
            if parsed:
                return parsed
        return None
```

Prompt: 指示LLM只做结构化回显，不推理。
每个槽位输出 value + confidence（[0,1]）。

边界: 非JSON->重试1次; JSON缺字段->返回None->降级; confidence clamp到[0,1]

---

## 5. RuleConstraintEngine

### FrameLibrary

```python
@dataclass
class FrameLibrary:
    rules: list[ConstraintRule] = field(default_factory=list)

    @classmethod
    def load_default(cls):  # 20-30个初始帧
        ...

    def query(self, slot_name, value, domain="general"):
        return [r for r in self.rules if r.slot_name == slot_name]

    def get_frame(self, name):
        return [r for r in self.rules if r.frame_name == name]
```

### 消解算法（四步）

```python
class RuleConstraintEngine:
    THRESHOLD = 0.75

    def refine(self, slots: dict[str, SlotValue], ctx: ParseContext):
        result = dict(slots)
        for name, slot in slots.items():
            if slot.confidence >= self.THRESHOLD:
                continue
            cands = self._resolve(name, slot, slots, ctx)
            if cands:
                result[name] = self._pick(cands)
        return result

    def _resolve(self, name, slot, all_slots, ctx):
        # Step1: 约束框架匹配
        frame_name = f"{name}({slot.value})"
        rules = self.library.get_frame(frame_name)
        if not rules: return []
        # Step2: 跨维度交叉验证
        cands = {}
        for r in rules:
            for c in r.candidates:
                cands[c] = cands.get(c,0) + 1.0/len(r.candidates)
        for r in rules:
            for oslot, excls in r.incompatible_with.items():
                if oslot in all_slots and all_slots[oslot].value in excls:
                    cands = {k:v for k,v in cands.items() if k not in excls}
        # Step3: 上下文补充
        for elist in ctx.entities.values():
            for e in elist:
                if e not in cands: cands[e] = 0.5
        # Step4: 排序
        if not cands: return []
        sorted_c = sorted(cands.items(), key=lambda x:-x[1])
        return [(v, 0.7 + (s/sorted_c[0][1])*0.2) for v,s in sorted_c[:3]]
```

复杂度: 只对低置信度维度做功(~3候选) -> <3ms。

---

## 6. StabilityScorer

```python
class StabilityScorer:
    MIN_STABILITY = 0.6

    def score(self, slots: dict[str, SlotValue]) -> float:
        if not slots: return 0.0
        cs = [s.confidence for s in slots.values()]
        import statistics
        m = statistics.mean(cs)
        v = statistics.variance(cs) if len(cs) > 1 else 0
        return max(0.0, min(1.0, m * (1.0 - v)))

    def is_undefined(self, s: float) -> bool:
        return s < self.MIN_STABILITY
```

示例: mean=0.94 var=0.001 -> 0.94 | mean=0.8 var=0.06 -> 0.75 | mean=0.5 -> 0.5

---

## 7. StreamingValidator

流式输出中每收到一个key-value即与帧库比对。硬冲突标记，输出完成后覆盖。

```python
@dataclass
class ValidationConflict:
    slot_name: str; llm_value: str; rule_suggestion: str
    conflict_type: str; resolved: bool = False

class StreamingValidator:
    def __init__(self, engine: RuleConstraintEngine):
        self.engine = engine; self.conflicts = []

    def on_slot_received(self, name, slot, ctx):
        for rule in self.engine.library.query(name, slot.value):
            if rule.is_applicable(ctx) and slot.value not in rule.candidates and rule.priority >= 10:
                self.conflicts.append(ValidationConflict(name, slot.value, rule.candidates[0], "hard"))

    def resolve(self, slots):
        result = dict(slots)
        for c in self.conflicts:
            if c.conflict_type == "hard" and not c.resolved:
                result[c.slot_name] = SlotValue(c.rule_suggestion, 0.82, "rule", True)
                c.resolved = True
        return result
```

---

## 8. DegradationManager

三态切换: full(LLM+规则) | rule_only(纯规则) | none(退避)

```python
class DegradationManager:
    MODE_FULL = "full"; MODE_RULE = "rule"; MODE_NONE = "none"

    def __init__(self, max_retries=1, threshold=3):
        self.mode = self.MODE_FULL; self.fails = 0; self.threshold = threshold

    def on_success(self):
        self.fails = 0
        if self.mode != self.MODE_FULL: self.mode = self.MODE_FULL

    def on_failure(self):
        self.fails += 1
        if self.fails >= self.threshold: self.mode = self.MODE_RULE

    def should_use_llm(self): return self.mode == self.MODE_FULL

    def rule_parse(self, sentence, library):
        # jieba分词 + 简单词性标注 + 帧库匹配
        import jieba
        words = jieba.lcut(sentence)
        # 动词->action, 名词->agent/patient
        slots = {}
        for w, pos in simple_pos_tag(words):
            if pos == "v": slots["action"] = SlotValue(w, 0.7, "rule")
            elif pos == "n":
                if "agent" not in slots: slots["agent"] = SlotValue(w, 0.6, "rule")
                else: slots["patient"] = SlotValue(w, 0.6, "rule")
        return slots
```

### simple_pos_tag
基于词表: VERBS={运行,修改,删除,查看,执行,分析,...}, NOUNS={程序,日志,配置,...}
不在词表中的词 -> pos=x

---

## 9. HybridCompiler (入口)

```python
class HybridCompiler:
    def __init__(self, llm_provider, frame_lib=None, max_retries=1):
        self.llm = LLMPseudoParser(llm_provider, max_retries)
        self.lib = frame_lib or FrameLibrary.load_default()
        self.rule = RuleConstraintEngine(self.lib)
        self.scorer = StabilityScorer()
        self.val = StreamingValidator(self.rule)
        self.deg = DegradationManager(max_retries)

    async def process(self, sentence, context=None):
        start = time.monotonic(); ctx = context or ParseContext()
        if not self.deg.should_use_llm():
            slots = self.deg.rule_parse(sentence, self.lib)
            s = self.scorer.score(slots)
            r = ParseResult(slots, s, degraded=True, undefined=self.scorer.is_undefined(s))
            r.latency_ms = (time.monotonic()-start)*1000; return r
        # Step1: LLM
        llm_out = await self.llm.parse(sentence, ctx)
        if not llm_out: self.deg.on_failure(); return await self.process(sentence, ctx)
        slots = {n: SlotValue(d["value"], d["confidence"], "llm") for n,d in llm_out["slots"].items()}
        # Validate
        for n,s in slots.items(): self.val.on_slot_received(n, s, ctx)
        slots = self.val.resolve(slots)
        # Step2: 规则
        slots = self.rule.refine(slots, ctx)
        # Step3: 稳定性
        s = self.scorer.score(slots)
        r = ParseResult(slots, s, llm_out.get("utterance_type","statement"), undefined=self.scorer.is_undefined(s))
        if r.is_reliable: self.deg.on_success()
        else: r.reasons.append("stability_below_threshold")
        r.latency_ms = (time.monotonic()-start)*1000; return r
```

---

## 10. 测试策略

### 单元测试 (P0)

| 测试 | 内容 |
|------|------|
| test_models | SlotValue clamp, ParseResult.is_reliable, ConstraintRule |
| test_llm_parser | prompt构造, 响应解析, 重试, 非JSON |
| test_rule_engine | 四步消解, 交叉验证, 上下文补充, 全量/跳过 |
| test_stability | 不同置信度向量, 空槽位, 单槽位 |
| test_validator | 硬冲突, soft冲突, resolve覆盖 |
| test_degradation | 三态切换, 失败计数, 恢复, 纯规则降级 |
| test_compiler | 三步流水线, 降级重入, undefined输出 |

### 集成测试场景

1. LLM可用+完整流程: LLM输出JSON -> 规则引擎 -> 稳定性
2. LLM不可用: LLM返回None -> 纯规则降级
3. 非JSON+重试: 非JSON -> 重试 -> 降级
4. 硬冲突: agent=汽车 + action frame -> 规则覆盖
5. all confidence > 0.75: 跳过Step2
6. all confidence < 0.75: 全量规则消解
7. stability < 0.6: undefined flag
8. 连续3次失败: 自动切纯规则

---

## 11. 附录

### 与算法设计对照

| 算法S1 | 工程实现 | 状态 |
|--------|---------|------|
| Step1 LLM伪拆解 | LLMPseudoParser | 待实现 |
| Step2 规则深挖 | RuleConstraintEngine | 待实现 |
| Step3 稳定性 | StabilityScorer | 待实现 |
| 流式验证 | StreamingValidator | 待实现 |
| 降级路径 | DegradationManager | 待实现 |
| 入口 | HybridCompiler | 待实现 |

### 优先级

P0: models -> StabilityScorer -> LLMPseudoParser -> RuleConstraintEngine -> HybridCompiler
P1: DegradationManager + 纯规则降级 | StreamingValidator
P2: FrameLibrary完整帧库内容

### 待讨论

1. confidence校准: logprobs vs LLM自报? 首期只用自报。
2. 帧库: 初始20-30帧, 上线后按频率扩展。
3. 降级质量: jieba简单词性标注60-70%准确率, 是否有更好方案?

---


### 参数配置

| 参数 | 初始值 | 锚点来源 | 区间 | 自适应信号 | 速率 |
|------|--------|---------|------|-----------|------|
| threshold | 0.75 | Stanza CTB UAS 87-89% | [0.65, 0.85] | LLM vs rule conf diff | +-0.02/次 |
| min_stability | 0.6 | 经验值(过承诺不安全) | [0.50, 0.70] | 编译器输出后验验证 | +-0.01/50轮 |
| max_retries | 1 | 经验值 | [0, 3] | LLM 连续失败 | 手动 |

--- END OF DOCUMENT ---
