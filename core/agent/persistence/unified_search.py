# -*- coding: utf-8 -*-
"""UnifiedSearch: keyword/summary search over UnifiedGraphStore.

G10-P3 (2026-08-04): 补齐 hybrid_hyde / store_safety 引用的缺失模块。
检索实现：SQL LIKE over summary + data（可扩展为 FTS5 / BGE 向量召回）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class UnifiedSearch:
    """Search facade over a UnifiedGraphStore (node_id → summary/data)."""

    def __init__(self, store):
        self._store = store

    def keyword_search(self, query: str, domain: str = None,
                       node_type: str = None, limit: int = 20) -> List[dict]:
        """Full-text-ish keyword search over summary + data (LIKE)."""
        if not query:
            return []
        conditions = ["(summary LIKE ? OR data LIKE ?)"]
        params = [f"%{query}%", f"%{query}%"]
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if node_type:
            conditions.append("node_type = ?")
            params.append(node_type)
        params.append(limit)
        sql = ("SELECT * FROM unified_nodes WHERE " + " AND ".join(conditions) +
               " ORDER BY importance DESC, updated_at DESC LIMIT ?")
        try:
            with self._store._lock:
                rows = self._store._conn.execute(sql, params).fetchall()
            return [self._store._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.debug("UnifiedSearch keyword_search failed: %s", e)
            return []

    def summary_search(self, query: str, domain: str = None,
                       node_type: str = None, limit: int = 20) -> List[dict]:
        """Search over summary field only (semantic-value anchored)."""
        if not query:
            return []
        conditions = ["summary LIKE ?"]
        params = [f"%{query}%"]
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if node_type:
            conditions.append("node_type = ?")
            params.append(node_type)
        params.append(limit)
        sql = ("SELECT * FROM unified_nodes WHERE " + " AND ".join(conditions) +
               " ORDER BY importance DESC, updated_at DESC LIMIT ?")
        try:
            with self._store._lock:
                rows = self._store._conn.execute(sql, params).fetchall()
            return [self._store._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.debug("UnifiedSearch summary_search failed: %s", e)
            return []

    def stats(self) -> Dict[str, Any]:
        try:
            return {"searchable_nodes": len(self.keyword_search("", limit=1)) or 0}
        except Exception:
            return {"searchable_nodes": 0}
