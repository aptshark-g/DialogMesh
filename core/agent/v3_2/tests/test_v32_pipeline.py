import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.v3_2.integration import V32Pipeline
from core.agent.v3_2.testing_utils import MockLLM, DEFAULT_COMPILER_RESPONSE
pytestmark = pytest.mark.asyncio


def mkpipe():
    return V32Pipeline(MockLLM(DEFAULT_COMPILER_RESPONSE))


class TestV32:
    async def test_basic(self):
        r = await mkpipe().process("run")
        assert r["turn"] == 1

    async def test_graph(self):
        p = mkpipe()
        await p.process("run")
        assert p.get_status()["graph_nodes"] >= 1

    async def test_multi(self):
        p = mkpipe()
        for s in ["run", "check"]:
            await p.process(s)
        assert p.turn == 2

    async def test_no_graph(self):
        p = V32Pipeline(MockLLM(DEFAULT_COMPILER_RESPONSE), enable_graph=False)
        await p.process("x")
        assert p.turn == 1

    async def test_status(self):
        assert mkpipe().get_status()["turn"] == 0

    async def test_empty(self):
        r = await mkpipe().process("")
        assert r is not None
