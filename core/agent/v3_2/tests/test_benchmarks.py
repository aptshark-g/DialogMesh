"""Performance benchmarks for v3.2 modules"""
import sys, os, asyncio, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
pytest.importorskip("pytest_benchmark")

from core.agent.testing_utils import MockLLM, DEFAULT_COMPILER_RESPONSE
from core.agent.compiler.hybrid_compiler import HybridCompiler
from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.models import BehaviorStep
from core.agent.association.fusion_engine import FusionEngine
from core.agent.association.models import TrackType, TrackResult
from core.agent.compiler.degradation_manager import DegradationManager

def test_bm_compiler(benchmark):
    c = HybridCompiler(MockLLM(DEFAULT_COMPILER_RESPONSE))
    async def _run():
        return await c.process("run the program")
    result = benchmark(lambda: asyncio.run(_run()))
    assert result is not None
    assert result.is_reliable

def test_bm_graph(benchmark):
    def _run():
        g = BehaviorGraph()
        for i in range(100):
            g.record_edge(BehaviorStep(f"s{i}",f"a{i}","TOOL_EXEC"), BehaviorStep(f"s{i+1}",f"a{i+1}","LOG_CHECK"))
        return g
    g = benchmark(_run)
    assert len(g.nodes) >= 100

def test_bm_fusion(benchmark):
    fe = FusionEngine()
    trs = [TrackResult(TrackType.TRACK_0,{"d":"x"},0.85), TrackResult(TrackType.TRACK_1,{"intent":"x"},0.90), TrackResult(TrackType.TRACK_P,{"predicted_actions":["a"]},0.70), TrackResult(TrackType.CAUSAL,{"p":0.6},0.60)]
    async def _run():
        return await fe.fuse(*trs)
    result = benchmark(lambda: asyncio.run(_run()))
    assert result.confidence > 0.5

def test_bm_degradation(benchmark):
    """DegradationManager benchmark: validate failure mode triggers and reset behavior."""
    def _run():
        dm = DegradationManager()
        # 20 consecutive failures -> mode switches to RULE
        for _ in range(20):
            dm.on_failure()
        # Reset via success
        dm.on_success()
        # 10 more consecutive failures
        for _ in range(10):
            dm.on_failure()
        return dm
    dm = benchmark(_run)
    assert dm.mode == DegradationManager.MODE_RULE
    assert dm.fails == 10
    assert dm.get_status()["mode"] == DegradationManager.MODE_RULE
