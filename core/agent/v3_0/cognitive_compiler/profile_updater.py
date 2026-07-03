# -*- coding: utf-8 -*-

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from core.agent.v3_0.cognitive_tree.models import CognitiveTreeNode, CogNodeStatus

logger = logging.getLogger(__name__)


class ProfileUpdater:
    """
    ProfileUpdater v3.0 -- 用户画像深度更新器。

    基于工程文档 ENGINEERING_MULTILAYER_LLM.md section 7.3 实现。
    使用 EMA (Exponential Moving Average) 加权融合当前画像与会话画像。

    Profile_new = alpha * Profile_current + (1-alpha) * Profile_session

    双轨道架构：
      Track A (趋势跟踪): 认知动力学特征（元认知、发散性、稳定性）的 EMA 更新
      Track B (修正标记): 标签冲突检测与标记，标记画像中不一致的部分
    """

    DEFAULT_ALPHA = 0.7

    def __init__(self, alpha: float = DEFAULT_ALPHA):
        self._alpha = alpha
        self._profile_store: Dict[str, Dict[str, Any]] = {}

    def update(self, session_id: str, cog_tree_nodes: List[CognitiveTreeNode]) -> Dict[str, Any]:
        """
        使用 Cognitive Tree 节点更新用户画像。

        Args:
            session_id: 会话 ID
            cog_tree_nodes: 当前会话的 Cognitive Tree 节点列表

        Returns:
            Dict: 更新后的完整画像
        """
        current_profile = self._load_profile(session_id)
        session_profile = self._extract_session_profile(cog_tree_nodes)
        merged_profile = self._merge_profiles(current_profile, session_profile, self._alpha)
        merged_profile["_conflicts"] = self._detect_conflicts(merged_profile)
        merged_profile["_updated_at"] = time.time()
        self._save_profile(session_id, merged_profile)
        logger.debug("ProfileUpdater: session=%s merged", session_id)
        return merged_profile

    def get_profile(self, session_id: str) -> Dict[str, Any]:
        """获取当前会话的用户画像。"""
        return self._profile_store.get(session_id, self._default_profile())

    def _extract_session_profile(self, nodes: List[CognitiveTreeNode]) -> Dict[str, Any]:
        """从 Cognitive Tree 节点提取当前会话的画像特征。"""
        if not nodes:
            return self._default_profile()

        pcr_snapshots = [
            n.metadata.get("cognitive_snapshot", {})
            for n in nodes if n.source_llm == "PCR-LLM"
        ]

        if pcr_snapshots:
            n = len(pcr_snapshots)
            avg_meta = sum(s.get("metacognition", 0.5) for s in pcr_snapshots) / n
            avg_div = sum(s.get("divergence", 0.5) for s in pcr_snapshots) / n
            avg_stab = sum(s.get("stability", 0.5) for s in pcr_snapshots) / n
        else:
            avg_meta = avg_div = avg_stab = 0.5

        total_nodes = len(nodes)
        invalidated = sum(1 for n in nodes if n.status == CogNodeStatus.INVALIDATED)
        error_rate = invalidated / max(1, total_nodes)

        return {
            "cognitive_dynamics": {
                "metacognition": round(avg_meta, 3),
                "divergence": round(avg_div, 3),
                "stability": round(avg_stab, 3),
            },
            "error_rate": round(error_rate, 3),
            "total_cog_nodes": total_nodes,
        }

    def _merge_profiles(self, current: Dict[str, Any], session: Dict[str, Any], alpha: float) -> Dict[str, Any]:
        """F-02: EMA 加权融合当前画像和会话画像。"""
        merged = {}
        all_keys = set(current.keys()) | set(session.keys())
        for key in all_keys:
            if key.startswith("_"):
                continue
            v_cur = current.get(key, 0.5)
            v_ses = session.get(key, 0.5)
            if isinstance(v_cur, dict) and isinstance(v_ses, dict):
                merged[key] = self._merge_profiles(v_cur, v_ses, alpha)
            elif isinstance(v_cur, (int, float)) and isinstance(v_ses, (int, float)):
                merged[key] = round(alpha * v_cur + (1 - alpha) * v_ses, 3)
            else:
                merged[key] = v_cur
        merged["_merge_count"] = current.get("_merge_count", 0) + 1
        return merged

    def _detect_conflicts(self, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Track B: 检测画像标签冲突。"""
        conflicts = []
        cd = profile.get("cognitive_dynamics", {})
        meta = cd.get("metacognition", 0.5)
        stab = cd.get("stability", 0.5)
        if meta > 0.7 and stab < 0.3:
            conflicts.append({
                "type": "meta_stability_mismatch",
                "message": "高元认知但低稳定性，可能用户处于探索状态",
                "severity": "medium",
            })
        err = profile.get("error_rate", 0)
        if err > 0.3 and meta > 0.6:
            conflicts.append({
                "type": "high_error_with_meta",
                "message": "错误率高但元认知不低，可能系统理解有系统性问题",
                "severity": "high",
            })
        return conflicts

    def _default_profile(self) -> Dict[str, Any]:
        return {"cognitive_dynamics": {"metacognition": 0.5, "divergence": 0.5, "stability": 0.5}, "error_rate": 0, "total_cog_nodes": 0}

    def _load_profile(self, session_id: str) -> Dict[str, Any]:
        return self._profile_store.get(session_id, self._default_profile()).copy()

    def _save_profile(self, session_id: str, profile: Dict[str, Any]) -> None:
        self._profile_store[session_id] = profile


__all__ = ["ProfileUpdater"]
