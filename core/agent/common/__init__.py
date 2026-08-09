# -*- coding: utf-8 -*-
"""core.agent.common — 跨模块基础设施（文本/序列化/匹配）。"""

from core.agent.common.text_utils import (
    safe_str,
    to_json_safe,
    zh_keyword_match,
    normalize_text,
)

__all__ = ["safe_str", "to_json_safe", "zh_keyword_match", "normalize_text"]
