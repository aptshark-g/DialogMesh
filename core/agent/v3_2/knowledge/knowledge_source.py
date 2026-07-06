# Abstract Knowledge Source
from abc import ABC, abstractmethod
from .models import KnowledgeEntry
class KnowledgeSource(ABC):
    @property
    @abstractmethod
    def source_name(self): pass
    @property
    @abstractmethod
    def base_confidence(self): pass
    @abstractmethod
    async def query(self, slot_name, value, domain='general'):
        pass
