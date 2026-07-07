"""??/??/???? ? ?? O(1) ?????????"""
from typing import Dict, List, Optional
from .models import DiscourseBlock, DiscourseEntity


class Indexer:
    """
    ????????:
    - entity -> blocks (??????)
    - intent -> blocks (??????)
    - turn -> block_id (??????)
    - keyword -> blocks (?????)
    """

    def __init__(self):
        self.entity_to_blocks: Dict[str, List[str]] = {}
        self.intent_to_blocks: Dict[str, List[str]] = {}
        self.turn_to_block: Dict[int, str] = {}
        self.keyword_index: Dict[str, List[str]] = {}

    def index_block(self, block: DiscourseBlock):
        """???? DiscourseBlock"""
        bid = block.block_id

        # ????
        for entity in block.entities:
            key = entity.text if isinstance(entity, DiscourseEntity) else str(entity)
            if key not in self.entity_to_blocks:
                self.entity_to_blocks[key] = []
            if bid not in self.entity_to_blocks[key]:
                self.entity_to_blocks[key].append(bid)

        # EDU ????
        for edu in block.atomic_units:
            for ent in edu.entities:
                if ent not in self.entity_to_blocks:
                    self.entity_to_blocks[ent] = []
                if bid not in self.entity_to_blocks[ent]:
                    self.entity_to_blocks[ent].append(bid)

        # ????
        intent = block.primary_intent
        if intent not in self.intent_to_blocks:
            self.intent_to_blocks[intent] = []
        if bid not in self.intent_to_blocks[intent]:
            self.intent_to_blocks[intent].append(bid)

        for sec in block.secondary_intents:
            if sec not in self.intent_to_blocks:
                self.intent_to_blocks[sec] = []
            if bid not in self.intent_to_blocks[sec]:
                self.intent_to_blocks[sec].append(bid)

        # ????
        self.turn_to_block[block.created_at_turn] = bid

        # ?????
        for edu in block.atomic_units:
            for word in edu.raw_text.split():
                w = word.strip("???????""''??()").lower()
                if len(w) > 1:
                    if w not in self.keyword_index:
                        self.keyword_index[w] = []
                    if bid not in self.keyword_index[w]:
                        self.keyword_index[w].append(bid)

    def find_by_entity(self, entity: str) -> List[str]:
        return self.entity_to_blocks.get(entity, [])

    def find_by_intent(self, intent: str) -> List[str]:
        return self.intent_to_blocks.get(intent, [])

    def find_by_turn(self, turn: int) -> Optional[str]:
        return self.turn_to_block.get(turn)

    def find_by_keyword(self, keyword: str) -> List[str]:
        return self.keyword_index.get(keyword.lower(), [])

    def find_by_reference(self, ref: str) -> List[str]:
        """??????: ??? + ?? + ??"""
        results = set()
        ref_lower = ref.lower()
        for kw, bids in self.keyword_index.items():
            if ref_lower in kw:
                results.update(bids)
        for ent, bids in self.entity_to_blocks.items():
            if ref_lower in ent.lower():
                results.update(bids)
        for intent, bids in self.intent_to_blocks.items():
            if ref_lower in intent.lower():
                results.update(bids)
        return list(results)

    def remove_block(self, block_id: str):
        """????????"""
        for mapping in [self.entity_to_blocks, self.intent_to_blocks, self.keyword_index]:
            keys_to_remove = []
            for key, bids in mapping.items():
                if block_id in bids:
                    bids.remove(block_id)
                if not bids:
                    keys_to_remove.append(key)
            for k in keys_to_remove:
                del mapping[k]


INDEXER = Indexer()
