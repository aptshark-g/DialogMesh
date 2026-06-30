# core/agent/discourse_block_tree/indexer.py
"""Indexer — 实体/意图/轮次索引器。

为话语块建立多维度索引，支持快速查询：
- 实体索引: entity_name → List[block_id]
- 意图索引: intent_label → List[block_id]
- 轮次索引: turn_index → List[block_id]
- 时间索引: timestamp → List[block_id]

支持增量更新（新块加入时自动索引）。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set

try:
    from core.agent.discourse_block_tree.models import (
        DiscourseBlock,
        EDU,
    )
except ImportError:
    import importlib.util
    import os
    import sys
    _models_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "discourse_block_tree", "models.py"
    )
    _spec = importlib.util.spec_from_file_location("discourse_models", _models_path)
    _models_module = importlib.util.module_from_spec(_spec)
    sys.modules["discourse_models"] = _models_module
    _spec.loader.exec_module(_models_module)
    DiscourseBlock = _models_module.DiscourseBlock
    EDU = _models_module.EDU


class Indexer:
    """话语块索引器。"""

    def __init__(self):
        # 实体索引: entity_name → set of block_ids
        self._entity_index: Dict[str, Set[str]] = defaultdict(set)
        # 意图索引: intent_label → set of block_ids
        self._intent_index: Dict[str, Set[str]] = defaultdict(set)
        # 轮次索引: turn_index → set of block_ids
        self._turn_index: Dict[int, Set[str]] = defaultdict(set)
        # 时间索引: timestamp_bucket → set of block_ids (按 60s 分桶)
        self._time_index: Dict[int, Set[str]] = defaultdict(set)

        # 反向索引: block_id → indexed entities/intents
        self._block_entities: Dict[str, Set[str]] = defaultdict(set)
        self._block_intents: Dict[str, Set[str]] = defaultdict(set)

    # ── 公共接口 ──────────────────────────────────────────────────

    def index_block(self, block: DiscourseBlock):
        """为单个块建立索引。"""
        block_id = block.id

        # 实体索引
        for edu in block.edus:
            for entity in edu.raw_entities:
                self._entity_index[entity].add(block_id)
                self._block_entities[block_id].add(entity)

        # 意图索引
        if block.intent_label:
            self._intent_index[block.intent_label].add(block_id)
            self._block_intents[block_id].add(block.intent_label)
        for edu in block.edus:
            if edu.intent_label:
                self._intent_index[edu.intent_label].add(block_id)
                self._block_intents[block_id].add(edu.intent_label)

        # 轮次索引
        for turn in range(block.start_turn, block.end_turn + 1):
            self._turn_index[turn].add(block_id)

        # 时间索引（按 EDU 时间戳）
        for edu in block.edus:
            if edu.timestamp:
                bucket = int(edu.timestamp) // 60  # 60 秒分桶
                self._time_index[bucket].add(block_id)

    def remove_block(self, block_id: str):
        """从索引中移除块。"""
        # 实体索引
        for entity in list(self._block_entities.get(block_id, set())):
            self._entity_index[entity].discard(block_id)
            if not self._entity_index[entity]:
                del self._entity_index[entity]
        self._block_entities.pop(block_id, None)

        # 意图索引
        for intent in list(self._block_intents.get(block_id, set())):
            self._intent_index[intent].discard(block_id)
            if not self._intent_index[intent]:
                del self._intent_index[intent]
        self._block_intents.pop(block_id, None)

        # 轮次索引和时间索引
        for turn, block_ids in list(self._turn_index.items()):
            block_ids.discard(block_id)
            if not block_ids:
                del self._turn_index[turn]

        for bucket, block_ids in list(self._time_index.items()):
            block_ids.discard(block_id)
            if not block_ids:
                del self._time_index[bucket]

    def query_by_entity(self, entity_name: str) -> List[str]:
        """通过实体名查询块 ID 列表。"""
        return sorted(self._entity_index.get(entity_name, set()))

    def query_by_intent(self, intent_label: str) -> List[str]:
        """通过意图标签查询块 ID 列表。"""
        return sorted(self._intent_index.get(intent_label, set()))

    def query_by_turn(self, turn_index: int) -> List[str]:
        """通过轮次索引查询块 ID 列表。"""
        return sorted(self._turn_index.get(turn_index, set()))

    def query_by_time_range(self, start_ts: float, end_ts: float) -> List[str]:
        """通过时间范围查询块 ID 列表。"""
        start_bucket = int(start_ts) // 60
        end_bucket = int(end_ts) // 60
        result = set()
        for bucket in range(start_bucket, end_bucket + 1):
            result.update(self._time_index.get(bucket, set()))
        return sorted(result)

    def get_entities(self) -> List[str]:
        """获取所有已索引的实体名称。"""
        return sorted(self._entity_index.keys())

    def get_intents(self) -> List[str]:
        """获取所有已索引的意图标签。"""
        return sorted(self._intent_index.keys())

    def get_entity_frequency(self) -> Dict[str, int]:
        """获取实体频率统计。"""
        return {k: len(v) for k, v in self._entity_index.items()}

    def get_intent_frequency(self) -> Dict[str, int]:
        """获取意图频率统计。"""
        return {k: len(v) for k, v in self._intent_index.items()}

    def clear(self):
        """清空所有索引。"""
        self._entity_index.clear()
        self._intent_index.clear()
        self._turn_index.clear()
        self._time_index.clear()
        self._block_entities.clear()
        self._block_intents.clear()

    # ── 批量索引 ────────────────────────────────────────────────────

    def index_blocks(self, blocks: List[DiscourseBlock]):
        """批量索引多个块。"""
        for block in blocks:
            self.index_block(block)
