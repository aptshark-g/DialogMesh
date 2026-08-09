# -*- coding: utf-8 -*-
"""G10-P3: 补齐的 unified_search / domain_adapter 模块测试."""
from __future__ import annotations

import os
import tempfile

import pytest

from core.agent.persistence.unified_graph_store import UnifiedGraphStore
from core.agent.persistence.unified_search import UnifiedSearch
from core.agent.persistence.domain_adapter import DomainAdapter


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = UnifiedGraphStore(db_path=path)
    yield s
    s.close()
    os.unlink(path)


def test_unified_search_keyword_and_summary(store):
    store.save_node("n1", "topic_block", "C", {"text": "gateway nginx config"},
                    summary="gateway monitoring setup", importance=0.9)
    store.save_node("n2", "topic_block", "C", {"text": "causal DAG expansion"},
                    summary="causal reasoning", importance=0.5)

    searcher = UnifiedSearch(store)
    kw = searcher.keyword_search("gateway")
    assert len(kw) == 1 and kw[0]["node_id"] == "n1"

    sm = searcher.summary_search("causal")
    assert len(sm) == 1 and sm[0]["node_id"] == "n2"

    with_domain = searcher.keyword_search("config", domain="C")
    assert len(with_domain) == 1


def test_domain_adapter_save_load(store):
    adapter = DomainAdapter(store, "B", session_id="sess-1")
    assert adapter._save("step1", "behavior_step",
                         {"action": "run"}, summary="run tests", importance=0.8)
    node = adapter._load("step1")
    assert node is not None
    assert node["domain"] == "B"
    assert node["session_id"] == "sess-1"
    assert node["data"]["action"] == "run"

    all_nodes = adapter._load_all("behavior_step")
    assert len(all_nodes) == 1


def test_multi_domain_adapters_importable():
    """此前 ImportError（domain_adapter 缺失）→ 现在可导入."""
    from core.agent.persistence.multi_domain_adapters import (
        BehaviorAdapter, UserProfileAdapter, CausalAdapter,
    )
    assert BehaviorAdapter and UserProfileAdapter and CausalAdapter


def test_hybrid_hyde_and_store_safety_importable():
    """此前 ImportError（unified_search 缺失）→ 现在可导入."""
    from core.agent.persistence.hybrid_hyde import HybridSearchEngine, HyDERetriever
    from core.agent.persistence.store_safety import SafeUnifiedStore
    assert HybridSearchEngine and HyDERetriever and SafeUnifiedStore
