"""约束补全编译器主入口"""
import time
from .models import SlotValue, ParseResult, ParseContext
from .llm_pseudo_parser import LLMPseudoParser
from .rule_engine import RuleConstraintEngine, FrameLibrary
from .stability_scorer import StabilityScorer
from .streaming_validator import StreamingValidator
from .degradation_manager import DegradationManager


class HybridCompiler:
    """三步流水线: LLM伪拆解 -> 规则引擎 -> 稳定性评分"""

    def __init__(self, llm_provider, frame_library: object = None, max_retries: int = 1):
        self.llm_parser = LLMPseudoParser(llm_provider, max_retries)
        self.library = frame_library or FrameLibrary.load_default()
        self.rule_engine = RuleConstraintEngine(self.library)
        self.scorer = StabilityScorer()
        self.validator = StreamingValidator(self.rule_engine)
        self.degradation = DegradationManager(max_retries)

    async def process(self, sentence: str, context: object = None) -> ParseResult:
        start = time.monotonic()
        ctx = context or ParseContext()

        if not self.degradation.should_use_llm():
            return await self._rule_only(sentence, ctx, start)

        # Step 1: LLM 伪拆解
        llm_out = await self.llm_parser.parse(sentence, ctx)
        if llm_out is None:
            self.degradation.on_failure()
            return await self.process(sentence, ctx)

        self.degradation.on_success()
        slots: dict[str, SlotValue] = {}
        for name, data in llm_out["slots"].items():
            slots[name] = SlotValue(
                value=data["value"],
                confidence=data["confidence"],
                source="llm"
            )

        # 检查是否全维度低置信 -> 全量规则消解
        all_low = all(s.confidence < RuleConstraintEngine.CONFIDENCE_THRESHOLD for s in slots.values())
        if all_low:
            slots = self.rule_engine.resolve_all(slots, ctx)
        else:
            # 流式验证
            for name, slot in slots.items():
                self.validator.on_slot_received(name, slot, ctx)
            slots = self.validator.resolve(slots)
            # Step 2: 选择性深挖
            slots = self.rule_engine.refine(slots, ctx)

        # Step 3: 稳定性评分
        stability = self.scorer.score(slots)

        result = ParseResult(
            slots=slots, stability=stability,
            utterance_type=llm_out.get("utterance_type", "statement"),
            sentiment=llm_out.get("sentiment", "neutral"),
            undefined=self.scorer.is_undefined(stability)
        )
        if not result.is_reliable:
            result.reasons.append("stability_below_threshold")
        result.latency_ms = (time.monotonic() - start) * 1000
        return result

    async def _rule_only(self, sentence: str, ctx: ParseContext, start: float) -> ParseResult:
        """纯规则降级路径"""
        slots = self.degradation.rule_parse(sentence, self.library)
        if slots:
            slots = self.rule_engine.refine(slots, ctx)
        stability = self.scorer.score(slots)
        result = ParseResult(
            slots=slots, stability=stability,
            degraded=True, undefined=self.scorer.is_undefined(stability)
        )
        result.latency_ms = (time.monotonic() - start) * 1000
        return result

    def get_status(self) -> dict:
        return self.degradation.get_status()
