# -*- coding: utf-8 -*-
"""P0 写即索引测试: write_file 产出内容进 chunk_store（可召回）。"""
import pytest

from core.agent.tools.registry import ToolRegistry
from core.agent.storage.chunk_store import ChunkStore


def test_file_write_indexes_into_chunk_store(tmp_path):
    cs = ChunkStore(backend="in_memory")
    ToolRegistry.set_config({"chunk_store": cs})
    target = tmp_path / "produced.md"
    content = "统一召回方案设计文档: 混合锚点 BGE+BM25+SPO, RRF 融合, 时序约束。"
    from core.agent.tools.builtin import _file_write
    r = _file_write(str(target), content)
    assert r.success
    # 内容已索引进 chunk_store
    hits = cs.search("混合锚点", top_k=5)
    assert any(h.block_id == f"file:{target}" for h in hits)


def test_short_content_not_indexed(tmp_path):
    cs = ChunkStore(backend="in_memory")
    ToolRegistry.set_config({"chunk_store": cs})
    from core.agent.tools.builtin import _file_write
    r = _file_write(str(tmp_path / "tiny.md"), "hi")
    assert r.success
    assert len(cs.search("hi", top_k=5)) == 0  # <20 字符不索引


def test_recall_global_pool_merges_produced_blocks(tmp_path):
    """P0 闭环: produced 原子进 recall 冷路径块池（可被召回）。"""
    from core.agent.recall.recall_service import RecallService
    cs = ChunkStore(backend="in_memory")
    ToolRegistry.set_config({"chunk_store": cs})
    content = "统一召回方案: 混合锚点 BGE+BM25+SPO, RRF 融合, 时序约束, 情景再现。"
    from core.agent.tools.builtin import _file_write
    _file_write(str(tmp_path / "doc.md"), content)
    svc = RecallService(engine=None, chunk_store=cs, discourse=None, llm=None)
    blocks = svc._ensure_global_blocks()
    produced = [b for b in blocks if b["id"].startswith("file:")]
    assert len(produced) == 1
    assert produced[0]["path"] == [str(tmp_path / "doc.md")]
    # 真召回: query 命中产出块
    res = svc.recall("混合锚点 RRF 融合", top_k=5)
    assert any(h.id.startswith("file:") for h in res.hits)


def test_produced_vector_persisted_via_g0(monkeypatch, tmp_path):
    """G0 记忆闭环: produced 块向量落盘 global.json, 二次加载恢复。"""
    import os
    from core.agent.recall.recall_service import RecallService
    cs = ChunkStore(backend="in_memory")
    ToolRegistry.set_config({"chunk_store": cs})
    content = "产出记忆: 混合锚点 BGE+BM25+SPO, RRF 融合, 时序约束。"
    from core.agent.tools.builtin import _file_write
    _file_write(str(tmp_path / "m.md"), content)
    svc = RecallService(engine=None, chunk_store=cs, discourse=None, llm=None)
    monkeypatch.setattr(
        svc, "_embed", lambda text: [0.1] * 32)
    blocks = svc._ensure_global_blocks()
    produced = [b for b in blocks if b["id"].startswith("file:")]
    assert produced[0]["vector"] is not None
    # 落盘
    import json
    path = svc._index_path("global")
    assert os.path.exists(path)
    data = json.load(open(path, encoding="utf-8"))
    bid = produced[0]["id"]
    assert bid in data.get("blocks", {})
    assert data["blocks"][bid].get("vector") is not None
    # 二次实例加载恢复（模拟重启）
    svc2 = RecallService(engine=None, chunk_store=cs, discourse=None, llm=None)
    svc2._load_index_cache("global")
    assert svc2._index_cache.get(bid, {}).get("vector") is not None
