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

    def test_parent_context_appended_at_return_layer(self):
        rr = RecallResult(query="q", hits=[
            RecallHit(id="h1", text="小块正文", source="bm25",
                      score=0.5, confidence=0.5,
                      parent_context="文件摘要（方案 B 返回层附加, 不参与排序）"),
        ])
        out = format_anchors(rr)
        assert "| 文件: 文件摘要" in out


class TestMultiIntentSegments:
    """多意图 segments 消费（2026-08-13, 意图副路径实质化）:
    recall(sub_queries=意图拆分段) → 并行多路召回合并。"""

    def test_sub_queries_merged_into_hits(self):
        # b4 只被段查询命中（主查询"AES 密钥"不含"修复"语义）。
        blocks = BLOCKS + [
            FakeBlock("b4", "定位问题后实施修复方案", children=[]),
        ]
        svc = _svc(blocks)
        # 机制级: 段并行召回产出 segment 源命中（含段独有块）
        seg = svc._segment_anchors(["密钥存储位置", "修复方案实施"], 10)
        assert any(h.id == "b4" and h.source == "segment" for h in seg)
        # 集成级: sub_queries 进入 recall 不破坏主链路, 段独有块可被召回
        rr = svc.recall("AES 密钥", top_k=10, use_hyde=False,
                        sub_queries=["密钥存储位置", "修复方案实施"])
        assert any(h.id == "b4" for h in rr.hits)

    def test_single_or_empty_segments_skip(self):
        svc = _svc(BLOCKS)
        rr1 = svc.recall("AES 密钥", top_k=10, use_hyde=False,
                         sub_queries=["只有一个段"])
        rr2 = svc.recall("AES 密钥", top_k=10, use_hyde=False,
                         sub_queries=[])
        assert not any(h.source == "segment" for h in rr1.hits)
        assert not any(h.source == "segment" for h in rr2.hits)


class TestA18Persistence:
    """A18 持久化（2026-08-13）: 置信度/权重覆盖落盘, 重启不丢。"""

    def test_feedback_persists_across_services(self, tmp_path):
        svc = _svc(BLOCKS)
        svc._index_cache_dir = str(tmp_path)  # 测试隔离, 不碰生产 data/
        rr = svc.recall("AES 密钥", top_k=5, use_hyde=False)
        assert rr.hits
        target = rr.hits[0]
        base_source = target.source.split(":", 1)[-1]  # hot:bm25 -> bm25
        before = svc._confidence(base_source)
        r = svc.feedback(target.id, useful=True, intent="记忆召回")
        assert r["ok"]
        assert r["source"] == base_source and r["after"] > before
        # 新服务实例（同一 data 目录）加载持久化置信度
        svc2 = _svc(BLOCKS)
        # __init__ 加载发生在 _index_cache_dir 赋值前（指向生产目录）—
        # 测试隔离: 赋值后重载一次
        svc2._index_cache_dir = str(tmp_path)
        svc2._load_learned_conf()
        # per-intent 置信度已持久化（不假设 top1 是 vector——单测环境
        # 无真实 embedding 时 bm25 占 top1）; 全局不受 per-intent 影响
        assert svc2._confidence(base_source, "记忆召回") == r["after"]
        assert svc2._confidence(base_source) == before

    def test_rerank_file_signal_boosts_doc_blocks(self):
        """B 尾巴（2026-08-14）: 文件层信号进重排权重（不保底抬分）。"""
        svc = _svc(BLOCKS)
        h_low = RecallHit(id="a", text="t", source="bm25", score=0.5,
                          confidence=0.5, path=["docs/x.md"])
        h_high = RecallHit(id="b", text="t", source="bm25", score=0.6,
                           confidence=0.5, path=["docs/y.md"])
        h_low.scores = {"bm25": 0.5}
        h_high.scores = {"bm25": 0.6}
        # 无文件信号 → 原分高者第一
        out = svc._rerank([h_low, h_high])
        assert out[0].id == "b"
        # 文件摘要命中 x.md → a 的块加权反超（0.25×5/6 + 0.15×0.9 > 0.25）
        out2 = svc._rerank([h_low, h_high], file_sims={"docs/x.md": 0.9})
        assert out2[0].id == "a"
        # 未命中文件 → 无影响
        out3 = svc._rerank([h_low, h_high], file_sims={"docs/z.md": 0.9})
        assert out3[0].id == "b"

    def test_pool_extras_expand_candidates(self, monkeypatch):
        """C 最小版（2026-08-14）: 文件命中 → 节块进候选池扩展,
        不抬排序（pool_extras 独立于 hits, 供子图编译消费）。"""
        svc = _svc(BLOCKS)
        svc._file_pool = True
        svc._file_pool_per_doc = 2
        fake_hit = RecallHit(
            id="pool1", text="补充块", source="vector", score=0.25,
            confidence=0.5, path=["docs/x.md"])

        def fake_doc_scores(q):
            return {"docs/x.md": 0.8}, 1.0, 1

        def fake_global_blocks():
            return [{"id": "pool1", "text": "补充块", "doc": "docs/x.md",
                     "vector": [0.1] * 8, "heading": "", "spo": [],
                     "temperature": "active"}]

        def fake_vec(q, top_k, blocks=None, query_vec=None,
                     prf_vec=None, boost_docs=None, pool_docs=None):
            return [fake_hit] if pool_docs else []

        monkeypatch.setattr(svc, "_file_doc_scores", fake_doc_scores)
        monkeypatch.setattr(svc, "_ensure_global_blocks", fake_global_blocks)
        monkeypatch.setattr(svc, "_vector_anchors", fake_vec)
        rr = svc.recall("AES 密钥", top_k=5, use_hyde=False)
        assert rr.pool_extras and rr.pool_extras[0].id == "pool1"
        assert rr.pool_extras[0].source == "cold:pool"
        assert all(h.id != "pool1" for h in rr.hits)  # 不混入排序

    def test_full_text_backfilled_p9(self):
        """P9 原文保留（2026-08-15 一致性测试）: 命中必须携带全文,
        摘要/截断只影响展示（text[:200]）, 不影响存在（full_text）。"""
        svc = _svc(BLOCKS)
        rr = svc.recall("AES 密钥", top_k=5, use_hyde=False)
        assert rr.hits
        for h in rr.hits[:2]:
            assert h.full_text, "P9: 命中必须携带全文"
            assert len(h.full_text) >= len(h.text)
        d = rr.hits[0].to_dict()
        assert d["full_text"], "P9: to_dict 必须带全文（放大路径）"

    def test_set_weight_rerank_override_persists(self, tmp_path):
        svc = _svc(BLOCKS)
        svc._index_cache_dir = str(tmp_path)
        r = svc.set_weight("bm25", 0.9, intent="任务规划", target="rerank")
        assert r["ok"] and r["weight"] == 0.9
        svc2 = _svc(BLOCKS)
        svc2._index_cache_dir = str(tmp_path)
        svc2._load_learned_conf()
        w = svc2.weights("任务规划")
        assert w["rerank"]["bm25"] == 0.9
        # 全局置信度不受 per-intent 覆盖影响
        assert svc2._confidence("bm25") == 0.7

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
