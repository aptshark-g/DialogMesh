# core/agent/discourse_block_tree/manager.py
"""DiscourseBlockTreeManager — 话语块树管理器。

职责:
1. 接收编译器管道输出的 EDU 列表
2. 调用 Segmenter 切分为 DiscourseBlock
3. 管理块生命周期状态（ACTIVE → COOLING → COLD）
4. 提供上下文查询接口（Hot/Warm/Cold 块筛选）
5. 与 TopicTreeManagerV2 集成（将 Block 作为话题路由输入）

设计原则:
- 最小可寻址单元是 DiscourseBlock（而非轮次）
- 块状态基于轮次距离自动更新
- 支持回退开关（当 discourse_block_tree.enabled=False 时退化为轮级模式）
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

try:
    from core.agent.discourse_block_tree.models import (
        BlockState,
        BoundaryType,
        DiscourseBlock,
        EDU,
        ProgressiveSummary,
    )
    from core.agent.discourse_block_tree.segmenter import Segmenter
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
    BlockState = _models_module.BlockState
    BoundaryType = _models_module.BoundaryType
    DiscourseBlock = _models_module.DiscourseBlock
    EDU = _models_module.EDU
    ProgressiveSummary = _models_module.ProgressiveSummary

    _segmenter_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "discourse_block_tree", "segmenter.py"
    )
    _seg_spec = importlib.util.spec_from_file_location("segmenter", _segmenter_path)
    _seg_module = importlib.util.module_from_spec(_seg_spec)
    sys.modules["segmenter"] = _seg_module
    _seg_spec.loader.exec_module(_seg_module)
    Segmenter = _seg_module.Segmenter

logger = logging.getLogger(__name__)

class DiscourseBlockTreeManager:
    """话语块树管理器。"""

    def __init__(
        self,
        segmenter: Optional[Segmenter] = None,
        hot_turns: int = 5,
        warm_turns: int = 10,
        enabled: bool = True,
    ):
        # 从配置读取默认值
        config = get_discourse_config() if get_discourse_config else None
        mgr_cfg = config.manager if config else None

        self.hot_turns = hot_turns if (mgr_cfg is None) else mgr_cfg.hot_turns
        self.warm_turns = warm_turns if (mgr_cfg is None) else (mgr_cfg.hot_turns + mgr_cfg.cooling_turns)
        self.enabled = enabled if (mgr_cfg is None) else True  # 始终由上层控制
        self.merge_threshold = mgr_cfg.merge_threshold if mgr_cfg else 0.55

        self.segmenter = segmenter or Segmenter()

        # 存储
        self._blocks: List[DiscourseBlock] = []          # 所有块，按时间顺序
        self._block_index: Dict[str, DiscourseBlock] = {}  # ID → Block 索引
        self._current_turn: int = 0                      # 当前轮次索引

        # 活跃块（最近 HOTA 轮内的块）
        self._active_block: Optional[DiscourseBlock] = None

        logger.debug(
            f"DiscourseBlockTreeManager initialized (hot={self.hot_turns}, "
            f"warm={self.warm_turns}, merge_threshold={self.merge_threshold})"
        )

    # ── 公共接口 ──────────────────────────────────────────────────

    def ingest_turn(self, edus: List[EDU]) -> List[DiscourseBlock]:
        """接收新轮次的 EDU 列表，切分并路由。

        Args:
            edus: 编译器管道输出的量化 EDU 列表

        Returns:
            新创建或更新的话语块列表
        """
        if not self.enabled or not edus:
            # 退化为轮级模式：每个轮次作为一个整块
            return self._fallback_ingest(edus)

        # 更新当前轮次
        self._current_turn = max(self._current_turn, max(e.turn_index for e in edus))

        # 1. 调用 Segmenter 切分
        new_blocks = self.segmenter.segment(edus)

        # 2. 更新现有块状态
        self._update_block_states()

        # 3. 路由新块
        routed_blocks = []
        for block in new_blocks:
            routed = self._route_block(block)
            if routed:
                routed_blocks.append(routed)

        return routed_blocks

    def get_blocks(self, state: Optional[BlockState] = None) -> List[DiscourseBlock]:
        """获取话语块列表（可选按状态筛选）。"""
        if state is None:
            return list(self._blocks)
        return [b for b in self._blocks if b.state == state]

    def get_hot_blocks(self) -> List[DiscourseBlock]:
        """获取 Hot 块（ACTIVE 状态）。"""
        return self.get_blocks(BlockState.ACTIVE)

    def get_warm_blocks(self) -> List[DiscourseBlock]:
        """获取 Warm 块（COOLING 状态）。"""
        return self.get_blocks(BlockState.COOLING)

    def get_cold_blocks(self) -> List[DiscourseBlock]:
        """获取 Cold 块（COLD 状态）。"""
        return self.get_blocks(BlockState.COLD)

    def get_block_by_id(self, block_id: str) -> Optional[DiscourseBlock]:
        """通过 ID 获取块。"""
        return self._block_index.get(block_id)

    def get_latest_block(self) -> Optional[DiscourseBlock]:
        """获取最新的话语块。"""
        if not self._blocks:
            return None
        return self._blocks[-1]

    def get_active_block(self) -> Optional[DiscourseBlock]:
        """获取当前活跃块（最新创建的块）。"""
        return self._active_block

    @property
    def current_turn(self) -> int:
        """当前轮次索引。"""
        return self._current_turn

    @property
    def block_count(self) -> int:
        """总块数。"""
        return len(self._blocks)

    def reset(self):
        """重置所有状态（新会话）。"""
        self._blocks.clear()
        self._block_index.clear()
        self._current_turn = 0
        self._active_block = None

    # ── 内部路由 ────────────────────────────────────────────────────

    def _route_block(self, block: DiscourseBlock) -> DiscourseBlock:
        """将新块路由到树中。

        策略:
        1. 如果当前有活跃块，且新块与活跃块高粘合 → 合并到活跃块
        2. 否则 → 作为新块追加
        """
        if not self._active_block:
            # 第一个块
            self._add_block(block)
            self._active_block = block
            return block

        # 计算与活跃块的边界粘合度
        cohesion = self.segmenter.compute_block_boundary_cohesion(
            self._active_block, block
        )

        if cohesion >= self.merge_threshold:  # 高粘合度阈值（从配置读取）
            # 合并到活跃块
            self._merge_into_active(block)
            return self._active_block
        else:
            # 新块
            self._add_block(block)
            self._active_block = block
            return block

    def _add_block(self, block: DiscourseBlock):
        """将块加入存储。"""
        self._blocks.append(block)
        self._block_index[block.id] = block

    def _merge_into_active(self, block: DiscourseBlock):
        """将新块合并到当前活跃块。"""
        if not self._active_block:
            return
        # 合并 EDU
        self._active_block.edus.extend(block.edus)
        self._active_block.end_turn = max(self._active_block.end_turn, block.end_turn)
        # 更新实体签名
        self._active_block._update_entity_signature()
        # 更新 embedding（平均）
        if self._active_block.macro_embedding and block.macro_embedding:
            self._active_block.macro_embedding = self.segmenter._average_vectors(
                [self._active_block.macro_embedding, block.macro_embedding]
            )
        elif block.macro_embedding:
            self._active_block.macro_embedding = block.macro_embedding
        # 更新意图（重新计算主导意图）
        intent_counts = {}
        for e in self._active_block.edus:
            if e.intent_label:
                intent_counts[e.intent_label] = intent_counts.get(e.intent_label, 0) + 1
        if intent_counts:
            self._active_block.intent_label = max(intent_counts, key=intent_counts.get)

    # ── 状态管理 ──────────────────────────────────────────────────────

    def _update_block_states(self):
        """基于当前轮次更新所有块的生命周期状态。"""
        for block in self._blocks:
            turn_distance = self._current_turn - block.end_turn
            if turn_distance <= self.hot_turns:
                block.state = BlockState.ACTIVE
            elif turn_distance <= self.warm_turns:
                block.state = BlockState.COOLING
            else:
                block.state = BlockState.COLD

    # ── 退化模式 ─────────────────────────────────────────────────────

    def _fallback_ingest(self, edus: List[EDU]) -> List[DiscourseBlock]:
        """退化模式：每个轮次作为一个整块（不启用 discourse block tree）。"""
        if not edus:
            return []
        turn_index = edus[0].turn_index
        block_id = f"block:T{turn_index}:fallback"

        block = DiscourseBlock(
            id=block_id,
            edus=list(edus),
            start_turn=turn_index,
            end_turn=turn_index,
            state=BlockState.ACTIVE,
        )
        block._update_entity_signature()

        self._add_block(block)
        self._active_block = block
        self._current_turn = max(self._current_turn, turn_index)
        self._update_block_states()
        return [block]

    # ── 序列化 ───────────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        """序列化状态。"""
        return {
            "current_turn": self._current_turn,
            "block_count": len(self._blocks),
            "blocks": [b.to_dict() for b in self._blocks],
            "active_block_id": self._active_block.id if self._active_block else None,
        }
