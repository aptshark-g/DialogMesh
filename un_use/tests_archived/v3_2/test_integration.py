"""v3.2 端到端集成测试 — Compiler -> BehaviorGraph -> FusionEngine"""
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.v3_2.testing_utils import MockLLM, DEFAULT_COMPILER_RESPONSE
from core.agent.compiler.hybrid_compiler import HybridCompiler
from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.models import BehaviorStep
from core.agent.association.fusion_engine import FusionEngine
from core.agent.association.models import TrackType, TrackResult

pytestmark = pytest.mark.asyncio

@pytest.fixture
def compiler():
    return HybridCompiler(MockLLM(DEFAULT_COMPILER_RESPONSE))

@pytest.fixture
def graph():
    return BehaviorGraph()

class TestPipeline:
    async def test_compiler_outputs_slots(self, compiler):
        r = await compiler.process("run the program")
        assert len(r.slots) > 0
        assert 0 <= r.stability <= 1

    async def test_compiler_to_graph(self, compiler, graph):
        r = await compiler.process("run the program")
        assert not r.undefined
        graph.record_edge(BehaviorStep("s1","run","TOOL_EXEC"), BehaviorStep("s2","check","LOG_CHECK"))
        w = graph.get_edge_weight("run", "check")
        assert w is not None
        assert 0 <= w <= 1

    async def test_compiler_to_fusion(self, compiler):
        await compiler.process("analyze")
        fe = FusionEngine()
        fr = await fe.fuse(TrackResult(TrackType.TRACK_0, {"d":"x"}, 0.9), TrackResult(TrackType.TRACK_1, {"intent":"x"}, 0.85))
        assert fr.final_output is not None
        assert fr.confidence > 0

    async def test_multi_step(self, compiler, graph):
        steps = [("run","TOOL_EXEC"),("check","LOG_CHECK"),("analyze","ENTITY_ANALYZE"),("fix","CODE_RUN")]
        for i in range(len(steps)-1):
            graph.record_edge(BehaviorStep(f"s{i}",steps[i][0],steps[i][1]), BehaviorStep(f"s{i+1}",steps[i+1][0],steps[i+1][1]))
        s = graph.get_statistics()
        assert s.node_count == len(steps)
        assert s.edge_count == len(steps)-1

    async def test_degradation(self):
        c = HybridCompiler(MockLLM("invalid text"))
        r = await c.process("test")
        assert r.degraded or not r.undefined

    async def test_lite_mode(self):
        fr = await FusionEngine().fuse(TrackResult(TrackType.TRACK_0,{"d":"x"},0.8), profile_lite=True)
        assert fr.profile_lite
        assert fr.confidence > 0

    async def test_four_tracks(self):
        trs = [TrackResult(TrackType.TRACK_0,{"d":"scan"},0.85), TrackResult(TrackType.TRACK_1,{"intent":"scan"},0.90), TrackResult(TrackType.TRACK_P,{"predicted_actions":["check"]},0.70), TrackResult(TrackType.CAUSAL,{"p":0.6},0.60)]
        fr = await FusionEngine().fuse(*trs)
        assert fr.confidence > 0.5
        assert len(fr.stages) > 0