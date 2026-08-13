# -*- coding: utf-8 -*-
"""RecallService 测试 — 统一召回接口（B2-3 P1, 2026-08-08）。"""
from __future__ import annotations

import pytest

import time

from core.agent.recall.recall_service import (
    RecallService, RecallHit, RecallResult, format_anchors)


class FakeBlock:
    def __init__(self, bid, text, parent=None, children=None, status="active"):
        self.block_id = bid
        self._raw_text = text
        self.parent_id = parent
        self.child_ids = children or []
        self.status = status
        self.atomic_units = []


class FakeDiscourse:
    def __init__(self, blocks):
        self.blocks = {b.block_id: b for b in blocks}


def _svc(blocks):
    return RecallService(engine=None, chunk_store=None, discourse=FakeDiscourse(blocks), llm=None)


BLOCKS = [
    FakeBlock("b1", "AES 密钥需要存储在安全的地方", children=["b2"]),
    FakeBlock("b2", "密钥泄露会导致数据被解密", parent="b1"),
    FakeBlock("b3", "今天天气很好适合出去走走"),
]


class TestFormatAnchors:
    """v2.1 召回→执行层桥: 锚点格式化（候选注入, 不塞原文）。"""

    def test_empty_result_returns_empty(self):
        assert format_anchors(RecallResult(query="q")) == ""
        assert format_anchors(None) == ""

    def test_formats_hits_with_source_and_score(self):
        rr = RecallResult(query="q", hits=[
            RecallHit(id="h1", text="AES 密钥安全存储",
                      source="bm25", score=0.8, confidence=0.9,
                      path=["docs/only/recall/DESIGN.md", "§五"]),
            RecallHit(id="h2", text="多行\n文本折叠",
                      source="vector", score=0.6, confidence=0.8),
        ])
        out = format_anchors(rr)
        assert "## 候选锚点" in out
        assert "[bm25" in out and "0.72" in out  # 0.8×0.9
        assert "多行 文本折叠" in out  # 换行折叠
        assert "精确查阅" in out
        # 索引语义: 锚点携带源文档路径（执行层 file_read 精确查阅用）
        assert "docs/only/recall/DESIGN.md" in out

    def test_truncates_long_hits(self):
        long_text = "x" * 300
        rr = RecallResult(query="q", hits=[RecallHit(
            id="h1", text=long_text, source="vector",
            score=0.5, confidence=0.5)])
        out = format_anchors(rr, max_chars=500)
        assert len(out) <= 500 + 5
        assert "x" * 200 not in out  # 截断到 160

    def test_respects_max_hits(self):
        rr = RecallResult(query="q", hits=[
            RecallHit(id=f"h{i}", text=f"t{i}", source="bm25",
                      score=0.5, confidence=0.5) for i in range(8)])
        out = format_anchors(rr, max_hits=3)
        assert out.count("- [bm25") == 3


class TestTemporalConstraint:
    """时序约束（2026-08-09）: 块 created_at → 排序因子, 旧文档降权。"""

    def _svc(self, blocks, half_life=60.0):
        svc = _svc(blocks)
        svc.time_half_life_days = half_life
        return svc

    def test_factor_neutral_when_disabled(self):
        svc = _svc(BLOCKS)
        hit = RecallHit(id="h", text="t", source="bm25")
        assert svc._temporal_factor(hit) == 1.0  # 半衰期 0 = 关

    def test_factor_neutral_without_timestamp(self):
        svc = self._svc(BLOCKS)
        hit = RecallHit(id="h", text="t", source="bm25", created_at=0.0)
        assert svc._temporal_factor(hit) == 1.0

    def test_old_doc_decays_to_floor(self):
        svc = self._svc(BLOCKS, half_life=30.0)
        hit = RecallHit(id="h", text="t", source="bm25",
                        created_at=time.time() - 360 * 86400)  # 360 天前
        f = svc._temporal_factor(hit)
        assert f == 0.3  # 下限

    def test_recent_doc_factor_high(self):
        svc = self._svc(BLOCKS, half_life=30.0)
        hit = RecallHit(id="h", text="t", source="bm25",
                        created_at=time.time() - 5 * 86400)  # 5 天前
        f = svc._temporal_factor(hit)
        assert 0.3 < f <= 1.0

    def test_temporal_reranks_newer_first(self):
        """同相关度时新文档排在旧文档前（排序 key 融合时序因子）。"""
        now = time.time()
        old = RecallHit(id="old", text="旧版交接文档", source="bm25",
                        score=0.9, confidence=1.0,
                        created_at=now - 300 * 86400)
        new = RecallHit(id="new", text="新版交接文档", source="bm25",
                        score=0.8, confidence=1.0, created_at=now - 2 * 86400)
        svc = self._svc(BLOCKS, half_life=60.0)
        # fused: old=0.9, new=0.8; 时序后: old 0.9×0.3=0.27, new 0.8×~0.98
        assert (new.fused() * svc._temporal_factor(new)
                > old.fused() * svc._temporal_factor(old))


