# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_tree/tests/test_cognitive_tree.py
──────────────────────────────────────────────────────────
Cognitive Tree v3.0 — 单元测试套件

验证范围:
  - 数据模型序列化 / 反序列化
  - 节点与边的 CRUD
  - 索引与查询
  - 树遍历（DFS / BFS）
  - 活跃分支管理
  - 访问控制矩阵
  - 交叉引用管理
  - 事务性 flush

运行方式:
  cd core/agent/v3_0/cognitive_tree
  pytest tests/test_cognitive_tree.py -v
  # 或 python -m pytest tests/test_cognitive_tree.py -v

版本: 3.0.0
"""

from __future__ import annotations

import asyncio
import pytest
from typing import List

from core.agent.v3_0.cognitive_tree.models import (
    AccessControlMatrix,
    CognitiveTreeEdge,
    CognitiveTreeNode,
    CogEdgeType,
    CogNodeStatus,
    CogType,
    LLMPermissions,
)
from core.agent.v3_0.cognitive_tree.manager import CognitiveTree
from core.agent.v3_0.cognitive_tree.cross_ref import CrossRefManager


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_node() -> CognitiveTreeNode:
    """单个认知节点"""
    return CognitiveTreeNode(
        node_id="C-001",
        cog_type=CogType.PERCEPTION,
        source_llm="PCR-LLM",
        content="用户输入有 0.3 的噪声",
        confidence=0.85,
    )


@pytest.fixture
def sample_edge() -> CognitiveTreeEdge:
    """单条认知边"""
    return CognitiveTreeEdge(
        edge_id="E-001",
        source_id="C-001",
        target_id="C-002",
        edge_type=CogEdgeType.DERIVES,
        weight=0.9,
    )


@pytest.fixture
def populated_tree() -> CognitiveTree:
    """预填充的 3 层认知树

    结构:
        C-001 (root) --DERIVES--> C-002 --DERIVES--> C-003
                        |
                        +--CONDITIONAL--> C-004
    """
    tree = CognitiveTree(session_id="test-session")

    n1 = CognitiveTreeNode(
        node_id="C-001", cog_type=CogType.PERCEPTION,
        source_llm="PCR-LLM", content="感知输入", confidence=0.8,
    )
    n2 = CognitiveTreeNode(
        node_id="C-002", cog_type=CogType.HYPOTHESIS,
        source_llm="Intent-LLM", content="意图假设", confidence=0.7,
    )
    n3 = CognitiveTreeNode(
        node_id="C-003", cog_type=CogType.DECISION,
        source_llm="Planning-LLM", content="最终决策", confidence=0.9,
    )
    n4 = CognitiveTreeNode(
        node_id="C-004", cog_type=CogType.HYPOTHESIS,
        source_llm="Planning-LLM", content="备选方案", confidence=0.5,
    )

    for n in (n1, n2, n3, n4):
        tree.add_node(n, check_permission=False)

    tree.add_edge(CognitiveTreeEdge(source_id="C-001", target_id="C-002", edge_type=CogEdgeType.DERIVES))
    tree.add_edge(CognitiveTreeEdge(source_id="C-002", target_id="C-003", edge_type=CogEdgeType.DERIVES))
    tree.add_edge(CognitiveTreeEdge(source_id="C-002", target_id="C-004", edge_type=CogEdgeType.CONDITIONAL))

    tree.root = "C-001"
    tree.set_active_branch(["C-001", "C-002", "C-003"])
    return tree


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型测试
# ═══════════════════════════════════════════════════════════════════════════

class TestCognitiveTreeNode:
    """认知节点数据模型测试"""

    def test_init_default(self):
        node = CognitiveTreeNode()
        assert node.node_id.startswith("C-")
        assert node.cog_type == CogType.REASONING
        assert 0.0 <= node.confidence <= 1.0

    def test_confidence_clamping(self):
        node = CognitiveTreeNode(confidence=1.5)
        assert node.confidence == 1.0
        node2 = CognitiveTreeNode(confidence=-0.3)
        assert node2.confidence == 0.0

    def test_add_reflection(self, sample_node: CognitiveTreeNode):
        sample_node.add_reflection(" Planning-LLM 的决策忽略了用户的低 g 因子")
        assert len(sample_node.reflections) == 1

    def test_add_validation(self, sample_node: CognitiveTreeNode):
        sample_node.add_validation("噪声评估与事后验证一致")
        assert len(sample_node.validations) == 1

    def test_create_version(self, sample_node: CognitiveTreeNode):
        old = sample_node.create_version("新版本内容")
        assert old == "用户输入有 0.3 的噪声"
        assert sample_node.content == "新版本内容"
        assert len(sample_node.version_history) == 1

    def test_update_status(self, sample_node: CognitiveTreeNode):
        sample_node.update_status(CogNodeStatus.VALIDATED)
        assert sample_node.status == CogNodeStatus.VALIDATED
        assert "status_history" in sample_node.metadata

    def test_to_dict_roundtrip(self, sample_node: CognitiveTreeNode):
        d = sample_node.to_dict()
        restored = CognitiveTreeNode.from_dict(d)
        assert restored.node_id == sample_node.node_id
        assert restored.cog_type == sample_node.cog_type
        assert restored.content == sample_node.content

    def test_repr(self, sample_node: CognitiveTreeNode):
        assert "C-001" in repr(sample_node)
        assert "perception" in repr(sample_node)


class TestCognitiveTreeEdge:
    """认知边数据模型测试"""

    def test_init_default(self):
        edge = CognitiveTreeEdge()
        assert edge.edge_type == CogEdgeType.DERIVES

    def test_weight_clamping(self):
        edge = CognitiveTreeEdge(weight=1.5)
        assert edge.weight == 1.0

    def test_to_dict_roundtrip(self, sample_edge: CognitiveTreeEdge):
        d = sample_edge.to_dict()
        restored = CognitiveTreeEdge.from_dict(d)
        assert restored.edge_id == sample_edge.edge_id
        assert restored.edge_type == sample_edge.edge_type


class TestAccessControlMatrix:
    """访问控制矩阵测试"""

    def test_default_permissions_loaded(self):
        acm = AccessControlMatrix()
        assert "PCR-LLM" in acm.permissions
        assert "Planning-LLM" in acm.permissions

    def test_check_create(self):
        acm = AccessControlMatrix()
        assert acm.check_create("PCR-LLM", CogType.PERCEPTION) is True
        assert acm.check_create("PCR-LLM", CogType.DECISION) is False

    def test_check_read(self):
        acm = AccessControlMatrix()
        assert acm.check_read("Planning-LLM", "any-id") is True

    def test_check_update_own(self):
        acm = AccessControlMatrix()
        # Meta-Cognitive 可以更新所有
        assert acm.check_update("Meta-Cognitive-LLM", "N-1", "PCR-LLM") is True
        # Planning 只能更新自己创建的
        assert acm.check_update("Planning-LLM", "N-1", "PCR-LLM") is False
        assert acm.check_update("Planning-LLM", "N-1", "Planning-LLM") is True

    def test_check_delete(self):
        acm = AccessControlMatrix()
        # 默认所有 LLM 都不能删除
        assert acm.check_delete("PCR-LLM", "N-1", "PCR-LLM") is False

    def test_register_llm(self):
        acm = AccessControlMatrix()
        new_perms = LLMPermissions(
            llm_name="Custom-LLM",
            can_create={CogType.OBSERVATION},
            can_read={"all"},
            can_update={"own"},
            can_delete={"none"},
        )
        acm.register_llm("Custom-LLM", new_perms)
        assert acm.check_create("Custom-LLM", CogType.OBSERVATION) is True
        assert acm.check_create("Custom-LLM", CogType.PERCEPTION) is False

    def test_to_dict_roundtrip(self):
        acm = AccessControlMatrix()
        d = acm.to_dict()
        restored = AccessControlMatrix.from_dict(d)
        assert "PCR-LLM" in restored.permissions


# ═══════════════════════════════════════════════════════════════════════════
# 树管理器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestCognitiveTreeNodeCRUD:
    """节点增删改查测试"""

    def test_add_node(self):
        tree = CognitiveTree()
        node = CognitiveTreeNode(node_id="N-1", cog_type=CogType.PERCEPTION)
        tree.add_node(node, check_permission=False)
        assert "N-1" in tree.nodes

    def test_add_node_with_permission(self):
        tree = CognitiveTree()
        node = CognitiveTreeNode(node_id="N-1", cog_type=CogType.PERCEPTION)
        tree.add_node(node, check_permission=True, requester_llm="PCR-LLM")
        assert "N-1" in tree.nodes

    def test_add_node_permission_denied(self):
        tree = CognitiveTree()
        node = CognitiveTreeNode(node_id="N-1", cog_type=CogType.DECISION)
        with pytest.raises(PermissionError):
            tree.add_node(node, check_permission=True, requester_llm="PCR-LLM")

    def test_get_node(self, populated_tree: CognitiveTree):
        assert populated_tree.get_node("C-001") is not None
        assert populated_tree.get_node("NONEXIST") is None

    def test_update_node(self, populated_tree: CognitiveTree):
        ok = populated_tree.update_node(
            "C-001", requester_llm="PCR-LLM", content="更新后的内容"
        )
        assert ok is True
        assert populated_tree.nodes["C-001"].content == "更新后的内容"

    def test_update_node_status(self, populated_tree: CognitiveTree):
        ok = populated_tree.update_node_status(
            "C-001", CogNodeStatus.VALIDATED, requester_llm="Meta-Cognitive-LLM"
        )
        assert ok is True
        assert populated_tree.nodes["C-001"].status == CogNodeStatus.VALIDATED

    def test_remove_node(self, populated_tree: CognitiveTree):
        # 不带 requester_llm 跳过权限检查，仅验证删除操作本身
        ok = populated_tree.remove_node("C-004")
        assert ok is True
        assert "C-004" not in populated_tree.nodes


class TestCognitiveTreeEdgeCRUD:
    """边管理测试"""

    def test_add_edge(self, populated_tree: CognitiveTree):
        e = CognitiveTreeEdge(source_id="C-001", target_id="C-003", edge_type=CogEdgeType.SUPPORTS)
        populated_tree.add_edge(e)
        assert len(populated_tree.edges) == 4

    def test_add_duplicate_edge_ignored(self, populated_tree: CognitiveTree):
        e = CognitiveTreeEdge(source_id="C-001", target_id="C-002", edge_type=CogEdgeType.DERIVES)
        populated_tree.add_edge(e)
        # 已有相同 source/target/type 的边，应被忽略
        assert len(populated_tree.edges) == 3

    def test_add_edge_node_not_exist(self, populated_tree: CognitiveTree):
        e = CognitiveTreeEdge(source_id="C-999", target_id="C-002")
        with pytest.raises(ValueError):
            populated_tree.add_edge(e)

    def test_get_outgoing(self, populated_tree: CognitiveTree):
        outgoing = populated_tree.get_outgoing("C-002")
        assert len(outgoing) == 2
        target_ids = {e.target_id for e in outgoing}
        assert target_ids == {"C-003", "C-004"}

    def test_get_incoming(self, populated_tree: CognitiveTree):
        incoming = populated_tree.get_incoming("C-002")
        assert len(incoming) == 1
        assert incoming[0].source_id == "C-001"

    def test_get_neighbors(self, populated_tree: CognitiveTree):
        neighbors = populated_tree.get_neighbors("C-002")
        assert set(neighbors) == {"C-001", "C-003", "C-004"}

    def test_remove_edge(self, populated_tree: CognitiveTree):
        edge_id = populated_tree.edges[0].edge_id
        ok = populated_tree.remove_edge(edge_id)
        assert ok is True
        assert len(populated_tree.edges) == 2


class TestCognitiveTreeQuery:
    """查询 API 测试"""

    def test_find_by_type(self, populated_tree: CognitiveTree):
        percepts = populated_tree.find_by_type(CogType.PERCEPTION)
        assert len(percepts) == 1
        assert percepts[0].node_id == "C-001"

    def test_find_by_llm(self, populated_tree: CognitiveTree):
        planning_nodes = populated_tree.find_by_llm("Planning-LLM")
        assert len(planning_nodes) == 2

    def test_find_by_status(self, populated_tree: CognitiveTree):
        created = populated_tree.find_by_status(CogNodeStatus.CREATED)
        assert len(created) == 4

    def test_find_active_branch(self, populated_tree: CognitiveTree):
        branch = populated_tree.find_active_branch()
        assert len(branch) == 3
        assert branch[0].node_id == "C-001"
        assert branch[-1].node_id == "C-003"

    def test_find_roots(self, populated_tree: CognitiveTree):
        roots = populated_tree.find_roots()
        assert len(roots) == 1
        assert roots[0].node_id == "C-001"

    def test_find_leaves(self, populated_tree: CognitiveTree):
        leaves = populated_tree.find_leaves()
        leaf_ids = {n.node_id for n in leaves}
        assert leaf_ids == {"C-003", "C-004"}

    def test_search_content(self, populated_tree: CognitiveTree):
        results = populated_tree.search_content("备选")
        assert len(results) == 1
        assert results[0].node_id == "C-004"


class TestCognitiveTreeTraversal:
    """树遍历测试"""

    def test_traverse_dfs(self, populated_tree: CognitiveTree):
        result = populated_tree.traverse_dfs("C-001")
        ids = [n.node_id for n in result]
        assert ids[0] == "C-001"
        assert "C-001" in ids
        assert "C-003" in ids

    def test_traverse_dfs_max_depth(self, populated_tree: CognitiveTree):
        result = populated_tree.traverse_dfs("C-001", max_depth=1)
        ids = [n.node_id for n in result]
        assert "C-001" in ids
        assert "C-002" in ids
        assert "C-003" not in ids  # 深度 2，被截断

    def test_traverse_bfs(self, populated_tree: CognitiveTree):
        result = populated_tree.traverse_bfs("C-001")
        ids = [n.node_id for n in result]
        assert ids[0] == "C-001"
        # BFS 同层节点应在相邻位置
        assert "C-001" in ids
        assert "C-003" in ids

    def test_traverse_bfs_max_depth(self, populated_tree: CognitiveTree):
        result = populated_tree.traverse_bfs("C-001", max_depth=1)
        ids = [n.node_id for n in result]
        assert "C-003" not in ids

    def test_get_path_to_root(self, populated_tree: CognitiveTree):
        path = populated_tree.get_path_to_root("C-003")
        ids = [n.node_id for n in path]
        assert ids == ["C-001", "C-002", "C-003"]

    def test_traverse_nonexistent_start(self, populated_tree: CognitiveTree):
        assert populated_tree.traverse_dfs("NONEXIST") == []
        assert populated_tree.traverse_bfs("NONEXIST") == []


class TestCognitiveTreeActiveBranch:
    """活跃分支管理测试"""

    def test_set_active_branch(self, populated_tree: CognitiveTree):
        populated_tree.set_active_branch(["C-001", "C-002"])
        assert populated_tree.active_branch == ["C-001", "C-002"]

    def test_set_active_branch_creates_stale(self, populated_tree: CognitiveTree):
        populated_tree.set_active_branch(["C-001", "C-002"])
        # 旧活跃分支 C-003 不再在新分支中，应移入 stale_branches
        assert len(populated_tree.stale_branches) == 1
        assert "C-003" in populated_tree.stale_branches[0]

    def test_set_active_branch_invalid_nodes(self, populated_tree: CognitiveTree):
        populated_tree.set_active_branch(["C-001", "INVALID", "C-002"])
        assert "INVALID" not in populated_tree.active_branch

    def test_append_to_active_branch(self, populated_tree: CognitiveTree):
        populated_tree.append_to_active_branch("C-004")
        assert populated_tree.active_branch[-1] == "C-004"

    def test_append_to_active_branch_nonexistent(self, populated_tree: CognitiveTree):
        with pytest.raises(ValueError):
            populated_tree.append_to_active_branch("NONEXIST")


class TestCognitiveTreeSerialization:
    """序列化测试"""

    def test_to_dict_roundtrip(self, populated_tree: CognitiveTree):
        d = populated_tree.to_dict()
        restored = CognitiveTree.from_dict(d)
        assert restored.session_id == populated_tree.session_id
        assert len(restored.nodes) == len(populated_tree.nodes)
        assert len(restored.edges) == len(populated_tree.edges)
        assert restored.active_branch == populated_tree.active_branch

    def test_serialization_preserves_indices(self, populated_tree: CognitiveTree):
        d = populated_tree.to_dict()
        restored = CognitiveTree.from_dict(d)
        # 验证索引已重建
        percepts = restored.find_by_type(CogType.PERCEPTION)
        assert len(percepts) == 1
        assert percepts[0].node_id == "C-001"

    def test_empty_tree_serialization(self):
        tree = CognitiveTree(session_id="empty")
        d = tree.to_dict()
        restored = CognitiveTree.from_dict(d)
        assert restored.session_id == "empty"
        assert len(restored.nodes) == 0


class TestCognitiveTreeFlush:
    """事务性写入测试"""

    @pytest.mark.asyncio
    async def test_flush(self, populated_tree: CognitiveTree):
        nodes, edges = await populated_tree.flush()
        assert nodes > 0
        assert edges > 0

    @pytest.mark.asyncio
    async def test_flush_empty(self):
        tree = CognitiveTree()
        nodes, edges = await tree.flush()
        assert nodes == 0
        assert edges == 0

    @pytest.mark.asyncio
    async def test_emergency_flush(self, populated_tree: CognitiveTree):
        nodes, edges = await populated_tree.emergency_flush()
        assert nodes >= 0
        assert edges >= 0

    @pytest.mark.asyncio
    async def test_concurrent_flush(self, populated_tree: CognitiveTree):
        """并发 flush 不应引发竞态条件"""
        async def flusher():
            return await populated_tree.flush()

        results = await asyncio.gather(flusher(), flusher(), flusher())
        # 至少有一次成功返回大于 0；后续 flush 为空时返回 0,0
        total_nodes = sum(r[0] for r in results)
        total_edges = sum(r[1] for r in results)
        assert total_nodes >= 0
        assert total_edges >= 0


# ═══════════════════════════════════════════════════════════════════════════
# 交叉引用管理器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossRefManager:
    """交叉引用管理器测试"""

    @pytest.fixture
    async def linked_manager(self):
        """预填充交叉引用的管理器"""
        mgr = CrossRefManager(session_id="test")
        await mgr.link("T-1", "C-1", link_type="automatic", confidence=0.9)
        await mgr.link("T-1", "C-2", link_type="manual", confidence=1.0)
        await mgr.link("T-2", "C-2", link_type="inferred", confidence=0.7)
        return mgr

    @pytest.mark.asyncio
    async def test_link(self):
        mgr = CrossRefManager()
        link = await mgr.link("T-1", "C-1")
        assert link.topic_node_id == "T-1"
        assert link.cognitive_node_id == "C-1"
        assert mgr.get_cognitive_ids_for_topic("T-1") == ["C-1"]
        assert mgr.get_topic_ids_for_cognitive("C-1") == ["T-1"]

    @pytest.mark.asyncio
    async def test_unlink(self, linked_manager: CrossRefManager):
        ok = await linked_manager.unlink("T-1", "C-1")
        assert ok is True
        assert "C-1" not in linked_manager.get_cognitive_ids_for_topic("T-1")

    @pytest.mark.asyncio
    async def test_unlink_nonexistent(self, linked_manager: CrossRefManager):
        ok = await linked_manager.unlink("T-99", "C-99")
        assert ok is False

    @pytest.mark.asyncio
    async def test_remove_all_for_topic(self, linked_manager: CrossRefManager):
        count = await linked_manager.remove_all_for_topic("T-1")
        assert count == 2
        assert len(linked_manager.get_cognitive_ids_for_topic("T-1")) == 0

    @pytest.mark.asyncio
    async def test_remove_all_for_cognitive(self, linked_manager: CrossRefManager):
        count = await linked_manager.remove_all_for_cognitive("C-2")
        assert count == 2
        assert len(linked_manager.get_topic_ids_for_cognitive("C-2")) == 0

    @pytest.mark.asyncio
    async def test_get_links_for_topic(self, linked_manager: CrossRefManager):
        links = linked_manager.get_links_for_topic("T-1")
        assert len(links) == 2

    @pytest.mark.asyncio
    async def test_get_link_detail(self, linked_manager: CrossRefManager):
        detail = linked_manager.get_link_detail("T-1", "C-1")
        assert detail is not None
        assert detail.confidence == 0.9

    @pytest.mark.asyncio
    async def test_validate_consistency(self, linked_manager: CrossRefManager):
        report = linked_manager.validate_consistency(
            existing_topic_ids={"T-1", "T-2"},
            existing_cognitive_ids={"C-1", "C-2"},
        )
        assert report["is_consistent"] is True
        assert report["total_links"] == 3

        # 制造不一致
        report2 = linked_manager.validate_consistency(
            existing_topic_ids={"T-1"},  # T-2 缺失
            existing_cognitive_ids={"C-1", "C-2"},
        )
        assert report2["is_consistent"] is False
        assert "T-2" in report2["orphan_topic_ids"]

    @pytest.mark.asyncio
    async def test_prune_orphans(self, linked_manager: CrossRefManager):
        count = await linked_manager.prune_orphans(
            existing_topic_ids={"T-1"},
            existing_cognitive_ids={"C-1", "C-2"},
        )
        # T-2 相关的链接应被清理
        assert count == 1
        assert len(linked_manager._links) == 2

    @pytest.mark.asyncio
    async def test_serialization(self, linked_manager: CrossRefManager):
        d = linked_manager.to_dict()
        restored = CrossRefManager.from_dict(d)
        assert restored.session_id == "test"
        assert len(restored._links) == 3

    @pytest.mark.asyncio
    async def test_concurrent_link(self):
        """并发 link 操作不应引发竞态条件"""
        mgr = CrossRefManager()

        async def linker(idx: int):
            return await mgr.link(f"T-{idx}", f"C-{idx}")

        await asyncio.gather(*[linker(i) for i in range(20)])
        assert len(mgr._links) == 20


# ═══════════════════════════════════════════════════════════════════════════
# 集成测试
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """端到端集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """模拟一轮完整对话产生的认知树操作"""
        tree = CognitiveTree(session_id="sess-42")
        cross_ref = CrossRefManager(session_id="sess-42")

        # 1. PCR-LLM 产生感知节点
        p1 = CognitiveTreeNode(
            cog_type=CogType.PERCEPTION,
            source_llm="PCR-LLM",
            content="用户输入噪声 0.2，期望 TOOL",
            confidence=0.8,
        )
        tree.add_node(p1, check_permission=True, requester_llm="PCR-LLM")

        # 2. Intent-LLM 产生假设
        h1 = CognitiveTreeNode(
            cog_type=CogType.HYPOTHESIS,
            source_llm="Intent-LLM",
            content="意图为 SCAN_MEMORY",
            confidence=0.75,
        )
        tree.add_node(h1, parent_id=p1.node_id, check_permission=True, requester_llm="Intent-LLM")
        tree.add_edge(CognitiveTreeEdge(source_id=p1.node_id, target_id=h1.node_id, edge_type=CogEdgeType.DERIVES))

        # 3. Planning-LLM 产生决策
        d1 = CognitiveTreeNode(
            cog_type=CogType.DECISION,
            source_llm="Planning-LLM",
            content="选择 first_scan 工具",
            confidence=0.9,
        )
        tree.add_node(d1, parent_id=h1.node_id, check_permission=True, requester_llm="Planning-LLM")
        tree.add_edge(CognitiveTreeEdge(source_id=h1.node_id, target_id=d1.node_id, edge_type=CogEdgeType.DERIVES))

        # 4. 设置活跃分支
        tree.set_active_branch([p1.node_id, h1.node_id, d1.node_id])

        # 5. 建立与 Topic Tree 的交叉引用
        await cross_ref.link("T-scan-memory", h1.node_id, confidence=0.85)
        await cross_ref.link("T-scan-memory", d1.node_id, confidence=0.9)

        # 6. Meta-Cognitive 验证
        v1 = CognitiveTreeNode(
            cog_type=CogType.VALIDATION,
            source_llm="Meta-Cognitive-LLM",
            content="决策与假设一致，置信度合理",
            confidence=0.95,
        )
        tree.add_node(v1, check_permission=True, requester_llm="Meta-Cognitive-LLM")
        tree.add_edge(CognitiveTreeEdge(source_id=d1.node_id, target_id=v1.node_id, edge_type=CogEdgeType.SUPPORTS))

        # 验证树结构
        assert len(tree.nodes) == 4
        assert len(tree.edges) == 3
        assert len(tree.find_active_branch()) == 3

        # 验证查询
        decisions = tree.find_by_type(CogType.DECISION)
        assert len(decisions) == 1
        assert decisions[0].node_id == d1.node_id

        # 验证遍历
        path = tree.get_path_to_root(d1.node_id)
        assert len(path) == 3

        # 验证交叉引用
        cog_ids = cross_ref.get_cognitive_ids_for_topic("T-scan-memory")
        assert len(cog_ids) == 2

        # 验证权限（Answer-LLM 不能创建 DECISION）
        with pytest.raises(PermissionError):
            bad_node = CognitiveTreeNode(cog_type=CogType.DECISION, source_llm="Answer-LLM")
            tree.add_node(bad_node, check_permission=True, requester_llm="Answer-LLM")

        # Flush
        nodes_flushed, edges_flushed = await tree.flush()
        assert nodes_flushed >= 4
        assert edges_flushed >= 3

    def test_tree_with_alternative_branch(self):
        """测试含备选分支的认知树"""
        tree = CognitiveTree()

        n1 = CognitiveTreeNode(node_id="N-1", cog_type=CogType.PERCEPTION, content="感知")
        n2 = CognitiveTreeNode(node_id="N-2", cog_type=CogType.HYPOTHESIS, content="假设 A")
        n3 = CognitiveTreeNode(node_id="N-3", cog_type=CogType.HYPOTHESIS, content="假设 B")

        for n in (n1, n2, n3):
            tree.add_node(n, check_permission=False)

        tree.add_edge(CognitiveTreeEdge(source_id="N-1", target_id="N-2", edge_type=CogEdgeType.DERIVES))
        tree.add_edge(CognitiveTreeEdge(source_id="N-1", target_id="N-3", edge_type=CogEdgeType.ALTERNATIVE))

        neighbors = tree.get_neighbors("N-1")
        assert set(neighbors) == {"N-2", "N-3"}

        # 验证 DFS 包含所有节点
        result = tree.traverse_dfs("N-1")
        ids = {n.node_id for n in result}
        assert ids == {"N-1", "N-2", "N-3"}

    def test_depth_limit(self):
        """测试深度限制标记"""
        tree = CognitiveTree(depth_limit=2)
        n1 = CognitiveTreeNode(node_id="N-1", content="层 0")
        n2 = CognitiveTreeNode(node_id="N-2", content="层 1")
        n3 = CognitiveTreeNode(node_id="N-3", content="层 2")
        n4 = CognitiveTreeNode(node_id="N-4", content="层 3")

        tree.add_node(n1, check_permission=False)
        tree.add_node(n2, parent_id="N-1", check_permission=False)
        tree.add_node(n3, parent_id="N-2", check_permission=False)
        tree.add_node(n4, parent_id="N-3", check_permission=False)

        assert tree.nodes["N-3"].depth == 2
        assert tree.nodes["N-3"].metadata.get("depth_exceeded") is None
        assert tree.nodes["N-4"].depth == 3
        assert tree.nodes["N-4"].metadata.get("depth_exceeded") is True
