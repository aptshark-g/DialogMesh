# DialogMesh L1Summary --- 工程实现文档

> **文档编号**: ENGINEERING-V3.3-L1SUMMARY-010  
> **版本**: v1.0  
> **日期**: 2026-07-05  
> **状态**: 工程待实现  
> **对应算法文档**: DESIGN_V3_3_ALGORITHM.md S10  
> **前置算法**: 三级自适应摘要引擎  
> **原则**: 行为和因果信息在 meta_info 中零丢失, LLM 压缩的 core_semantics 只用于检索。  

---
## 1. 文档目标与范围
为 L1Summary 提供工程实现规范。覆盖三级自适应分类、结构化元信息提取、异步存储、L2 重新聚合触发。

---
## 2. 数据模型
```python
@dataclass
class L1SummaryEntry:
    turn_id: str
    strategy: str           # deterministic | template | llm
    core_semantics: str     # 核心语义摘要
    meta_info: dict         # 结构化元信息
    raw_text: str = ""      # 原文（仅 deterministic 策略保留）
    created_at: float = 0.0

@dataclass
class L1MetaInfo:
    prev_action: str = ""
    current_action: str = ""
    predicted_next: list[str] = field(default_factory=list)
    causal_events: list[str] = field(default_factory=list)
    associations: list[str] = field(default_factory=list)
    is_topic_switch: bool = False
    user_satisfaction: str = "neutral"
    correction_detected: bool = False
    topic_id: str = ""

class ContentCategory(str, Enum):
    DETERMINISTIC = "deterministic"   # 工具输出/代码
    SEMI_DETERMINISTIC = "template"   # 明确指令/参数
    NON_DETERMINISTIC = "llm"         # 模糊需求/情感
```

---
## 3. ContentClassifier
```python
class ContentClassifier:
    DETERMINISTIC_PATTERNS = [r"return (0x[0-9a-f]+|\d+)", r"error (code|message)", r"execute"]
    CONSECUTIVE_LLM_SKIP = 5  # 连续 5 轮确定性 -> 跳过 LLM

    def classify(self, turn, consecutive_deterministic: int) -> ContentCategory:
        text = turn.get("raw_text", "")
        turn_type = turn.get("type", "")
        if turn_type == "tool_output" or turn_type == "code_result":
            return ContentCategory.DETERMINISTIC
        import re
        for pattern in self.DETERMINISTIC_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return ContentCategory.DETERMINISTIC
        if ("修改" in text or "设置" in text) and any(c.isdigit() for c in text):
            return ContentCategory.SEMI_DETERMINISTIC
        if consecutive_deterministic >= self.CONSECUTIVE_LLM_SKIP:
            return ContentCategory.SEMI_DETERMINISTIC
        return ContentCategory.NON_DETERMINISTIC
```

---
## 4. MetaInfoExtractor
```python
class MetaInfoExtractor:
    def extract(self, turn, prev_type, prediction) -> L1MetaInfo:
        info = L1MetaInfo()
        info.prev_action = prev_type
        info.current_action = turn.get("action_type", "")
        if prediction:
            info.predicted_next = [c.action_summary for c in prediction.top3]
        if turn.get("is_correction", False):
            info.correction_detected = True
            info.causal_events.append("USER_CORRECTION")
        if turn.get("is_error", False):
            info.causal_events.append("ERROR_TRIGGERED")
        info.associations = turn.get("associations", [])
        info.is_topic_switch = turn.get("is_topic_switch", False)
        info.user_satisfaction = turn.get("sentiment", "neutral")
        return info
```

---
## 5. SummaryGenerator
```python
class SummaryGenerator:
    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def generate(
        self, category: ContentCategory, turn, meta: L1MetaInfo
    ) -> str:
        if category == ContentCategory.DETERMINISTIC:
            return f"{meta.current_action}: {turn.get('result', '')}"
        if category == ContentCategory.SEMI_DETERMINISTIC:
            intent = turn.get("intent", "")
            entities = turn.get("entities", {})
            params = turn.get("params", {})
            return f"[用户要求] {intent} | 实体: {entities} | 参数: {params}"
        if self.llm:
            raw = turn.get("raw_text", "")
            return self._llm_compress(raw)
        return turn.get("raw_text", "")[:100]

    def _llm_compress(self, text: str, max_chars=100) -> str:
        prompt = f"压缩到{max_chars}字以内, 保留行为意图: {text}"
        return self.llm.generate(prompt, max_tokens=50) if self.llm else text[:max_chars]
```

---
## 6. L1Summary (入口)
```python
class L1Summary:
    L2_REAGGREGATE_THRESHOLD = 5

    def __init__(self, classifier=None, extractor=None, generator=None):
        self.classifier = classifier or ContentClassifier()
        self.extractor = extractor or MetaInfoExtractor()
        self.generator = generator or SummaryGenerator()
        self.entries: list[L1SummaryEntry] = []
        self.consecutive_deterministic = 0
        self.topic_summary_count: dict[str, int] = {}

    async def process(self, turn, prev_type, prediction=None) -> L1SummaryEntry:
        category = self.classifier.classify(turn, self.consecutive_deterministic)
        if category == ContentCategory.DETERMINISTIC:
            self.consecutive_deterministic += 1
        else:
            self.consecutive_deterministic = 0

        meta = self.extractor.extract(turn, prev_type, prediction)
        core = self.generator.generate(category, turn, meta)

        entry = L1SummaryEntry(
            turn_id=turn.get("turn_id", ""),
            strategy=category.value, core_semantics=core,
            meta_info=asdict(meta)
        )
        self.entries.append(entry)

        topic_id = meta.topic_id
        self.topic_summary_count[topic_id] = self.topic_summary_count.get(topic_id, 0) + 1
        needs_reaggregate = self.topic_summary_count[topic_id] >= self.L2_REAGGREGATE_THRESHOLD
        if needs_reaggregate:
            self.topic_summary_count[topic_id] = 0  # 重置
            # 发出 L2 重新聚合信号
        return entry
```

---
## 7. 测试策略
| 测试 | 内容 | 优先级 |
|------|------|--------|
| test_content_classifier | 三类内容分类, 连续确定性跳过 | P0 |
| test_meta_extractor | 8 字段提取, 纠正/错误检测 | P0 |
| test_summary_generator | 三策略生成, LLM 压缩超时回退 | P0 |
| test_l1summary | 完整流程, L2 触发, 并发安全 | P0 |
--- END OF DOCUMENT ---