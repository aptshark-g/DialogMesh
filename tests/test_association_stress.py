"""Association Chain stress tests — run with ``-m slow`` (A18: 压测不黑盒).

Covers hot-path throughput, convergence under volume, long-chain causal
triggering, and reconciliation scale. Fails loudly with concrete numbers.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent.association.l2_5_belief import BeliefAccumulator, Evidence
from core.agent.association.l4_temporal import L4TemporalEngine
from core.agent.association.causal_substrate import CausalSubstrate
from core.agent.association.skeleton_library import SkeletonLibrary
from core.agent.association.skeleton_matcher import SkeletonMatcher
from core.agent.association.models import CausalConstraints
from core.agent.association.association_funnel import AssociationFunnel

pytestmark = pytest.mark.slow


def _wait_until(predicate, timeout=5.0, interval=0.05):
    """轮询等待条件成立（压测不用固定 sleep）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TestBeliefVolume:
    def test_500_turns_converges_within_budget(self):
        acc = BeliefAccumulator()
        start = time.time()
        for turn in range(1, 501):
            acc.ingest(Evidence("e", "延迟", "causes", 0.6, turn))
        elapsed = time.time() - start
        st = acc.status()
        assert st["locked"] == "诊断", st["locked"]
        assert st["probabilities"]["诊断"] > 0.9
        # 500 ingests should be comfortably under 2s (Bayesian is O(intents)).
        assert elapsed < 2.0, f"500 ingests took {elapsed:.2f}s"

    def test_entropy_stays_stable_under_volume(self):
        acc = BeliefAccumulator()
        for turn in range(1, 201):
            acc.ingest(Evidence("e", "x", "co_occurrence", 0.5, turn))
        st = acc.status()
        assert st["entropy"] < 1.0
        assert st["trace_last_3"], "trace must persist at volume"


class TestTemporalVolume:
    def test_10000_transitions_budget(self):
        eng = L4TemporalEngine(window_size=50)
        intents = ["A", "B", "C", "D"]
        start = time.time()
        for turn in range(10000):
            eng.record(intents[turn % 4], turn=turn)
        elapsed = time.time() - start
        matrix = eng.transition_matrix()
        assert elapsed < 3.0, f"10k transitions took {elapsed:.2f}s"
        assert len(matrix) == 4
        assert abs(sum(matrix["A"].values()) - 1.0) < 1e-6

    def test_predict_next_under_volume(self):
        eng = L4TemporalEngine()
        for turn in range(2000):
            eng.record(["A", "B", "A", "C"][turn % 4], turn=turn)
        preds = eng.predict_next("A", top_k=2)
        assert preds, "must predict next from volume"
        assert abs(sum(p for _, p in preds) - 1.0) < 1e-6


class TestCausalChainVolume:
    def test_long_chain_triggers_and_caps_prior(self):
        class Step:
            def __init__(self, summary):
                self.action_summary = summary
        class Edge:
            def __init__(self, f, t):
                self.from_step_id = f
                self.to_step_id = t
        n = 15
        nodes = {f"s{i}": Step(f"step{i}") for i in range(n)}
        edges = {f"e{i}": Edge(f"s{i}", f"s{i+1}") for i in range(n - 1)}
        graph = type("G", (), {"nodes": nodes, "edges": edges})()
        cs = CausalSubstrate(graph)
        assert cs.should_trigger(n) is True
        chain = [Step(f"step{i}") for i in range(n)]
        results = cs.process_chain(chain)
        assert len(results) >= n - 1
        for r in results:
            assert 0.0 <= r["structural_prior"] <= 0.7, r  # A22 cap

    def test_short_chain_no_trigger(self):
        cs = CausalSubstrate(type("G", (), {"nodes": {}, "edges": {}})())
        assert cs.should_trigger(5) is False


class TestSkeletonMatchVolume:
    def test_1000_matches_budget(self):
        lib = SkeletonLibrary()
        m = SkeletonMatcher(lib)
        start = time.time()
        for _ in range(1000):
            m.match(CausalConstraints(
                domain_hint="software",
                involves_transformation=True,
                involves_storage=True,
            ))
        elapsed = time.time() - start
        assert elapsed < 2.0, f"1000 matches took {elapsed:.2f}s"


