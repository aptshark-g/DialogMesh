'''LLM metacognition - self-assessment and clarification flow
After each pipeline turn, optionally ask the LLM to self-assess its response.
Produces structured signals: confidence, uncertainty, suggested clarifications.
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

class MetaCognitionAdapter:
    '''Post-generation self-assessment via LLM'''

    ASSESS_PROMPT = '''Assess your confidence in the last response.
Return ONLY a JSON object:
{"confidence": 0.0-1.0, "uncertainties": ["list", "of", "doubts"],
"clarification_needed": true/false, "clarification_question": "if needed"}

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
