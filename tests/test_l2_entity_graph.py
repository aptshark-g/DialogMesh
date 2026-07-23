"""L2 Semantic Ontology — RelationSubstrate + Entity Graph integration test."""

import sys
sys.path.insert(0, '.')
from core.agent.compiler.relation_substrate import (
    RelationSubstrate, EntityNode, Evidence, RelationEdge
)
from core.agent.compiler.topic_quick_match import TopicQuickMatcher


def test_entity_node():
    n = EntityNode(entity_id="e1", name="延迟", types=["现象"], cluster_id="latency", last_seen_turn=3)
    assert n.name == "延迟"
    assert n.types == ["现象"]
    print("✅ EntityNode")


def test_conversation_edge():
    rs = RelationSubstrate()
    rs.add_entity(EntityNode("e1", "延迟", ["现象"], "latency", 1, 3))
    rs.add_entity(EntityNode("e2", "监控", ["工具"], "monitor", 0, 2))

    eid = rs.add_conversation_edge("e1", "e2", "co_occurrence", turn_num=3,
                                   bm25_score=0.7, llm_confidence=0.85)
    edges = rs._edges; edge = edges.get(eid)
    assert edge is not None
    assert edge.confidence == 0.85
    assert len(edge.evidence) == 2  # BM25 + LLM
    assert edge.evidence[0].source == "conversation_bm25"
    assert edge.evidence[1].source == "conversation_llm"
    print(f"✅ conversation_edge: conf={edge.confidence}, {len(edge.evidence)} evidence")


def test_two_hop():
    rs = RelationSubstrate()
    for eid, name in [("e1","延迟"),("e2","监控"),("e3","告警"),("e4","重试")]:
        rs.add_entity(EntityNode(eid, name, [], "", 0, 0))

    rs.add_conversation_edge("e1", "e2", "co_occurrence", 1, 0.8, 0.0)
    rs.add_conversation_edge("e2", "e3", "causes", 2, 0.7, 0.9)
    rs.add_conversation_edge("e3", "e4", "triggers", 3, 0.6, 0.0)

    neighbors = rs.entity_neighbors("e1", hops=2)
    assert len(neighbors["1hop"]) >= 1, "1-hop should find e2"
    assert len(neighbors["2hop"]) >= 1, "2-hop should find e3"
    print(f"✅ 2-hop: 1hop={neighbors['1hop']}, 2hop={neighbors['2hop']}")


if __name__ == "__main__":
    test_entity_node()
    test_conversation_edge()
    test_two_hop()
    print("\n🎉 L2 Entity Graph: all tests passed")