class TestReconcileVolume:
    def test_5000_sequences_budget(self):
        eng = L4TemporalEngine(window_size=100)
        seqs = [(f"X{i % 10}", f"Y{(i + 1) % 10}") for i in range(5000)]
        start = time.time()
        r = eng.triparty_reconcile(
            behavior_sequences=seqs,
            engineering_constraints={
                "forbidden_transitions": [["X0", "Y0"]],
                "resource_constraints": {"Y3": False},
            },
        )
        elapsed = time.time() - start
        assert elapsed < 3.0, f"5k sequences took {elapsed:.2f}s"
        assert r["behavior_supported"] == 5000
        assert any(b["to"] == "Y3" for b in r["blocked_transitions"])


class TestRunLayersVolume:
    def test_100_runs_budget(self):
        f = AssociationFunnel()
        start = time.time()
        for _ in range(100):
            r = f.run_layers("scan 0x401000 then patch the binary", pcr_zone="ATOMIC")
            assert "layers" in r
        elapsed = time.time() - start
        assert elapsed < 10.0, f"100 run_layers took {elapsed:.2f}s"


class TestAssociationServiceVolume:
    """Phase 6 — 关联链独立服务压测（M→1 定向通道 + EventLog 并发写）。"""

    def test_2000_events_throughput_no_loss(self, tmp_path):
        """2000 事件经 M→1 通道消费：不丢不重、consumed==enqueued 精确对账。"""
        from core.agent.association.association_service import AssociationService
        svc = AssociationService(db_path=str(tmp_path / "el.db"), queue_size=64)
        svc.start()
        start = time.time()
        for i in range(2000):
            svc.enqueue("behavior_recorded", {"label": f"act_{i}"})
        ok = _wait_until(
            lambda: svc.stats()["consumed"] >= 2000,
            timeout=15.0,
        )
        elapsed = time.time() - start
        st = svc.stats()
        assert ok, f"2000 事件应全部消费 consumed={st['consumed']}"
        assert st["consumed"] == 2000, "精确对账：无丢失"
        assert st["enqueued"] == 2000
        assert st["errors"] == 0, "消费无异常"
        svc._ensure_log()
        assert svc._log.stats["unconsumed"] == 0, "全部 ack，无未消费残留"
        assert elapsed < 10.0, f"2000 events took {elapsed:.2f}s"
        svc.stop()

    def test_5000_backpressure_no_log_corruption(self, tmp_path):
        """反压 + 并发写：EventLog 不损坏、不丢事件（崩溃重放兜底）。"""
        from core.agent.association.association_service import AssociationService
        db = str(tmp_path / "el.db")
        svc = AssociationService(db_path=db, queue_size=8)
        svc.start()
        for i in range(5000):
            svc.enqueue("intent_parsed", {"category": f"cat_{i % 7}"})
        # 全部事件应先落 EventLog（persist 不受队列反压影响）
        ok = _wait_until(lambda: svc.stats()["dropped"] > 0, timeout=5.0)
        assert ok, "小队列应触发反压丢最旧"
        # 反压丢的是唤醒信号，事件本身已在 EventLog —— 周期追赶补齐（§六）。
        ok = _wait_until(
            lambda: svc.stats()["consumed"] >= 5000,
            timeout=20.0,
        )
        assert ok, ("反压丢的事件应由 EventLog 重放兜底 "
                    f"consumed={svc.stats()['consumed']}")
        svc._ensure_log()
        assert svc._log.stats["total"] >= 5000, "EventLog 应完整记录全部事件"
        assert svc.stats()["consumed"] == 5000, "精确对账：无丢失无重复"
        assert svc._log.stats["unconsumed"] == 0, "全部 ack"
        svc.stop()

    def test_concurrent_enqueue_no_transaction_error(self, tmp_path):
        """并发 enqueue（多生产者）：EventLog 写锁串行化，无事务冲突。"""
        import threading
        from core.agent.association.association_service import AssociationService
        svc = AssociationService(db_path=str(tmp_path / "el.db"))
        svc.start()
        errors = []

        def producer(n):
            try:
                for i in range(300):
                    svc.enqueue("behavior_recorded", {"label": f"p{n}_{i}"})
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=producer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)
        assert not errors, f"并发 enqueue 不应抛错: {errors}"
        ok = _wait_until(lambda: svc.stats()["consumed"] >= 1200, timeout=15.0)
        assert ok, f"1200 并发事件应全部消费 consumed={svc.stats()['consumed']}"
        st = svc.stats()
        assert st["consumed"] == 1200, "并发场景精确对账（不重不丢）"
        assert st["errors"] == 0
        svc.stop()
