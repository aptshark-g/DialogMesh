"""ExtractionBlueprint — pluggable semantic extraction providers.

Four built-in blueprints with automatic fallback:
  extraction_regex    → always available (jieba segmentation)
  extraction_stanza   → Stanza Chinese dependency parsing (~50ms)
  extraction_lmstudio → requires LMStudio at localhost:1234
  extraction_deepseek → requires DEEPSEEK_API_KEY
"""
from __future__ import annotations
import os, re, logging, urllib.request
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractedDefinition:
    subject: str; text: str; confidence: float

@dataclass
class ExtractedRelation:
    source: str; target: str; predicate: str; confidence: float

@dataclass
class ExtractionResult:
    provider: str
    definitions: List[ExtractedDefinition] = field(default_factory=list)
    relations: List[ExtractedRelation] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ExtractionProvider:
    name = "base"; requires_llm = False
    def available(self) -> bool: return True
    def extract(self, text: str, concepts: List[str]) -> ExtractionResult:
        raise NotImplementedError


class RegexExtractionProvider(ExtractionProvider):
    """Hybrid: jieba segmentation + regex for definitions/relations."""
    name = "regex"; requires_llm = False

    def available(self) -> bool: return True

    def extract(self, text: str, concepts: List[str]) -> ExtractionResult:
        result = ExtractionResult(provider="regex")
        try:
            from core.agent.v4.tiered.jieba_parser import JiebaRelationParser
            jrp = JiebaRelationParser()
            tuples = jrp.extract(text)
            for tup in tuples:
                if tup["type"] == "definition":
                    result.definitions.append(ExtractedDefinition(tup["subject"],tup["object"][:300],tup["confidence"]))
                else:
                    result.relations.append(ExtractedRelation(tup["subject"],tup["object"],tup["predicate"],tup["confidence"]))
            # Regex declarative patterns
            cs = '|'.join(re.escape(c) for c in concepts) if concepts else r'[A-Z][a-z]+(?:[A-Z][a-z]+)+'
            for m in re.finditer(rf'({cs})\s*(?:是|定义为|指的是|负责|用于|指|根据)\s*(.{{5,300}}?)(?:[。；;]|$)', text):
                result.definitions.append(ExtractedDefinition(m.group(1),m.group(2).strip()[:300],0.5))
            for pat,pred in [(rf'({cs})\s*(?:依赖于|依赖|基于)\s*({cs})',"depends_on"),(rf'({cs})\s*调用\s*({cs})',"calls")]:
                for m in re.finditer(pat, text):
                    result.relations.append(ExtractedRelation(m.group(1),m.group(2),pred,0.5))
        except Exception as e:
            result.errors.append(str(e))
        return result


class StanzaExtractionProvider(ExtractionProvider):
    """Stanza Chinese dependency parsing — Tier 2 (~50ms)."""
    name = "stanza"; requires_llm = False

    def available(self) -> bool:
        try:
            from core.agent.v4.tiered.stanza_parser import StanzaParser
            return StanzaParser().available()
        except: return False

    def extract(self, text: str, concepts: List[str]) -> ExtractionResult:
        result = ExtractionResult(provider="stanza")
        try:
            from core.agent.v4.tiered.stanza_parser import StanzaParser
            sp = StanzaParser()
            tuples = sp.extract_tuples(text)
            for t in tuples:
                result.relations.append(ExtractedRelation(
                    t["subject"], t["object"], t["predicate"], t["confidence"]))
            p = sp.parse(text)
            if p.subject and p.predicate:
                def_kw = ["是","指","负责","定义"]
                if any(k in text for k in def_kw):
                    result.definitions.append(ExtractedDefinition(
                        p.subject, p.object or text[:200], p.confidence))
        except Exception as e:
            result.errors.append(str(e))
        return result


