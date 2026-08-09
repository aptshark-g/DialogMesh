"""5.2.1 FactStore stress — budget/mutation throughput baselines."""

from __future__ import annotations

import time

from core.agent.profile.fact_store import FactStore


def test_fact_store_1000_writes(tmp_path):
    # 1000 条 × ~40 字符 > 20000 → 预算会截断；这是吞吐测试，预算要给足
    store = FactStore(path=str(tmp_path / "USER.md"), char_limit=100000)
    t0 = time.perf_counter()
    for i in range(1000):
        store.add(f"fact number {i} about user preferences")
    elapsed = time.perf_counter() - t0
    assert store.usage["entries"] == 1000
    assert elapsed < 30.0  # loose ceiling; regression guard, not a benchmark


def test_fact_store_budget_rejection_fast(tmp_path):
    store = FactStore(path=str(tmp_path / "USER.md"), char_limit=200)
    store.add("short")
    long_fact = "x" * 300  # 超过 200 限额 → 每次必然拒绝
    t0 = time.perf_counter()
    for _ in range(500):
        res = store.add(long_fact)
        assert res["success"] is False
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0


def test_fact_store_batch_single_disk_write(tmp_path):
    """PE-3: begin_batch/end_batch → 1000 次 add 只落盘 1 次（消 thrash）。"""
    store = FactStore(path=str(tmp_path / "USER.md"), char_limit=20000)
    with store:
        for i in range(1000):
            assert store.add(f"batch fact {i}")["success"] is True
    assert store.usage["entries"] == 1000
    assert store.write_stats()["save_count"] == 1
    assert store.write_stats()["batch_depth"] == 0
    # 落盘内容完整（round-trip）
    reloaded = FactStore(path=str(tmp_path / "USER.md"), char_limit=20000)
    assert reloaded.usage["entries"] == 1000


def test_fact_store_single_mode_writes_each_time(tmp_path):
    """非批量模式行为不变：每次 add 各写一次盘（兼容旧语义）。"""
    store = FactStore(path=str(tmp_path / "USER.md"), char_limit=20000)
    for i in range(5):
        store.add(f"fact {i}")
    assert store.write_stats()["save_count"] == 5


def test_fact_store_batch_nested_and_reject(tmp_path):
    """嵌套 batch 只 flush 一次；超预算拒绝不产生 pending 写。"""
    store = FactStore(path=str(tmp_path / "USER.md"), char_limit=300)
    store.begin_batch()
    store.begin_batch()
    assert store.add("f1")["success"] is True
    assert store.add("f2")["success"] is True
    store.end_batch()  # 仍在内层 → 不落盘
    assert store.write_stats()["save_count"] == 0
    res = store.add("x" * 500)  # 超预算拒绝
    assert res["success"] is False
    store.end_batch()  # 最外层 → flush 一次
    assert store.write_stats()["save_count"] == 1
    assert store.usage["entries"] == 2
