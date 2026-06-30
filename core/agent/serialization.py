"""Discourse Block Tree 序列化/反序列化模块。

提供 DiscourseBlock、EDU、ProgressiveSummary 等核心数据结构的
JSON 可序列化支持，以及 DiscourseBlockTreeManager 的完整会话持久化。

设计约束:
- 纯 JSON 格式，human-readable
- 完整保留 embedding 向量、维度评分、实体签名等所有字段
- 支持向前兼容（缺失字段使用默认值）
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent.discourse_block_tree.models import (
    BlockState,
    BoundaryType,
    DiscourseBlock,
    EDU,
    EDUType,
    Entity,
    MacroDimensions,
    MicroDimensions,
    ProgressiveSummary,
)
from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager
from core.agent.discourse_block_tree.segmenter import Segmenter

logger = logging.getLogger(__name__)


# ── 辅助函数 ──────────────────────────────────────────────────────

def _block_state_to_str(state: BlockState) -> str:
    return state.value


def _block_state_from_str(s: str) -> BlockState:
    return BlockState(s)


def _boundary_type_to_str(bt: Optional[BoundaryType]) -> Optional[str]:
    return bt.value if bt else None


def _boundary_type_from_str(s: Optional[str]) -> Optional[BoundaryType]:
    return BoundaryType(s) if s else None


def _edu_type_to_str(et: Optional[EDUType]) -> Optional[str]:
    return et.value if et else None


def _edu_type_from_str(s: Optional[str]) -> Optional[EDUType]:
    return EDUType(s) if s else None


# ── 维度序列化 ───────────────────────────────────────────────────

def serialize_micro_dimensions(m: MicroDimensions) -> Dict[str, float]:
    return {
        "μ1": m.μ1,
        "μ2": m.μ2,
        "μ3": m.μ3,
        "μ4": m.μ4,
        "μ5": m.μ5,
    }


def deserialize_micro_dimensions(data: Dict[str, float]) -> MicroDimensions:
    return MicroDimensions(
        μ1=data.get("μ1", 0.0),
        μ2=data.get("μ2", 0.0),
        μ3=data.get("μ3", 0.0),
        μ4=data.get("μ4", 0.0),
        μ5=data.get("μ5", 0.0),
    )


def serialize_macro_dimensions(m: MacroDimensions) -> Dict[str, float]:
    return {
        "M1": m.M1,
        "M2": m.M2,
        "M3": m.M3,
        "M4": m.M4,
    }


def deserialize_macro_dimensions(data: Dict[str, float]) -> MacroDimensions:
    return MacroDimensions(
        M1=data.get("M1", 0.0),
        M2=data.get("M2", 0.0),
        M3=data.get("M3", 0.0),
        M4=data.get("M4", 0.0),
    )


# ── 渐进式摘要序列化 ──────────────────────────────────────────────

def serialize_progressive_summary(ps: ProgressiveSummary) -> Dict[str, Any]:
    return {
        "v1": ps.v1,
        "v2": ps.v2,
        "v3": ps.v3,
        "v1_timestamp": ps.v1_timestamp,
        "v2_timestamp": ps.v2_timestamp,
        "v3_timestamp": ps.v3_timestamp,
        "v3_trigger_reason": ps.v3_trigger_reason,
    }


def deserialize_progressive_summary(data: Optional[Dict[str, Any]]) -> Optional[ProgressiveSummary]:
    if data is None:
        return None
    ps = ProgressiveSummary(
        v1=data.get("v1"),
        v2=data.get("v2"),
        v3=data.get("v3"),
        v1_timestamp=data.get("v1_timestamp"),
        v2_timestamp=data.get("v2_timestamp"),
        v3_timestamp=data.get("v3_timestamp"),
        v3_trigger_reason=data.get("v3_trigger_reason"),
    )
    return ps


# ── 实体序列化 ───────────────────────────────────────────────────

def serialize_entity(e: Entity) -> Dict[str, Any]:
    return {
        "name": e.name,
        "type": e.type,
        "first_appearance": e.first_appearance,
        "last_appearance": e.last_appearance,
        "mention_count": e.mention_count,
        "attributes": e.attributes,
        "resolved_by": e.resolved_by,
        "confidence": e.confidence,
    }


def deserialize_entity(data: Dict[str, Any]) -> Entity:
    return Entity(
        name=data["name"],
        type=data.get("type", "unknown"),
        first_appearance=data.get("first_appearance", 0),
        last_appearance=data.get("last_appearance", 0),
        mention_count=data.get("mention_count", 1),
        attributes=data.get("attributes", []),
        resolved_by=data.get("resolved_by"),
        confidence=data.get("confidence", 1.0),
    )


# ── EDU 序列化 ────────────────────────────────────────────────────

def serialize_edu(edu: EDU) -> Dict[str, Any]:
    return {
        "id": edu.id,
        "turn_index": edu.turn_index,
        "edu_index": edu.edu_index,
        "raw_text": edu.raw_text,
        "subject": edu.subject,
        "predicate": edu.predicate,
        "object": edu.object,
        "subject_attrs": edu.subject_attrs,
        "object_attrs": edu.object_attrs,
        "negation": edu.negation,
        "uncertainty": edu.uncertainty,
        "imperative": edu.imperative,
        "question": edu.question,
        "raw_entities": edu.raw_entities,
        "parse_failed": edu.parse_failed,
        "parse_failed_reason": edu.parse_failed_reason,
        "embedding": edu.embedding,
        "intent_label": edu.intent_label,
        "micro_dimensions": serialize_micro_dimensions(edu.micro_dimensions) if edu.micro_dimensions else None,
        "macro_dimensions": serialize_macro_dimensions(edu.macro_dimensions) if edu.macro_dimensions else None,
        "timestamp": edu.timestamp,
        "boundary_type": _boundary_type_to_str(edu.boundary_type),
    }


def deserialize_edu(data: Dict[str, Any]) -> EDU:
    edu = EDU(
        id=data["id"],
        turn_index=data["turn_index"],
        edu_index=data["edu_index"],
        raw_text=data["raw_text"],
        subject=data.get("subject"),
        predicate=data.get("predicate"),
        object=data.get("object"),
        subject_attrs=data.get("subject_attrs", []),
        object_attrs=data.get("object_attrs", []),
        negation=data.get("negation", False),
        uncertainty=data.get("uncertainty", False),
        imperative=data.get("imperative", False),
        question=data.get("question", False),
        raw_entities=data.get("raw_entities", []),
        parse_failed=data.get("parse_failed", False),
        parse_failed_reason=data.get("parse_failed_reason", ""),
        embedding=data.get("embedding"),
        intent_label=data.get("intent_label"),
        micro_dimensions=deserialize_micro_dimensions(data["micro_dimensions"]) if data.get("micro_dimensions") else None,
        macro_dimensions=deserialize_macro_dimensions(data["macro_dimensions"]) if data.get("macro_dimensions") else None,
        timestamp=data.get("timestamp"),
        boundary_type=_boundary_type_from_str(data.get("boundary_type")),
    )
    return edu


# ── 话语块序列化 ─────────────────────────────────────────────────

def serialize_discourse_block(block: DiscourseBlock) -> Dict[str, Any]:
    return {
        "id": block.id,
        "edus": [serialize_edu(e) for e in block.edus],
        "start_turn": block.start_turn,
        "end_turn": block.end_turn,
        "state": _block_state_to_str(block.state),
        "summary": serialize_progressive_summary(block.summary) if block.summary else None,
        "entities": [serialize_entity(e) for e in block.entities],
        "entity_signature": block.entity_signature,
        "macro_embedding": block.macro_embedding,
        "intent_label": block.intent_label,
        "cohesion_boundary": block.cohesion_boundary,
        "parent_id": block.parent_id,
        "node_id": block.node_id,
    }


def deserialize_discourse_block(data: Dict[str, Any]) -> DiscourseBlock:
    block = DiscourseBlock(
        id=data["id"],
        edus=[deserialize_edu(e) for e in data.get("edus", [])],
        start_turn=data.get("start_turn", 0),
        end_turn=data.get("end_turn", 0),
        state=_block_state_from_str(data.get("state", "active")),
        summary=deserialize_progressive_summary(data.get("summary")),
        entities=[deserialize_entity(e) for e in data.get("entities", [])],
        entity_signature=data.get("entity_signature", ""),
        macro_embedding=data.get("macro_embedding"),
        intent_label=data.get("intent_label"),
        cohesion_boundary=data.get("cohesion_boundary"),
        parent_id=data.get("parent_id"),
        node_id=data.get("node_id"),
    )
    return block


# ── 批量序列化 ───────────────────────────────────────────────────

def serialize_blocks(blocks: List[DiscourseBlock]) -> Dict[str, Any]:
    """将 DiscourseBlock 列表序列化为 JSON 可序列化字典。

    Returns:
        dict: 包含 "version"、"block_count"、"blocks" 的字典
    """
    return {
        "version": 1,
        "block_count": len(blocks),
        "blocks": [serialize_discourse_block(b) for b in blocks],
    }


def deserialize_blocks(data: Dict[str, Any]) -> List[DiscourseBlock]:
    """从字典恢复 DiscourseBlock 列表。

    Args:
        data: serialize_blocks 输出的字典

    Returns:
        List[DiscourseBlock]: 恢复后的话语块列表
    """
    version = data.get("version", 1)
    blocks_data = data.get("blocks", [])
    blocks = [deserialize_discourse_block(b) for b in blocks_data]
    return blocks


# ── 会话持久化 ───────────────────────────────────────────────────

def serialize_manager(manager: DiscourseBlockTreeManager) -> Dict[str, Any]:
    """完整序列化 DiscourseBlockTreeManager 状态。"""
    blocks = manager.get_blocks()
    active_block_id = None
    if manager._active_block:
        active_block_id = manager._active_block.id

    return {
        "version": 1,
        "current_turn": manager._current_turn,
        "block_count": len(blocks),
        "blocks": [serialize_discourse_block(b) for b in blocks],
        "active_block_id": active_block_id,
        "hot_turns": manager.hot_turns,
        "warm_turns": manager.warm_turns,
        "merge_threshold": manager.merge_threshold,
        "enabled": manager.enabled,
    }


def deserialize_manager(data: Dict[str, Any]) -> DiscourseBlockTreeManager:
    """从字典恢复 DiscourseBlockTreeManager 状态。

    注意：不恢复 Segmenter 实例（由 Manager 自行创建新实例），
    仅恢复块列表、状态、轮次索引等核心数据。
    """
    manager = DiscourseBlockTreeManager(
        segmenter=Segmenter(),
        hot_turns=data.get("hot_turns", 5),
        enabled=data.get("enabled", True),
    )
    manager.warm_turns = data.get("warm_turns", 10)
    manager.merge_threshold = data.get("merge_threshold", 0.55)
    manager._current_turn = data.get("current_turn", 0)

    blocks = deserialize_blocks({
        "version": data.get("version", 1),
        "blocks": data.get("blocks", []),
    })

    for block in blocks:
        manager._blocks.append(block)
        manager._block_index[block.id] = block

    # 恢复 active_block
    active_block_id = data.get("active_block_id")
    if active_block_id and active_block_id in manager._block_index:
        manager._active_block = manager._block_index[active_block_id]

    # 恢复状态
    manager._update_block_states()

    return manager


def save_session(manager: DiscourseBlockTreeManager, path: str) -> None:
    """将 DiscourseBlockTreeManager 保存到 JSON 文件。

    Args:
        manager: 话语块树管理器
        path: JSON 文件路径
    """
    data = serialize_manager(manager)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Session saved to {path} ({data['block_count']} blocks)")


def load_session(path: str) -> DiscourseBlockTreeManager:
    """从 JSON 文件加载 DiscourseBlockTreeManager。

    Args:
        path: JSON 文件路径

    Returns:
        DiscourseBlockTreeManager: 恢复后的管理器实例
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    manager = deserialize_manager(data)
    logger.info(f"Session loaded from {path} ({manager.block_count} blocks)")
    return manager
