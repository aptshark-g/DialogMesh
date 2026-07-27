import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.foa.models import AttentionNode, FocusResult
from core.agent.foa.actr_activator import ACTRActivator
from core.agent.foa.foa import FoA

class TestModels:
    def test_attention_node(self):
        n = AttentionNode("s1", 0.5)
        assert n.node_id == "s1"
        assert n.activation == 0.5
    def test_focus_top_k(self):
        fr = FocusResult([], [AttentionNode("a", 0.9), AttentionNode("b", 0.3)], [], 0.3)
        top = fr.top_k
        assert top[0].node_id == "a"

class TestActivator:
    def test_empty(self):
        assert ACTRActivator().propagate([], {}, {}) == []
    def test_simple(self):
        r = ACTRActivator().propagate(["s1"], {"s1": 1}, {("s1","s2"): 0.8})
        assert len(r) > 0

class TestFoA:
    def test_fallback(self):
        r = FoA().focus("", "", {}, {})
        assert r.fallback_used
    def test_with_seeds(self):
        r = FoA().focus("", "s1", {"s1": 1}, {})
        assert not r.fallback_used
        assert "s1" in r.seed_nodes