def test_recall_returns_fused_hits():
    svc = _svc(BLOCKS)
    svc.fuse_mode = "linear"   # 本测试断言 linear 融合分降序
    result = svc.recall("AES 密钥")
    assert result.hits, "应有命中"
    # 融合分降序
    fused = [h.fused() for h in result.hits]
    assert fused == sorted(fused, reverse=True)


def test_bm25_anchor_finds_keyword_block():
    svc = _svc(BLOCKS)
    # 直测 bm25 路由语义（2026-08-13）: 融合去重会吞掉同 id 的
    # vector/bm25 版本, 且 vector 短文本余弦会把 b3 带进 top — 路由级
    # 断言与融合排序解耦。
    hits = svc._bm25_anchors("密钥存储", top_k=5)
    ids = [h.id for h in hits]
    assert ids[0] == "b1"
    assert "b3" not in ids


def test_spo_alignment_ranks_relation_block():
    """约束投影对齐: 查询 SPO(密钥,需要,存储) 应命中同构块。"""
    svc = _svc(BLOCKS)
    hits = svc._spo_anchors("密钥需要存储", top_k=5)
    assert hits, "SPO 对齐应有命中"
    assert hits[0].id == "b1"
    assert hits[0].source.endswith("spo")


def test_diffusion_reaches_neighbor():
    svc = _svc(BLOCKS)
    svc._ensure_blocks()
    diff = svc._diffuse(
        [RecallHit(id="b1", text="AES 密钥", source="vector",
                   score=0.9)], k=1)
    # b1 的子节点 b2 应通过扩散出现
    assert any(h.id == "b2" for h in diff)
    assert all(h.hops >= 1 for h in diff)


def test_feedback_adapts_confidence_a18():
    svc = _svc(BLOCKS)
    before = svc._confidence("bm25")
    # 2026-08-13: 直接构造结果 — 融合去重后 bm25 命中可能不出现,
    # feedback 机制本身与融合排序解耦。
    res = RecallResult(query="q", hits=[
        RecallHit(id="b1", text="t", source="bm25",
                  score=0.5, confidence=0.5)])
    svc._last_result = res
    target = next(h for h in res.hits if h.source.endswith("bm25"))
    svc.feedback(target.id, useful=True)
    after = svc._confidence("bm25")
    assert after > before
    # 负反馈下调
    svc.feedback(target.id, useful=False)
    assert svc._confidence("bm25") < after
    # 白盒权重
    w = svc.weights()
    assert "vector" in w and "spo" in w


def test_set_weight_clamp():
    svc = _svc(BLOCKS)
    svc.set_weight("spo", 1.5)
    assert svc._confidence("spo") <= 1.0
    svc.set_weight("spo", -1)
    assert svc._confidence("spo") >= 0.1


def test_hyde_fallback_without_llm():
    svc = _svc(BLOCKS)
    assert svc._expand_questions("测试") == ["测试"]


def test_pronoun_closed_loop():
    """代词闭环: '它' 用块内最近主语补全。"""
    svc = _svc(BLOCKS)
    spo = svc._extract_spo("密钥需要加密。它要保存在安全区")
    assert spo, "应提炼出 SPO"
    # 第二句的主语 '它' 应被补全为 '密钥'
    assert any(s.get("subject") == "密钥" for s in spo)


def test_spo_debug():
    """调试: 查 query 与 b1 的实际 SPO 值（防精确匹配误判）。"""
    from core.agent.recall.recall_service import RecallService
    svc = RecallService(engine=None, chunk_store=None,
                        discourse=FakeDiscourse(BLOCKS), llm=None)
    q_spo = svc._extract_spo("密钥需要存储")
    b_spo = svc._extract_spo("AES 密钥需要存储在安全的地方")
    print("QUERY SPO:", q_spo)
    print("B1 SPO:", b_spo)
    assert q_spo or b_spo  # 至少一方应有提取（防环境静默空）


# ── 索引缓存竞态修复（2026-08-11）──────────────────────────────


def test_cache_text_hash_invalidates_stale_entries(tmp_path):
    """内容指纹: bid 复用但文本变了 → 弃用旧缓存（防旧模型维度污染）。"""
    svc = _svc(BLOCKS)
    svc._index_cache_dir = str(tmp_path)  # 隔离: 不污染 data/recall_index/
    svc._load_index_cache = lambda sid: None  # 不读磁盘, 纯内存验证
    svc._index_cache = {"b1": {
        "hash": "stale", "spo": [{"subject": "旧"}], "vector": [0.5] * 4,
    }}
    blocks = svc._ensure_blocks("default")
    b1 = next(b for b in blocks if b["id"] == "b1")
    assert b1["vector"] is None, "文本指纹不匹配 → 旧向量必须弃用"
    assert b1["spo"] != [{"subject": "旧"}], "旧 SPO 必须重算"


