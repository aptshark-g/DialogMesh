"""HeuristicDistiller 测试 — 二阶抽象提炼管道（发散/收敛/反推/规则兜底）。"""

from __future__ import annotations

from types import SimpleNamespace

from core.agent.blueprint.heuristic_distiller import HeuristicDistiller
from core.agent.blueprint.heuristic_inventory import Heuristic, HeuristicInventory


class _FakeLLM:
    """按调用顺序返回结构化响应的假 LLM（duck-type generate）。"""

    def __init__(self, responses):
        self._responses = responses
        self.calls = 0

    def generate(self, _req):
        self.calls += 1
        idx = min(self.calls - 1, len(self._responses) - 1)
        return SimpleNamespace(structured=self._responses[idx])


def _samples(n=6):
    return [
        {"intent": f"task{i % 2}", "tool_sequence": ["search", "read"],
         "strategy": "TEMPLATE", "node_count": 4}
        for i in range(n)
    ]


def test_rule_baseline_without_llm(tmp_path):
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    d = HeuristicDistiller(llm_provider=None, inventory=inv)
    r = d.try_distill(samples=_samples(), reason="no_llm")
    assert r["triggered"] is True
    assert r["mode"] == "rule"
    assert r["added"] >= 1
    rules = [h for h in inv.all(active_only=False) if h.source == "rule"]
    assert len(rules) >= 1
    assert "工具链" in rules[0].pattern_desc


def test_insufficient_samples_not_triggered(tmp_path):
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    d = HeuristicDistiller(llm_provider=_FakeLLM([]), inventory=inv)
    r = d.try_distill(samples=[{"intent": "x"}], reason="few")
    assert r["triggered"] is False
    assert r["reason"] == "insufficient_samples"


def test_llm_pipeline_verifies_and_promotes(tmp_path):
    cand = {
        "pattern_desc": "先验证假设再选方案",
        "conditions": "多方案候选时",
        "counterexample": "时间紧迫需快速响应时",
        "reasoning_path": "验证假设降低返工成本",
        "insight_score": 0.8,
    }
    responses = [
        {"candidates": [cand, {
            "pattern_desc": "低质候选", "conditions": "x", "counterexample": "y",
            "reasoning_path": "z", "insight_score": 0.2,
        }]},
        {"verdicts": [
            {"index": 0, "keep": True, "reason": "可解释历史决策", "insight_score": 0.8},
            {"index": 1, "keep": False, "reason": "重复已有种子", "insight_score": 0.2},
        ]},
        {"reasoning_path": "若验证先行, 工具选择会偏向证据充足路径",
         "evidence": ["样本1 支持"], "updated_insight": 0.8},
        {"matches": [1, 1, 1, 0, 1, 1]},  # 5/6 ≈ 0.833 > 0.8 → 过拟合!
    ]
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    d = HeuristicDistiller(llm_provider=_FakeLLM(responses), inventory=inv)
    r = d.try_distill(samples=_samples(6), variant="commonalize")
    assert r["candidates"] == 2
    assert r["kept"] == 1
    assert r["expanded"] == 1
    # coverage 0.833 > 0.80 → 过拟合拒绝
    assert r["verified"] == 0


def test_llm_pipeline_coverage_ok_promotes(tmp_path):
    cand = {
        "pattern_desc": "结构对齐找共性",
        "conditions": "表面不同的场景需要抽象",
        "counterexample": "表面与结构都不同时",
        "reasoning_path": "结构对齐揭示共享机制",
        "insight_score": 0.75,
    }
    responses = [
        {"candidates": [cand]},
        {"verdicts": [{"index": 0, "keep": True, "reason": "ok", "insight_score": 0.75}]},
        {"reasoning_path": "扩展: 若结构对齐成立, 远迁移可用",
         "evidence": ["样本2 支持"], "updated_insight": 0.75},
        {"matches": [1, 1, 1, 0, 1, 1, 1, 0, 1, 1]},  # 8/10 = 0.80 合格上界
    ]
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    d = HeuristicDistiller(llm_provider=_FakeLLM(responses), inventory=inv)
    r = d.try_distill(samples=_samples(10), variant="far_transfer")
    assert r["verified"] == 1
    h = inv.get(r["heuristics"][0])
    assert h.source == "distilled"
    assert h.coverage == 0.8
    assert "反事实" in h.reasoning_path or "扩展" in h.reasoning_path


def test_llm_pipeline_low_coverage_rejected(tmp_path):
    cand = {
        "pattern_desc": "幻觉式启发",
        "conditions": "无",
        "counterexample": "无",
        "reasoning_path": "编的",
        "insight_score": 0.7,
    }
    responses = [
        {"candidates": [cand]},
        {"verdicts": [{"index": 0, "keep": True, "reason": "ok", "insight_score": 0.7}]},
        {"reasoning_path": "扩展", "evidence": [], "updated_insight": 0.7},
        {"matches": [1, 0, 0, 0, 0, 0]},  # 1/6 ≈ 0.17 < 0.60 → 幻觉拒绝
    ]
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    d = HeuristicDistiller(llm_provider=_FakeLLM(responses), inventory=inv)
    r = d.try_distill(samples=_samples(6))
    assert r["verified"] == 0


def test_verify_sample_size_param_clamped():
    """反推采样成本护栏: 默认 12, 上限 20, 下限 4。"""
    assert HeuristicDistiller()._verify_sample_size == 12
    assert HeuristicDistiller(verify_sample_size=100)._verify_sample_size == 20
    assert HeuristicDistiller(verify_sample_size=1)._verify_sample_size == 4
    assert HeuristicDistiller(verify_sample_size=8)._verify_sample_size == 8


def test_health_check_via_bridge(tmp_path):
    """learning_bridge.check_heuristic_health: 停用 stale + 统计。"""
    from core.agent.blueprint.learning_bridge import LearningBridge
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    inv.add(Heuristic(
        heuristic_id="h_bad_1", pattern_desc="坏启发",
        conditions="x", counterexample="y", reasoning_path="z",
        coverage=0.1, source="distilled",
    ))
    lb = LearningBridge()
    lb.attach_distiller(HeuristicDistiller(llm_provider=None, inventory=inv))
    r = lb.check_heuristic_health(threshold=0.5)
    assert r["checked"] is True
    assert "h_bad_1" in r["deactivated"]
    assert inv.get("h_bad_1").active is False


def test_info_route_three_signal():
    """P×I 路由（2026-08-07 修正）: 高频聚合 / 低频高价值保留 / 低频低价值过滤。"""
    assert HeuristicDistiller._info_route(0.8, 0.5) == "aggregate"
    assert HeuristicDistiller._info_route(0.1, 0.8) == "preserve"
    # 用户核心修正: 低频低价值 = filter（垃圾不因稀有而保留）
    assert HeuristicDistiller._info_route(0.1, 0.2) == "filter"
    assert HeuristicDistiller._info_route(0.4, 0.9) == "filter"  # 中频


def test_semantic_value_proxy():
    """价值代理（无 LLM）: 意图多样性 + 新颖度 + 长度。"""
    assert HeuristicDistiller._semantic_value_proxy(3, 5, 5) >= 0.6
    assert HeuristicDistiller._semantic_value_proxy(1, 2, 2) < 0.6
