# core/agent/discourse_block_tree/context_builder.py
"""ContextBuilder — 上下文构建器。

组装 LLM 上下文：
- Hot 块（ACTIVE, 最近 5 轮）: 完整文本 + v1 摘要
- Warm 块（COOLING, 5-20 轮）: v2 摘要
- Cold 块（COLD, > 20 轮）: v3 摘要（如有）或省略

输出: 上下文字符串（按时间顺序排列）
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

try:
    from core.agent.discourse_block_tree.models import (
        BlockState,
        DiscourseBlock,
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
    BlockState = _models_module.BlockState
    DiscourseBlock = _models_module.DiscourseBlock

logger = logging.getLogger(__name__)

class ContextBuilder:
    """上下文构建器。"""

    def __init__(self, hot_turns: int = 5, warm_turns: int = 20):
        # 从配置读取默认值
        config = get_discourse_config() if get_discourse_config else None
        ctx_cfg = config.context if config else None

        self.hot_turns = hot_turns if (ctx_cfg is None) else ctx_cfg.hot_turns
        self.warm_turns = warm_turns  # 温层阈值：20 轮（热/温/冷 = 5/20/∞）

        logger.debug(f"ContextBuilder initialized (hot_turns={self.hot_turns}, warm_turns={self.warm_turns})")

    # ── 公共接口 ──────────────────────────────────────────────────

    def build_context(
        self,
        blocks: List[DiscourseBlock],
        current_turn: int,
        max_tokens: Optional[int] = None,
    ) -> str:
        """构建上下文字符串。

        Args:
            blocks: 所有话语块列表
            current_turn: 当前轮次索引
            max_tokens: 最大 token 数（MVP 中暂不精确控制，按块数截断）

        Returns:
            按时间顺序排列的上下文字符串
        """
        parts = []

        for block in blocks:
            turn_distance = current_turn - block.end_turn
            part = self._format_block(block, turn_distance)
            if part:
                parts.append(part)

        # 按时间顺序排序（start_turn 升序）
        # 但 blocks 本身已是按时间顺序
        return "\n".join(parts)

    def build_structured_context(
        self,
        blocks: List[DiscourseBlock],
        current_turn: int,
    ) -> List[Dict]:
        """构建结构化上下文（用于调试或特殊场景）。

        返回列表，每个元素包含：
        - state: hot/warm/cold
        - summary: 对应摘要
        - full_text: 完整文本（仅 hot）
        """
        result = []
        for block in blocks:
            turn_distance = current_turn - block.end_turn
            item = self._format_block_structured(block, turn_distance)
            if item:
                result.append(item)
        return result

    # ── 格式化方法 ───────────────────────────────────────────────────

    def _format_block(self, block: DiscourseBlock, turn_distance: int) -> str:
        """根据块状态格式化单个块。"""
        if turn_distance <= self.hot_turns:
            # Hot: 完整文本 + v1 摘要
            text = block.text
            v1 = block.summary.v1 if block.summary else None
            if v1:
                return f"[Hot] {block.id}\n{text}\n[v1] {v1}"
            return f"[Hot] {block.id}\n{text}"

        elif turn_distance <= self.warm_turns:
            # Warm: v2 摘要
            v2 = block.summary.v2 if block.summary else None
            if v2:
                return f"[Warm] {block.id} {v2}"
            # 无 v2，回退到 v1
            v1 = block.summary.v1 if block.summary else None
            if v1:
                return f"[Warm] {block.id} {v1}"
            return f"[Warm] {block.id} (no summary)"

        else:
            # Cold: v3 摘要（如有）或省略
            v3 = block.summary.v3 if block.summary else None
            if v3:
                return f"[Cold] {block.id} {v3}"
            v2 = block.summary.v2 if block.summary else None
            if v2:
                return f"[Cold] {block.id} {v2}"
            return f"[Cold] {block.id} (archived)"

    def _format_block_structured(self, block: DiscourseBlock, turn_distance: int) -> Optional[Dict]:
        """结构化格式化。"""
        if turn_distance <= self.hot_turns:
            return {
                "state": "hot",
                "block_id": block.id,
                "full_text": block.text,
                "v1": block.summary.v1 if block.summary else None,
                "v2": block.summary.v2 if block.summary else None,
            }
        elif turn_distance <= self.warm_turns:
            return {
                "state": "warm",
                "block_id": block.id,
                "v2": block.summary.v2 if block.summary else None,
                "v3": block.summary.v3 if block.summary else None,
            }
        else:
            return {
                "state": "cold",
                "block_id": block.id,
                "v3": block.summary.v3 if block.summary else None,
            }