def test_cache_text_hash_keeps_fresh_entries(tmp_path):
    """内容指纹: 文本一致 → 直接复用缓存向量/SPO。"""
    svc = _svc(BLOCKS)
    svc._index_cache_dir = str(tmp_path)  # 隔离: 不污染 data/recall_index/
    svc._load_index_cache = lambda sid: None
    text = "AES 密钥需要存储在安全的地方"
    svc._index_cache = {"b1": {
        "hash": svc._text_hash(text),
        "spo": [{"subject": "AES 密钥", "predicate": "存储", "object": "安全的地方"}],
        "vector": [0.1, 0.2, 0.3, 0.4],
    }}
    blocks = svc._ensure_blocks("default")
    b1 = next(b for b in blocks if b["id"] == "b1")
    assert b1["vector"] == [0.1, 0.2, 0.3, 0.4]
    assert b1["spo"][0]["subject"] == "AES 密钥"


def test_flush_writes_per_file_subset(tmp_path):
    """分文件落盘: default 与 global 各自只写自己池的 bid。"""
    svc = _svc(BLOCKS)
    svc._index_cache_dir = str(tmp_path)
    svc._file_bids = {"default": {"b1", "b2"}, "global": {"b1", "b3"}}
    svc._index_cache = {
        "b1": {"hash": "h", "spo": [], "vector": [1.0]},
        "b2": {"hash": "h", "spo": [], "vector": [2.0]},
        "b3": {"hash": "h", "spo": [], "vector": [3.0]},
    }
    svc.flush_index_cache()
    import json
    with open(tmp_path / "default.json", encoding="utf-8") as f:
        default = json.load(f)["blocks"]
    with open(tmp_path / "global.json", encoding="utf-8") as f:
        global_ = json.load(f)["blocks"]
    assert set(default) == {"b1", "b2"}   # 不含 b3
    assert set(global_) == {"b1", "b3"}   # 不含 b2
    assert default["b1"]["vector"] == [1.0]
    assert global_["b3"]["vector"] == [3.0]


def test_load_merges_not_overwrites(tmp_path):
    """合并加载: global 加载不覆盖 default 已加载条目。"""
    import json
    (tmp_path / "default.json").write_text(
        json.dumps({"blocks": {"b1": {"hash": "h1", "vector": [1.0]}}}),
        encoding="utf-8")
    (tmp_path / "global.json").write_text(
        json.dumps({"blocks": {"b3": {"hash": "h3", "vector": [3.0]}}}),
        encoding="utf-8")
    svc = _svc(BLOCKS)
    svc._index_cache_dir = str(tmp_path)
    svc._load_index_cache("default")
    svc._load_index_cache("global")
    assert "b1" in svc._index_cache and "b3" in svc._index_cache
    assert svc._file_bids["default"] == {"b1"}
    assert svc._file_bids["global"] == {"b3"}


# ── 并行子问题分解 + DAG 分层扩展（2026-08-11, SUBGRAPH_EXPANSION_UPGRADE）──


class FakeLLM:
    """模拟 LLM: 返回多行子问题。"""

    def __init__(self, lines):
        self._lines = lines

    def chat(self, messages):
        return "\n".join(self._lines)


def test_expand_questions_uses_decompose_count():
    svc = _svc(BLOCKS)
    svc._llm = FakeLLM(["子问题A", "子问题B", "子问题C", "子问题D"])
    svc.decompose_subqueries = 4
    out = svc._expand_questions("原问题")
    assert out[0] == "原问题"
    assert len(out) == 5  # 原问题 + 4 个子问题


def test_expand_questions_records_miss_on_failure():
    svc = _svc(BLOCKS)

    class Boom:
        def chat(self, messages):
            raise RuntimeError("llm down")

    svc._llm = Boom()
    svc._decompose_misses = []
    out = svc._expand_questions("问题")
    assert out == ["问题"]  # 兜底原 query
    assert len(svc._decompose_misses) == 1  # 失败已记录


def test_hyde_anchors_parallel_full_route():
    """并行分解: 每子问题走 vector+bm25+spo 全路, 合并去重。"""
    svc = _svc(BLOCKS)
    svc.parallel_decompose = True
    svc.decompose_max_workers = 2
    svc._decompose_misses = []
    hits = svc._hyde_anchors(["密钥存储", "天气"], top_k=5)
    ids = {h.id for h in hits}
    assert "b1" in ids, "bm25/vector 应命中密钥块"
    assert all(h.source == "hyde" for h in hits)


def test_hyde_anchors_records_empty_subquery_miss():
    svc = _svc(BLOCKS)
    svc.parallel_decompose = True
    svc._decompose_misses = []
    # 强制三路全空, 验证"子问题空召回 → 记录 miss"（不依赖语料是否真命中）
    svc._vector_anchors = lambda q, top_k, blocks=None: []
    svc._bm25_anchors = lambda q, top_k, blocks=None: []
    svc._spo_anchors = lambda q, top_k, blocks=None: []
    svc._hyde_anchors(["某子问题"], top_k=5)
    assert len(svc._decompose_misses) == 1
    assert svc._decompose_misses[0]["error"] == "empty recall"
