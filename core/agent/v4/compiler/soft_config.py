"""SoftConfig — load extensible configuration from JSON files.

Design: hardcoded strings → soft-coded JSON → LLM-extensible knowledge base.

Files:
  data/soft_config/perspective_strategies.json — BGE strategy descriptions + keywords
  data/soft_config/importance_signals.json — correction/metacognition/switch patterns

Supports:
  - Load from file (auto-fallback to code defaults)
  - Extend at runtime (LLM can add new entries)
  - Persist extensions back to file
"""
from __future__ import annotations
import json, os, logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "soft_config"
_DEFAULTS_DIR = _CONFIG_DIR  # same dir for now


class SoftConfig:
    """Single soft-config file loader with runtime extension support."""

    def __init__(self, filename: str, defaults: Any):
        self._path = _CONFIG_DIR / filename
        self._defaults = defaults
        self._data = None

    def load(self) -> Any:
        if self._data is not None:
            return self._data
        try:
            if self._path.exists():
                with open(self._path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                logger.debug("SoftConfig loaded: %s (%d keys)", self._path.name,
                            len(self._data) if isinstance(self._data, dict) else 'list')
                return self._data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("SoftConfig %s failed: %s, using defaults", self._path.name, e)
        self._data = self._defaults
        return self._data

    def extend(self, key: str, value: Any, append: bool = False):
        """Add or append entry at runtime.

        Args:
            key: Config key to modify
            value: New value (replaces by default, appends if append=True)
            append: If True and key is a list, append value to list
        """
        data = self.load()
        if isinstance(data, dict):
            if append and isinstance(data.get(key), list):
                data[key].append(value)
            else:
                data[key] = value

    def persist(self):
        """Save runtime extensions back to file."""
        if self._data is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            logger.info("SoftConfig persisted: %s", self._path.name)
        except OSError as e:
            logger.warning("SoftConfig persist failed: %s", e)

    def reload(self):
        """Force reload from file (after external edits)."""
        self._data = None
        return self.load()


# ── Module-level configs ──

def load_perspective_config() -> dict:
    """Load perspective strategy descriptions for BGE semantic matching."""
    return SoftConfig("perspective_strategies.json", {
        "architecture": {"description": "系统架构设计、整体结构、模块关系", "keywords": ["架构","设计"]},
        "evolution":   {"description": "历史演变、设计决策的原因", "keywords": ["为什么","原因"]},
        "engineering": {"description": "代码实现、函数定义、技术细节", "keywords": ["代码","实现"]},
        "execution":   {"description": "运行流程、执行步骤、调度逻辑", "keywords": ["流程","运行"]},
    }).load()


def load_importance_config() -> dict:
    """Load importance signal patterns."""
    return SoftConfig("importance_signals.json", {
        "correction_signals": [{"pattern": "不是", "importance": 0.9}],
        "metacognition_signals": [{"pattern": "元认知", "importance": 0.85}],
        "switch_signals": [{"pattern": "switch", "importance": 0.6}],
    }).load()
