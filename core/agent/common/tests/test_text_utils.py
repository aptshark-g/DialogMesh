# -*- coding: utf-8 -*-
"""text_utils 基础设施测试（ERROR_META_REFLECTION E1）.

覆盖:
  - safe_str: None / dataclass / 自定义对象 / 长文本截断
  - to_json_safe: dataclass / 嵌套 / 不可序列化对象
  - zh_keyword_match: 中文↔英文工具匹配（"查论文" → arxiv_search）
  - normalize_text: BOM / 控制字符
"""
from __future__ import annotations

from dataclasses import dataclass

from core.agent.common.text_utils import (
    safe_str, to_json_safe, zh_keyword_match, normalize_text,
)


class _FakeObject:
    def __str__(self):
        return "<fake plan>"


@dataclass
class _FakeDC:
    name: str = "x"
    value: int = 1


class TestSafeStr:
    def test_none(self):
        assert safe_str(None) == ""

    def test_dict(self):
        assert safe_str({"a": 1, "b": "中"}) == '{"a": 1, "b": "中"}'

    def test_object_repr(self):
        assert safe_str(_FakeObject()) == "<fake plan>"

    def test_truncate(self):
        s = safe_str("x" * 1000, limit=100)
        assert len(s) <= 100 + 3  # +"..."

    def test_unprintable(self):
        class _Bad:
            def __str__(self):
                raise RuntimeError("boom")
            def __repr__(self):
                raise RuntimeError("boom2")
        assert safe_str(_Bad()) == "<unprintable>"


class TestToJsonSafe:
    def test_dataclass(self):
        d = to_json_safe(_FakeDC())
        assert d == {"name": "x", "value": 1}

    def test_nested_mixed(self):
        d = to_json_safe({"a": [_FakeDC(), 1, None], "b": _FakeObject()})
        assert d["a"][0] == {"name": "x", "value": 1}
        assert d["a"][1] == 1
        assert d["a"][2] is None
        assert d["b"] == "<fake plan>"

    def test_primitive_passthrough(self):
        assert to_json_safe(42) == 42
        assert to_json_safe("s") == "s"
        assert to_json_safe(True) is True

    def test_dict_str_keys(self):
        d = to_json_safe({1: "one", None: "none"})
        assert d == {"1": "one", "None": "none"}


class TestZhKeywordMatch:
    def test_zh_keyword_hits(self):
        # "查论文" ↔ arxiv_search.keywords_zh=["论文", "文献", "学术"]
        assert zh_keyword_match("查一下最近的论文", ["论文", "文献"],
                                en_text="Search arxiv for academic papers",
                                name="arxiv_search")

    def test_english_name_hits(self):
        assert zh_keyword_match("arxiv", [], en_text="", name="arxiv_search")

    def test_no_match(self):
        assert not zh_keyword_match("播放音乐", ["论文"], en_text="search papers")

    def test_empty_query(self):
        assert not zh_keyword_match("", ["论文"])


class TestNormalizeText:
    def test_bom_stripped(self):
        assert normalize_text("\ufeffhello") == "hello"

    def test_control_chars_removed(self):
        assert normalize_text("a\x00b\x07c") == "abc"

    def test_newline_kept(self):
        assert normalize_text("a\nb\tc") == "a\nb\tc"

    def test_none(self):
        assert normalize_text(None) == ""
