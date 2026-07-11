# FrameLibrary source (built-in rules)
from .knowledge_source import KnowledgeSource
from .models import KnowledgeEntry
from ..compiler.rule_engine import FrameLibrary
class FrameLibrarySource(KnowledgeSource):
    def __init__(self, library=None):
        self.library = library or FrameLibrary.load_default()
    @property
    def source_name(self): return 'manual_rule'
    @property
    def base_confidence(self): return 0.90
    async def query(self, slot_name, value, domain='general'):
        rules = self.library.query(slot_name, value, domain)
        if not rules:
            return []
        entries = []
        for r in rules:
            entries.append(KnowledgeEntry(
                slot_name, r.frame_name, r.candidates,
                source_name='manual_rule', confidence=0.90,
                domain=r.domain
            ))
        return entries
