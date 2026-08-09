"""GAP-4 压缩反馈闭环（Hermes manual_compression_feedback 对齐）.

用户/系统对压缩结果反馈质量（good/bad + comment）:
  - 反馈持久化（data/compression_feedback.json, 原子写, 线程安全）
  - 统计（good/bad/good_rate）供评测
  - 消费方: 元认知复盘（decision_bus 事件）/ 未来压缩阈值调优
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

FEEDBACK_FILE = os.path.join("data", "compression_feedback.json")


class CompressionFeedbackStore:
    """压缩质量反馈存储（记录 + 统计）。"""

    def __init__(self, path: str = FEEDBACK_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._items: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def _persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._items[-200:], f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            pass

    def record(self, quality: str, comment: str = "", compression_id: str = "",
               source: str = "user") -> Optional[Dict[str, Any]]:
        """记录一条压缩反馈. quality ∈ {good, bad}. 返回条目或 None（非法质量）。"""
        if quality not in ("good", "bad"):
            return None
        item = {
            "id": f"cf_{int(time.time() * 1000)}",
            "quality": quality,
            "comment": comment[:500],
            "compression_id": compression_id,
            "source": source,
            "ts": time.time(),
        }
        with self._lock:
            self._items.append(item)
            self._persist()
        return item

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._items)
            good = sum(1 for i in self._items if i.get("quality") == "good")
            bad = total - good
        return {
            "total": total,
            "good": good,
            "bad": bad,
            "good_rate": round(good / total, 3) if total else 0.0,
        }

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._items[-limit:])
