# -*- coding: utf-8 -*-
"""DomainAdapter: 各域模型到 UnifiedGraphStore 的通用适配基类。

G10-P3 (2026-08-04): 补齐 multi_domain_adapters 引用的缺失模块。
域 (domain) 标记: B=行为链 / P=画像 / K=因果基板 / C=主题树。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DomainAdapter:
    """Base adapter mapping domain models to UnifiedGraphStore nodes."""

    def __init__(self, store, domain: str, session_id: str = ""):
        self._store = store
        self._domain = domain
        self._session_id = session_id

    def _save(self, node_id: str, node_type: str, data: dict,
              summary: str = "", importance: float = 0.5) -> bool:
        """Persist a domain node (idempotent upsert)."""
        try:
            return self._store.save_node(
                node_id, node_type, self._domain, data,
                session_id=self._session_id or None,
                summary=summary, importance=importance,
            )
        except Exception:
            logger.exception("DomainAdapter._save failed: %s", node_id)
            return False

    def _load(self, node_id: str) -> Optional[dict]:
        return self._store.load_node(node_id)

    def _load_all(self, node_type: str = None, limit: int = 1000) -> List[dict]:
        """Load domain nodes (optionally filtered by node_type)."""
        nodes = self._store.query_nodes(
            domain=self._domain, node_type=node_type, limit=limit)
        return nodes

    def count(self) -> int:
        counts = self._store.get_tier_counts()
        return sum(counts.values())