class LMStudioExtractionProvider(ExtractionProvider):
    name = "lmstudio"; requires_llm = True
    def __init__(self, base_url="http://127.0.0.1:1234/v1", model="nvidia/nemotron-3-nano-4b"):
        self._base_url = base_url; self._model = model; self._p = None

    def available(self) -> bool:
        try:
            urllib.request.urlopen(urllib.request.Request(f"{self._base_url}/models"), timeout=5)
            return True
        except: return False

    def extract(self, text: str, concepts: List[str]) -> ExtractionResult:
        result = ExtractionResult(provider="lmstudio")
        if not concepts: return result
        try:
            if not self._p:
                from core.agent.llm_providers.openai_provider import OpenAIProvider
                self._p = OpenAIProvider("lmstudio",{"api_key":"lm-studio","base_url":self._base_url,"model":self._model})
            from core.agent.llm_providers.base import GenerateRequest
            cl = ", ".join(concepts[:5])
            prompt = (f"从以下文本提取关于{cl}的定义和关系。JSON:\n{{definitions:[{{subject,text}}],relations:[{{source,target,predicate:depends_on|calls|produces|extends|implements}}]}}\n文本:{text[:2000]}\nJSON:")
            resp = self._p.generate(GenerateRequest(prompt=prompt,max_tokens=500))
            jt = resp.text if hasattr(resp,'text') else str(resp)
            import json; m = re.search(r'\{[\s\S]*\}', jt)
            if m:
                d = json.loads(m.group())
                for x in d.get("definitions",[]): result.definitions.append(ExtractedDefinition(x.get("subject",""),x.get("text",""),0.7))
                for x in d.get("relations",[]): result.relations.append(ExtractedRelation(x.get("source",""),x.get("target",""),x.get("predicate","depends_on"),0.6))
        except Exception as e: result.errors.append(str(e))
        return result


class DeepSeekExtractionProvider(ExtractionProvider):
    name = "deepseek"; requires_llm = True
    def __init__(self, model="deepseek-chat"): self._model = model; self._p = None
    def available(self) -> bool: return bool(os.environ.get("DEEPSEEK_API_KEY",""))

    def extract(self, text: str, concepts: List[str]) -> ExtractionResult:
        result = ExtractionResult(provider="deepseek")
        if not concepts: return result
        try:
            if not self._p:
                from core.agent.llm_providers.openai_provider import OpenAIProvider
                self._p = OpenAIProvider("deepseek",{"api_key":os.environ.get("DEEPSEEK_API_KEY",""),"base_url":"https://api.deepseek.com/v1","model":self._model})
            from core.agent.llm_providers.base import GenerateRequest
            cl = ", ".join(concepts[:5])
            prompt = (f"Extract definitions and relations for: {cl}. JSON:\n{{definitions:[{{subject,text}}],relations:[{{source,target,predicate:depends_on|calls|produces|extends|implements}}]}}\nText:{text[:2000]}\nJSON:")
            resp = self._p.generate(GenerateRequest(prompt=prompt,max_tokens=500))
            jt = resp.text if hasattr(resp,'text') else str(resp)
            import json; m = re.search(r'\{[\s\S]*\}', jt)
            if m:
                d = json.loads(m.group())
                for x in d.get("definitions",[]): result.definitions.append(ExtractedDefinition(x.get("subject",""),x.get("text",""),0.85))
                for x in d.get("relations",[]): result.relations.append(ExtractedRelation(x.get("source",""),x.get("target",""),x.get("predicate","depends_on"),0.75))
        except Exception as e: result.errors.append(str(e))
        return result


@dataclass
class ExtractionBlueprint:
    id: str; provider: ExtractionProvider; fallback_id: Optional[str] = None
    def available(self) -> bool: return self.provider.available()


class ExtractionOrchestrator:
    def __init__(self):
        self._bp: Dict[str, ExtractionBlueprint] = {}; self._order: List[str] = []; self._stats: Dict[str,int] = {}

    def register(self, bp: ExtractionBlueprint):
        self._bp[bp.id] = bp
        if bp.id not in self._order: self._order.append(bp.id); self._stats[bp.id] = 0

    def extract(self, text: str, concepts: List[str], preferred: str = None) -> ExtractionResult:
        if preferred and preferred in self._bp:
            bp = self._bp[preferred]
            if bp.available(): self._stats[preferred] += 1; return bp.provider.extract(text, concepts)
            bid = bp.fallback_id
            while bid and bid in self._bp:
                b2 = self._bp[bid]
                if b2.available(): self._stats[bid] += 1; return b2.provider.extract(text, concepts)
                bid = b2.fallback_id
        for bid in self._order:
            bp = self._bp[bid]
            if bp.available(): self._stats[bid] += 1; return bp.provider.extract(text, concepts)
        return ExtractionResult(provider="none", errors=["No provider available"])

    @property
    def stats(self) -> dict: return dict(self._stats)
