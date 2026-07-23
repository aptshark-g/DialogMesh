"""L2 Configuration loader — reads config/l2_config.json once, cached."""

import json
from pathlib import Path
from typing import Any

_config: dict = None


def load() -> dict:
    global _config
    if _config is None:
        cfg_path = Path(__file__).parent.parent.parent.parent / "config" / "l2_config.json"
        _config = json.loads(open(cfg_path, encoding='utf-8').read())
    return _config


def get(path: str, default: Any = None) -> Any:
    """Dot-path access: get('confidence.syntax_overlap_weight')"""
    cfg = load()
    keys = path.split('.')
    for k in keys:
        if isinstance(cfg, dict):
            cfg = cfg.get(k)
        else:
            return default
    return cfg if cfg is not None else default
