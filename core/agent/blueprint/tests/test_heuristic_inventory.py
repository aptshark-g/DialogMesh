"""HeuristicInventory 测试 — 二阶抽象启发库存（种子/检索/注入/持久化）。"""

from __future__ import annotations

from core.agent.blueprint.heuristic_inventory import (
    Heuristic, HeuristicInventory, SEED_HEURISTICS,
)


def test_seed_loads_when_empty(tmp_path):
    inv = HeuristicInventory(str(tmp_path / "heuristics.json"))
    stats = inv.stats()
    assert stats["total"] == len(SEED_HEURISTICS) == 2
    assert stats["by_source"].get("seed") == 2
    assert stats["active"] == 2


def test_seed_persisted(tmp_path):
    path = str(tmp_path / "h.json")
    inv1 = HeuristicInventory(path)
    inv2 = HeuristicInventory(path)
    assert inv2.get("h_seed_diff") is not None
    assert inv2.get("h_seed_diff").pattern_desc.startswith("差异即信息")


def test_add_and_deactivate(tmp_path):
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    h = Heuristic(
        heuristic_id="h_test_1",
        pattern_desc="测试启发",
        conditions="有样本时",
        counterexample="无样本时",
        reasoning_path="测试路径",
        coverage=0.7,
        source="distilled",
    )
    assert inv.add(h) is True
    assert inv.get("h_test_1").source == "distilled"
    assert inv.deactivate("h_test_1") is True
    assert inv.get("h_test_1").active is False
    assert inv.stats()["active"] == 2  # 只剩 2 条种子


def test_format_for_prompt_contains_structure(tmp_path):
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    block = inv.format_for_prompt("低概率事件怎么处理", top_k=2)
    assert "[决策依据]" in block
    assert "差异即信息" in block
    assert "适用:" in block and "反例:" in block and "路径:" in block


def test_search_ranks_relevant(tmp_path):
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    hits = inv.search("分类 集合 抽象")
    assert len(hits) >= 1
    assert hits[0].heuristic_id == "h_seed_classify"


def test_kernel_heuristics_list(monkeypatch, tmp_path):
    """白盒视图: kernel_heuristics_list 返回库存全量 + 统计。"""
    from core.agent.kernel.dispatch import kernel_heuristics_list

    class _Eng:
        def __init__(self):
            self._heuristic_inventory = HeuristicInventory(str(tmp_path / "hk.json"))

    monkeypatch.setattr("core.agent.kernel.dispatch.get_engine", lambda: _Eng())
    data = kernel_heuristics_list()
    assert data["stats"]["total"] == 2
    assert data["stats"]["by_source"].get("seed") == 2
    ids = [h["heuristic_id"] for h in data["heuristics"]]
    assert "h_seed_diff" in ids and "h_seed_classify" in ids


def test_check_health_deactivates_stale(tmp_path):
    """活性监测: 蒸馏/规则启发 coverage 跌破阈值 → stale; 种子不查。"""
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    inv.add(Heuristic(
        heuristic_id="h_stale_1", pattern_desc="过时启发",
        conditions="x", counterexample="y", reasoning_path="z",
        coverage=0.3, source="distilled",
    ))
    inv.add(Heuristic(
        heuristic_id="h_stale_2", pattern_desc="规则启发低覆盖",
        conditions="x", counterexample="y", reasoning_path="z",
        coverage=0.2, source="rule",
    ))
    inv.add(Heuristic(
        heuristic_id="h_ok_1", pattern_desc="健康启发",
        conditions="x", counterexample="y", reasoning_path="z",
        coverage=0.7, source="distilled",
    ))
    stale = inv.check_health(threshold=0.5)
    ids = {h.heuristic_id for h in stale}
    assert "h_stale_1" in ids and "h_stale_2" in ids
    assert "h_ok_1" not in ids
    # 种子不参与自动停用
    assert not any(h.heuristic_id.startswith("h_seed") for h in stale)
    deactivated = inv.deactivate_stale(threshold=0.5)
    assert "h_stale_1" in deactivated and "h_stale_2" in deactivated
    assert inv.get("h_stale_1").active is False
    assert inv.get("h_ok_1").active is True
