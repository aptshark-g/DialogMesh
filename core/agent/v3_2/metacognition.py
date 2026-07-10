'''LLM metacognition - self-assessment and clarification flow (v3.2)
After each pipeline turn, optionally ask the LLM to self-assess its response.
Produces structured signals: confidence, uncertainty, suggested clarifications.
Closed-loop: MetaCognitionResult now carries action recommendations consumed by FusionEngine.
'''
import json, logging, asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MetaAssessment:
    confidence: float = 0.5
    uncertainties: list = field(default_factory=list)
    clarification_needed: bool = False
    clarification_question: str = ''
    raw_assessment: str = ''
    latency_ms: float = 0.0
    turn: int = 0
    timestamp: float = 0.0


@dataclass
class MetaCognitionResult:
    """Structured metacognition result with action recommendation."""
    assessment: MetaAssessment = field(default_factory=MetaAssessment)
    action_recommended: str = "continue"   # "continue" / "clarify" / "fallback" / "escalate"
    confidence_adjustment: float = 0.0      # -0.2 to +0.1


class MetaCognitionAdapter:
    '''Post-generation self-assessment via LLM'''

    ASSESS_PROMPT = '''Assess your confidence in the last response.
Return ONLY a JSON object:
{{"confidence": 0.0-1.0, "uncertainties": ["list", "of", "doubts"],
"clarification_needed": true/false, "clarification_question": "if needed"}}

User said: {query}
You responded: {response}
'''

    MAX_ASSESS_TOKENS = 200

    def __init__(self, llm_provider, enabled=True):
        self.llm = llm_provider
        self.enabled = enabled

    async def assess(self, query: str, response: str,
                     context: Optional[dict] = None) -> MetaAssessment:
        if not self.enabled or not self.llm:
            return MetaAssessment(confidence=0.5)
        import time
        t0 = time.time()
        prompt = self.ASSESS_PROMPT.format(query=query[:200], response=response[:500])
        if context:
            prompt += f'\nContext: stability={context.get("stability", "?")}\n'
        try:
            raw = await self.llm.generate(prompt, max_tokens=self.MAX_ASSESS_TOKENS)
            elapsed = (time.time() - t0) * 1000
            data = json.loads(raw.strip().removeprefix('`json').removesuffix('`').strip())
            return MetaAssessment(
                confidence=float(data.get('confidence', 0.5)),
                uncertainties=data.get('uncertainties', []),
                clarification_needed=bool(data.get('clarification_needed', False)),
                clarification_question=data.get('clarification_question', ''),
                raw_assessment=raw[:200], latency_ms=round(elapsed, 1)
            )
        except Exception as e:
            logging.debug(f'[MetaCog] assessment failed: {e}')
            return MetaAssessment(confidence=0.5, raw_assessment=f'error: {e}')


class MetaCognitionScheduler:

    DEFAULT_TOKEN_THRESHOLD = 10000
    DEFAULT_CHANGE_SENSITIVITY = 0.3

    def __init__(self, adapter, token_threshold=None, change_sensitivity=None):
        self.adapter = adapter
        self.token_threshold = token_threshold or self.DEFAULT_TOKEN_THRESHOLD
        self.change_sensitivity = change_sensitivity or self.DEFAULT_CHANGE_SENSITIVITY
        self.tokens_since_last = 0
        self.assessments = []
        self._error_count = 0
        self._total_count = 0
        self._turn_of_last = 0
        self._latest_result: Optional[MetaCognitionResult] = None

    def record_turn(self, query, response_summary, context, tokens_used):
        if not self.adapter or not self.adapter.enabled:
            return None
        self.tokens_since_last += max(tokens_used, 1)
        self._total_count += 1
        if context and context.get("error"):
            self._error_count += 1
        if self._should_run():
            import asyncio
            task = asyncio.create_task(self._run_assessment(query, response_summary, context))
            return task
        return None

    def _should_run(self):
        if self.tokens_since_last >= self.token_threshold:
            return True
        if self._total_count >= 10:
            cur_rate = self._error_count / max(self._total_count, 1)
            last_rate = getattr(self, "_last_error_rate", 0.0)
            if abs(cur_rate - last_rate) > self.change_sensitivity:
                self._last_error_rate = cur_rate
                return True
        return False

    async def _run_assessment(self, query, response_summary, context):
        self.tokens_since_last = 0
        self._turn_of_last = self._total_count
        assessment = await self.adapter.assess(
            query=query,
            response=response_summary or str(context.get("stability", "?")),
            context=context
        )
        assessment.turn = self._total_count
        assessment.timestamp = __import__("time").time()
        self.assessments.append(assessment)
        # Build MetaCognitionResult with action recommendation
        conf = assessment.confidence
        if conf < 0.3:
            action = "fallback"
            adj = -0.15
        elif conf < 0.5:
            action = "clarify"
            adj = -0.1
        elif conf < 0.7:
            action = "continue"
            adj = -0.1
        else:
            action = "continue"
            adj = 0.05
        result = MetaCognitionResult(
            assessment=assessment,
            action_recommended=action,
            confidence_adjustment=adj,
        )
        self._latest_result = result
        return result

    def get_latest_result(self) -> Optional[MetaCognitionResult]:
        """Retrieve the most recent assessment result."""
        return self._latest_result

    def should_clarify(self) -> bool:
        """Helper: true if latest result recommends clarification."""
        return self._latest_result is not None and self._latest_result.action_recommended == "clarify"

    def configure(self, token_threshold=None, change_sensitivity=None):
        if token_threshold is not None:
            self.token_threshold = max(100, token_threshold)
        if change_sensitivity is not None:
            self.change_sensitivity = max(0.05, min(1.0, change_sensitivity))

    def get_stats(self):
        return {
            "total_assessments": len(self.assessments),
            "tokens_since_last": self.tokens_since_last,
            "token_threshold": self.token_threshold,
            "change_sensitivity": self.change_sensitivity,
            "error_rate": round(self._error_count / max(self._total_count, 1), 3),
            "last_conf": round(self.assessments[-1].confidence, 2) if self.assessments else None,
            "last_turn": self._turn_of_last,
        }
